"""Context preservation under a small budget, without asserting event identity."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import authentic_user as au
import record_selection as rs


class RecordSelectionTests(unittest.TestCase):
    def rows(self, conflict=False):
        survey = [{'date': '2025-01-01', 'industry': 'rental', 'score': 8, 'tags': []},
                  {'date': '2025-03-01', 'industry': 'rental', 'score': 0, 'tags': ['服务']}]
        if conflict: survey.append({'date': '2025-03-01', 'industry': 'rental', 'score': 9, 'tags': ['车辆']})
        archive = {'L2_attitude': {'nps_history': survey, 'verbatims': [
            {'date': '2025-01-02', 'industry': 'rental', 'score': 8, 'text': '价格透明，但其他费用不清楚。'},
            {'date': '2025-01-03', 'industry': 'rental', 'score': 8, 'text': '价格透明，预订过程直接。'},
            {'date': '2025-04-01', 'industry': 'rental', 'score': 1, 'text': '接待有待改进。'}]}}
        return au.records_from(archive)

    def test_new_policy_keeps_query_anchor_and_recent_zero_survey(self):
        rows = self.rows()
        legacy = au.select_records(rows, '价格透明', 2, 40000)
        selected, audit = rs.select(rows, '价格透明', 2, 40000)
        self.assertTrue(all(r['kind'] == 'verbatim' for r in legacy))
        self.assertTrue(any(r['kind'] == 'verbatim' and '价格透明' in r['text'] for r in selected))
        self.assertTrue(any(r['kind'] == 'survey' and r['score'] == 0 for r in selected))
        self.assertEqual(audit['latest_survey_context']['status'], 'selected')

    def test_same_time_conflicting_surveys_kept_as_separate_records(self):
        selected, audit = rs.select(self.rows(True), '价格透明', 3, 40000)
        last = [r for r in selected if r['kind'] == 'survey' and r['date'].startswith('2025-03-01')]
        self.assertEqual({r['score'] for r in last}, {0, 9})
        self.assertEqual(len(audit['latest_survey_context']['selected_evidence_ids']), 2)
        self.assertEqual(len({r['source_record_sha256'] for r in last}), 2)

    def test_conflicting_latest_scores_do_not_become_one_summary_value(self):
        selected,_=rs.select(self.rows(True),'价格透明',3,40000)
        self.assertIsNone(au.summarize(selected,resolve_score_ties=True)[1]['latest_score'])
        self.assertEqual(au.summarize(selected,resolve_score_ties=True)[1]['scored_survey_records'],2)
        self.assertEqual({r['score'] for r in selected if r['kind']=='survey'},{0,9})

    def test_conflict_group_does_not_become_an_arbitrary_last_score_when_budget_is_small(self):
        selected, audit = rs.select(self.rows(True), '价格透明', 2, 40000)
        self.assertEqual(audit['latest_survey_context']['status'], 'budget_excluded')
        self.assertEqual(audit['latest_survey_context']['selected_evidence_ids'], [])
        self.assertFalse(any(r['kind'] == 'survey' and r['date'].startswith('2025-03-01') for r in selected))

    def test_top_survey_tie_is_atomic_for_selection_but_not_merged(self):
        rows = [r for r in self.rows(True) if r['kind'] == 'survey']
        chosen, _ = rs.select(rows, '车辆', 1, 40000)
        self.assertFalse(any(r['date'].startswith('2025-03-01') for r in chosen))
        self.assertLessEqual(len(chosen), 1)

    def test_character_budget_skips_whole_text_without_truncation(self):
        rows = self.rows()
        rows[2] = dict(rows[2], text='价格透明'*1000, source_record_sha256='oversize-synthetic')
        chosen, audit = rs.select(rows, '价格透明', 4, 500)
        self.assertLessEqual(sum(len(au.canonical({k:v for k,v in r.items() if k!='id'})) for r in chosen), 500)
        self.assertEqual(audit['selected_records'], len(chosen))
        self.assertFalse(any(r['source_record_sha256'] == 'oversize-synthetic' for r in chosen))

    def test_input_permutation_preserves_selected_bytes_and_does_not_mutate_sources(self):
        rows = self.rows(True); before = copy.deepcopy(rows)
        a = rs.select(rows, '价格透明', 3, 40000)
        b = rs.select(list(reversed(rows)), '价格透明', 3, 40000)
        self.assertEqual(a, b); self.assertEqual(rows, before)
        self.assertTrue(all('id' not in r for r in rows))

    def test_latest_context_is_from_anchor_industry(self):
        rows = self.rows()
        extra = au.records_from({'L2_attitude': {'nps_history': [{'date':'2025-12-01','industry':'train','score':10,'tags':[]} ]}})
        chosen, audit = rs.select(rows+extra, '价格透明', 2, 40000)
        self.assertEqual(audit['latest_survey_context']['industry'], 'rental')
        self.assertTrue(all(r['industry']=='rental' for r in chosen))

    def test_empty_pool_and_all_oversize_do_not_fabricate_evidence(self):
        self.assertEqual(rs.select([], '问题', 2, 500)[0], [])
        self.assertEqual(rs.select(self.rows(), '问题', 2, 1)[0], [])

    def test_rehashed_bad_selection_budget_or_context_refs_are_rejected(self):
        b = au.prepare(ROOT/'examples/profiles', 'demo-rich', '酒店体验', cutoff='2026-01-01')
        for mutate in (lambda x:x['selection'].update(max_records=0),
                       lambda x:x['selection']['context_audit'].update(selected_records=999),
                       lambda x:x['selection']['context_audit']['latest_survey_context'].update(selected_evidence_ids=['E999'])):
            bad = copy.deepcopy(b); mutate(bad); bad['bundle_sha256']=au.bundle_digest(bad)
            with self.assertRaises(au.InputError): au.validate_bundle(bad)

    def test_alpha10_map_requirement_and_capability_are_not_dropped(self):
        b = au.prepare(ROOT/'examples/profiles', 'demo-rich', '酒店体验', cutoff='2026-01-01')
        b['skill_version']='2027.0.0-alpha.10'; b['bundle_sha256']=au.bundle_digest(b)
        au.validate_bundle(b)
        del b['source_map']; b['bundle_sha256']=au.bundle_digest(b)
        with self.assertRaises(au.InputError): au.validate_bundle(b)


if __name__=='__main__': unittest.main()
