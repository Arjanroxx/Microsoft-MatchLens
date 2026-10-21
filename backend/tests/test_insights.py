import copy
import json
import unittest
from pathlib import Path

from backend.app.evidence import (
    EvidenceError,
    build_evidence_packet,
    build_prompt,
)
from backend.app.narrative import (
    build_candidate_payload,
    generate_insight,
)
from backend.app.providers import LocalDemoProvider
from backend.app.verification import (
    audit_language,
    audit_numeric_tokens,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PATH = REPO_ROOT / "data" / "examples" / "short-match"


def sample_summary():
    """Small fixture matching the checked-in MatchLens summary shape."""
    return {
        "match_id": "synthetic-v1.3-match-2-5",
        "teams": {
            "home": {
                "team_id": "home",
                "name": "Northbridge FC",
                "goals": 1,
                "passes": {
                    "attempted": 42,
                    "completed": 29,
                    "incomplete": 13,
                    "accuracy_percentage": 69.05,
                },
                "shots": {"total": 2, "on_target": 1, "off_target": 1},
                "recoveries": 14,
                "possession": {"percentage": 51.32, "time_ms": 283509},
            },
            "away": {
                "team_id": "away",
                "name": "Southbank FC",
                "goals": 1,
                "passes": {
                    "attempted": 41,
                    "completed": 27,
                    "incomplete": 14,
                    "accuracy_percentage": 65.85,
                },
                "shots": {"total": 1, "on_target": 1, "off_target": 0},
                "recoveries": 13,
                "possession": {"percentage": 48.68, "time_ms": 268937},
            },
        },
        "possession": {
            "method": "team_phase_time_v1",
            "elapsed_time_ms": 600000,
        },
    }


class ScriptedProvider:
    """A deterministic test double; it returns exactly what the test supplies."""

    name = "mock-scripted"

    def __init__(self, response):
        self.response = response

    def generate(self, prompt):
        return self.response


class FailingProvider:
    """A test double that simulates a provider exception."""

    name = "mock-failing"

    def __init__(self, error):
        self.error = error

    def generate(self, prompt):
        raise self.error


class EvidenceReaderTests(unittest.TestCase):
    def setUp(self):
        self.summary = sample_summary()
        self.packet = build_evidence_packet(self.summary)

    def test_checked_in_summary_extracts_exact_values(self):
        summary = json.loads(
            (SAMPLE_PATH / "summary.json").read_text(encoding="utf-8")
        )
        packet = build_evidence_packet(summary)

        self.assertEqual(packet.match_id, summary["match_id"])
        self.assertEqual(
            packet.fact("ev-home-possession_percentage").value, 51.32
        )
        self.assertEqual(
            packet.fact("ev-home-pass_accuracy_percentage").value, 69.05
        )
        self.assertEqual(packet.fact("ev-home-shots").value, 2)
        self.assertEqual(packet.fact("ev-home-recoveries").value, 14)
        self.assertEqual(
            packet.fact("ev-away-possession_percentage").value, 48.68
        )

    def test_live_calculate_statistics_shape_is_supported(self):
        from simulator.statistics import calculate_statistics

        metadata = json.loads(
            (SAMPLE_PATH / "metadata.json").read_text(encoding="utf-8")
        )
        events = [
            json.loads(line)
            for line in (SAMPLE_PATH / "events.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        ]
        live = calculate_statistics(metadata, events)
        packet = build_evidence_packet(live, focus_team="home")

        self.assertIsNone(packet.match_id)
        self.assertEqual(
            packet.fact("ev-home-possession_percentage").value, 51.32
        )
        self.assertEqual(packet.fact("ev-home-shots").value, 2)

    def test_missing_optional_fields_are_omitted_not_zero(self):
        summary = copy.deepcopy(self.summary)
        del summary["teams"]["home"]["possession"]
        del summary["teams"]["home"]["passes"]["accuracy_percentage"]

        packet = build_evidence_packet(summary)
        home_metrics = {fact.metric for fact in packet.facts_for_team("home")}

        self.assertNotIn("possession_percentage", home_metrics)
        self.assertNotIn("pass_accuracy_percentage", home_metrics)
        self.assertIn("shots", home_metrics)
        self.assertTrue(all(fact.value is not None for fact in packet.facts))

    def test_malformed_fields_raise_evidence_error(self):
        def remove_all_stats(summary):
            for team_id in ("home", "away"):
                name = summary["teams"][team_id]["name"]
                summary["teams"][team_id].clear()
                summary["teams"][team_id]["name"] = name

        mutations = {
            "missing team": lambda s: s["teams"].pop("away"),
            "empty team name": lambda s: s["teams"]["home"].__setitem__(
                "name", ""
            ),
            "string goals": lambda s: s["teams"]["home"].__setitem__(
                "goals", "1"
            ),
            "boolean goals": lambda s: s["teams"]["home"].__setitem__(
                "goals", True
            ),
            "float count": lambda s: s["teams"]["home"].__setitem__(
                "goals", 1.0
            ),
            "passes not object": lambda s: s["teams"]["home"].__setitem__(
                "passes", []
            ),
            "negative shots": lambda s: s["teams"]["home"]["shots"].__setitem__(
                "total", -1
            ),
            "shots mismatch": lambda s: s["teams"]["home"]["shots"].__setitem__(
                "on_target", 9
            ),
            "passes mismatch": lambda s: s["teams"]["home"]["passes"].__setitem__(
                "completed", 999
            ),
            "percentage too high": lambda s: s["teams"]["home"][
                "possession"
            ].__setitem__("percentage", 120),
            "non-finite number": lambda s: s["teams"]["home"][
                "passes"
            ].__setitem__("accuracy_percentage", float("nan")),
            "team id mismatch": lambda s: s["teams"]["home"].__setitem__(
                "team_id", "away"
            ),
            "bad match id": lambda s: s.__setitem__("match_id", 123),
            "teams not object": lambda s: s.__setitem__("teams", []),
            "no usable facts": remove_all_stats,
        }

        for name, mutate in mutations.items():
            with self.subTest(case=name):
                summary = sample_summary()
                mutate(summary)
                with self.assertRaises(EvidenceError):
                    build_evidence_packet(summary)

    def test_prompt_is_structured_and_constrained(self):
        prompt = build_prompt(
            self.packet, "casual", ("casual_form", "generic_fact")
        )
        payload = json.loads(prompt)

        self.assertEqual(payload["focus_team"], "home")
        self.assertEqual(
            payload["allowed_template_ids"], ["casual_form", "generic_fact"]
        )
        self.assertIn("Do not write a headline", " ".join(payload["rules"]))
        self.assertTrue(payload["facts"])


class NarrativePipelineTests(unittest.TestCase):
    def setUp(self):
        self.summary = sample_summary()
        self.packet = build_evidence_packet(self.summary)

    def _run(self, candidate, mode="casual"):
        return generate_insight(
            self.packet,
            mode,
            ScriptedProvider(json.dumps(candidate)),
        )

    def _assert_fallback(self, result, reason="verification_failed"):
        self.assertEqual(result["status"], "fallback")
        self.assertEqual(result["fallback_reason"], reason)
        self.assertTrue(result["claims"])
        self.assertEqual(
            set(result["evidence_ids"]),
            {claim["evidence_id"] for claim in result["claims"]},
        )

    def test_local_demo_casual_and_analyst_are_verified_and_different(self):
        casual = generate_insight(
            self.packet,
            "casual",
            LocalDemoProvider(self.packet, "casual"),
        )
        analyst = generate_insight(
            self.packet,
            "analyst",
            LocalDemoProvider(self.packet, "analyst"),
        )

        self.assertEqual(casual["status"], "verified")
        self.assertEqual(casual["provider"], "local-demo")
        self.assertEqual(casual["template_id"], "casual_form")
        self.assertIn("51.32", casual["explanation"])
        self.assertIn("69.05", casual["explanation"])
        self.assertNotIn("29/42", casual["explanation"])
        self.assertIsNone(casual["fallback_reason"])

        self.assertEqual(analyst["status"], "verified")
        self.assertEqual(analyst["provider"], "local-demo")
        self.assertEqual(analyst["template_id"], "analyst_form")
        self.assertIn("29/42", analyst["explanation"])
        self.assertIn("1 on target", analyst["explanation"])
        self.assertNotEqual(casual["explanation"], analyst["explanation"])

        for result in (casual, analyst):
            self.assertEqual(
                set(result["evidence_ids"]),
                {claim["evidence_id"] for claim in result["claims"]},
            )
            self.assertIn("Descriptive statistics only", result["caveat"])

    def test_wrong_value_type_metric_and_team_are_rejected(self):
        mutations = {
            "wrong value": lambda c: c["claims"][0].__setitem__(
                "value", 999
            ),
            "wrong metric": lambda c: c["claims"][0].__setitem__(
                "metric", "shots"
            ),
            "wrong team": lambda c: c["claims"][0].__setitem__(
                "team_id", "away"
            ),
            "string number": lambda c: c["claims"][0].__setitem__(
                "value", "51.32"
            ),
            "boolean number": lambda c: c["claims"][0].__setitem__(
                "value", True
            ),
        }

        for name, mutate in mutations.items():
            with self.subTest(case=name):
                candidate = build_candidate_payload(
                    self.packet, "casual", "casual_form"
                )
                mutate(candidate)
                self._assert_fallback(self._run(candidate))

    def test_integer_fact_rejects_float_value(self):
        candidate = build_candidate_payload(
            self.packet, "casual", "casual_workrate"
        )
        self.assertEqual(candidate["claims"][0]["metric"], "recoveries")
        candidate["claims"][0]["value"] = 14.0
        self._assert_fallback(self._run(candidate))

    def test_evidence_ids_must_exactly_match_claim_ids(self):
        mutations = {
            "extra evidence id": lambda c: c["evidence_ids"].append(
                "ev-home-goals"
            ),
            "missing evidence id": lambda c: c["evidence_ids"].pop(),
            "duplicate evidence id": lambda c: c["evidence_ids"].append(
                c["evidence_ids"][0]
            ),
        }

        for name, mutate in mutations.items():
            with self.subTest(case=name):
                candidate = build_candidate_payload(
                    self.packet, "casual", "casual_form"
                )
                mutate(candidate)
                self._assert_fallback(self._run(candidate))

    def test_correct_numbers_with_unsupported_template_are_rejected(self):
        candidate = build_candidate_payload(
            self.packet, "casual", "casual_form"
        )
        candidate["template_id"] = "pressure_caused_goal"
        self._assert_fallback(self._run(candidate))

    def test_correct_numbers_with_free_text_interpretation_are_rejected(self):
        candidate = build_candidate_payload(
            self.packet, "casual", "casual_form"
        )
        candidate["explanation"] = "They scored because they pressed higher."
        self._assert_fallback(self._run(candidate))

    def test_invalid_responses_fall_back(self):
        valid = build_candidate_payload(
            self.packet, "casual", "casual_form"
        )

        missing_claims = copy.deepcopy(valid)
        missing_claims.pop("claims")

        wrong_field_type = copy.deepcopy(valid)
        wrong_field_type["claims"] = "not a list"

        wrong_mode = copy.deepcopy(valid)
        wrong_mode["audience_mode"] = "analyst"

        unknown_caveat = copy.deepcopy(valid)
        unknown_caveat["caveat_id"] = "confident"

        non_string_evidence_ids = copy.deepcopy(valid)
        non_string_evidence_ids["evidence_ids"] = [["not", "hashable"]]

        extra_claim_field = copy.deepcopy(valid)
        extra_claim_field["claims"][0]["interpretation"] = "unsupported"

        cases = {
            "malformed json": ("{not json", "invalid_json"),
            "json array": ("[]", "verification_failed"),
            "missing claims": (json.dumps(missing_claims), "verification_failed"),
            "wrong field type": (
                json.dumps(wrong_field_type),
                "verification_failed",
            ),
            "wrong mode": (json.dumps(wrong_mode), "verification_failed"),
            "unknown caveat": (
                json.dumps(unknown_caveat),
                "verification_failed",
            ),
            "non-string evidence id": (
                json.dumps(non_string_evidence_ids),
                "verification_failed",
            ),
            "extra claim field": (
                json.dumps(extra_claim_field),
                "verification_failed",
            ),
        }

        for name, (raw_response, reason) in cases.items():
            with self.subTest(case=name):
                result = generate_insight(
                    self.packet,
                    "casual",
                    ScriptedProvider(raw_response),
                )
                self._assert_fallback(result, reason=reason)

    def test_provider_exception_and_timeout_fall_back(self):
        cases = {
            "service error": (
                RuntimeError("service unavailable"),
                "service_error",
            ),
            "timeout": (TimeoutError("slow provider"), "timeout"),
        }

        for name, (error, reason) in cases.items():
            with self.subTest(case=name):
                result = generate_insight(
                    self.packet,
                    "casual",
                    FailingProvider(error),
                )
                self._assert_fallback(result, reason=reason)
                self.assertEqual(result["provider"], "mock-failing")

    def test_fallback_uses_only_verified_facts(self):
        result = generate_insight(
            self.packet,
            "casual",
            FailingProvider(RuntimeError("down")),
        )

        self.assertEqual(result["status"], "fallback")
        self.assertEqual(result["fallback_reason"], "service_error")
        self.assertIn("51.32", result["explanation"])
        self.assertIn("69.05", result["explanation"])
        self.assertIn("Northbridge FC", result["explanation"])
        self.assertEqual(audit_language(result["explanation"], self.packet.team_names), ())

        analyst = generate_insight(
            self.packet,
            "analyst",
            FailingProvider(RuntimeError("down")),
        )
        self.assertIn("29/42", analyst["explanation"])

    def test_numeric_audit_rejects_unsupported_numbers(self):
        shots = self.packet.fact("ev-home-shots")
        self.assertIsNotNone(shots)

        unsupported = audit_numeric_tokens(
            "Northbridge FC have taken 4 shots.",
            (shots,),
            self.packet.team_names,
        )
        self.assertTrue(unsupported)

        supported = audit_numeric_tokens(
            "Northbridge FC have taken 2 shots.",
            (shots,),
            self.packet.team_names,
        )
        self.assertEqual(supported, ())

        harmless_name_number = audit_numeric_tokens(
            "Northbridge FC 2 have taken 2 shots.",
            (shots,),
            ("Northbridge FC 2",),
        )
        self.assertEqual(harmless_name_number, ())

        wrong_metric_number = audit_numeric_tokens(
            "Northbridge FC had 51.32% possession.",
            (shots,),
            self.packet.team_names,
        )
        self.assertTrue(wrong_metric_number)

    def test_language_audit_rejects_unsupported_interpretations(self):
        unsupported_texts = (
            "They won because they pressed higher.",
            "He has a strong career record.",
            "Northbridge FC had more possession than Southbank FC.",
        )
        for text in unsupported_texts:
            with self.subTest(text=text):
                self.assertTrue(audit_language(text, self.packet.team_names))

        supported = audit_language(
            "Northbridge FC took 2 shots.",
            self.packet.team_names,
        )
        self.assertEqual(supported, ())


if __name__ == "__main__":
    unittest.main()
