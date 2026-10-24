import copy
import json
import unittest
from pathlib import Path

from simulator.generate import validate
from simulator.statistics import calculate_statistics
from simulator.xg import XGAccumulator, shot_xg


class ExpectedGoalsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = Path('data/examples/xg-match')
        cls.metadata = json.loads((base/'metadata.json').read_text(encoding='utf-8'))
        cls.events = [json.loads(s) for s in (base/'events.jsonl').read_text(encoding='utf-8').splitlines()]
        cls.roster = {p['player_id']:p for p in cls.metadata['players']}
        cls.shot = next(e for e in cls.events if e['type']=='shot')

    def test_every_generated_shot_matches_evidence(self):
        validate(self.metadata,self.events)
        for e in self.events:
            if e['type']=='shot':
                self.assertEqual(e['xg'],shot_xg(e,self.roster))
                self.assertTrue(0 < e['xg']['value'] < 1)

    def test_no_outcome_or_speed_leakage(self):
        changed=copy.deepcopy(self.shot)
        changed.update(outcome='goal',outcome_reason='goal',shot_speed={'kmh':999},kick_effort=0,end={'x_m':0,'y_m':0},shooting_skill=1)
        self.assertEqual(shot_xg(self.shot,self.roster),shot_xg(changed,self.roster))

    def test_distance_angle_and_defender_effects(self):
        e=copy.deepcopy(self.shot)
        e.update(team_id='home',period=1,set_piece_type=None,start={'x_m':94,'y_m':34},goalkeeper_id='away-01')
        e['pitch_snapshot']['players']={'away-01':{'x_m':104,'y_m':34}}
        close=shot_xg(e,self.roster)['value']
        e['start']['x_m']=75
        self.assertLess(shot_xg(e,self.roster)['value'],close)
        e['start']={'x_m':94,'y_m':60}
        self.assertLess(shot_xg(e,self.roster)['value'],close)
        e['start']={'x_m':94,'y_m':34}
        e['pitch_snapshot']['players']['away-02']={'x_m':95,'y_m':34}
        self.assertLess(shot_xg(e,self.roster)['value'],close)

    def test_direction_symmetry(self):
        e=copy.deepcopy(self.shot)
        value=shot_xg(e,self.roster)['value']
        e['period']=3-e['period']
        e['start']['x_m']=105-e['start']['x_m']
        for p in e['pitch_snapshot']['players'].values():p['x_m']=105-p['x_m']
        self.assertEqual(value,shot_xg(e,self.roster)['value'])

    def test_penalty_and_missing_coverage(self):
        e=copy.deepcopy(self.shot);e['set_piece_type']='penalty'
        a=XGAccumulator();a.add(e,self.roster)
        self.assertEqual(a.summary(0,0)['xg'],.76)
        self.assertEqual(a.summary(0,0)['non_penalty_xg'],0)
        a.add({'type':'shot'},self.roster)
        self.assertIsNone(a.summary(0,0)['xg'])
        self.assertEqual(a.summary(0,0)['xg_coverage']['shots_without_xg'],1)

    def test_derived_ratio_ties_use_the_browser_rounding_contract(self):
        a=XGAccumulator()
        a.shots=a.known=2
        a.units=62367
        self.assertEqual(a.summary(0,0)['xg_per_shot'],.031184)

    def test_team_player_sums_and_prefix(self):
        result=calculate_statistics(self.metadata,self.events)
        players=result['players']
        for team,s in result['teams'].items():
            for key in ('xg','non_penalty_xg','xg_assisted'):
                self.assertAlmostEqual(s[key],sum(p[key] for p in players.values() if p['team_id']==team),places=6)
        prefix=[e for e in self.events if e['sequence'] < self.shot['sequence']]
        self.assertEqual(calculate_statistics(self.metadata,prefix)['teams'][self.shot['team_id']]['xg'],0)
        invalid=copy.deepcopy(self.events)
        for e in invalid:
            if e['type']=='shot':e['valid_for_statistics']=False
        self.assertTrue(all(t['xg']==0 for t in calculate_statistics(self.metadata,invalid)['teams'].values()))

    def test_tampered_values_rejected(self):
        stream=copy.deepcopy(self.events)
        next(e for e in stream if e['type']=='shot')['xg']['value']=.999
        with self.assertRaisesRegex(ValueError,'xG'):validate(self.metadata,stream)

    def test_legacy_backfill_does_not_mutate(self):
        stream=copy.deepcopy(self.events)
        for e in stream:e.pop('xg',None)
        before=copy.deepcopy(stream)
        self.assertEqual(calculate_statistics(self.metadata,stream)['teams'],calculate_statistics(self.metadata,self.events)['teams'])
        self.assertEqual(stream,before)


if __name__=='__main__':unittest.main()

