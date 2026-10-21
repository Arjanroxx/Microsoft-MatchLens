"""Local demonstration provider.

This is not a real AI model. It is a deterministic stand-in that exercises the
same structured response contract a future Microsoft AI Foundry provider will
use. It makes no network calls and needs no credentials.
"""
from __future__ import annotations

import json

from .evidence import EvidencePacket
from .narrative import build_candidate_payload, choose_template


class LocalDemoProvider:
    """Deterministic local demo/test provider; not an AI model."""

    name = "local-demo"

    def __init__(self, packet: EvidencePacket, audience_mode: str):
        self.packet = packet
        self.audience_mode = audience_mode

    def generate(self, prompt: str) -> str:
        """Return a strict candidate for the best available reviewed template."""
        del prompt  # The local provider works from the packet, not a model prompt.
        template_id = choose_template(self.packet, self.audience_mode)
        candidate = build_candidate_payload(
            self.packet, self.audience_mode, template_id
        )
        return json.dumps(candidate, separators=(",", ":"))
