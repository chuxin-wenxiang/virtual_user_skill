"""Source grouping preserves conflicting rows and never repairs a model claim."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import authentic_user as au
import source_registry as sr
import validation_prep as vp
import validation_workflow as vw
import test_validation_prep as fixtures


class SourceMapTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {'id': 'E001', 'kind': 'survey', 'date': '2025-01-01', 'industry': 'rental', 'score': 9, 'tags': ['车辆状况']},
            {'id': 'E002', 'kind': 'verbatim', 'date': '2025-01-01', 'industry': 'rental', 'score': 0, 'text': '车况不符合描述。'},
        ]

    def test_same_day_conflict_stays_in_separate_source_records(self):
        m = sr.record_map(self.rows)
        book = sr.lookup(self.rows)
        self.assertEqual(len(m['records']), 2)
        self.assertEqual([book[r['fields']['score']]['value'] for r in m['records']], [9, 0])
        for r in m['records']:
            self.assertTrue(all(book[ref]['evidence_id'] == r['evidence_id'] for ref in r['fields'].values()))
        self.assertNotIn(self.rows[1]['text'], json.dumps(m, ensure_ascii=False))

    def test_same_record_neighbours_do_not_become_selected_premises(self):
        book = sr.lookup(self.rows)
        ref = sr.record_map(self.rows)['records'][1]['fields']['score']
        atom = {'kind': 'topic_hypothesis', 'text': '可能关注退订费用。', 'confidence': 'low', 'condition': 'none', 'anchors': [{'ref': ref, 'quote': '0'}]}
        # This remains a semantic error for review, not a regex or metadata verdict.
        self.assertEqual([x['field'] for x in sr.check_atom(atom, book)], ['score'])
        self.assertEqual(sr.review_hints(atom, book)['semantic_verdict'], None)
        self.assertNotIn('text', {x['field'] for x in sr.check_atom(atom, book)})

    def test_historical_tag_summary_does_not_acquire_a_date_or_self_report(self):
        row = {'id': 'E001', 'kind': 'historical_tag_summary', 'industry': 'rental', 'tag': '费用', 'count': 2}
        m = sr.record_map([row])['records'][0]
        self.assertIsNone(m['date'])
        self.assertIsNone(m['source_record_sha256'])
        self.assertEqual(set(m['fields']), {'tag', 'count'})

    def test_new_bundle_checks_map_and_legacy_alpha9_still_loads(self):
        b = au.prepare(ROOT/'examples/profiles', 'demo-rich', '酒店体验', cutoff='2026-01-01')
        bad = copy.deepcopy(b)
        bad['source_map']['records'][0]['fields']['score'] = 'F999'
        bad['bundle_sha256'] = au.bundle_digest(bad)
        with self.assertRaises(au.InputError): au.validate_bundle(bad)
        legacy = copy.deepcopy(b)
        legacy['skill_version'] = '2027.0.0-alpha.9'
        del legacy['source_map']
        legacy['bundle_sha256'] = au.bundle_digest(legacy)
        au.validate_bundle(legacy)
        self.assertNotIn(sr.MAP_INSTRUCTIONS, au.render_prompt(legacy))

    def test_hidden_append_cannot_change_map_or_references(self):
        archive = au.read_object(ROOT/'examples/profiles/archives_v2027/demo-rich.json')
        rows = au.records_from(archive, au.date_value('2026-01-01'))
        before = sr.record_map(au.select_records(rows, '酒店体验', 24, 40000))
        archive['L2_attitude']['verbatims'].insert(0, {'date': '2027-01-01', 'industry': 'rental', 'score': 0, 'text': 'HIDDEN MAP SENTINEL'})
        after_rows = au.records_from(archive, au.date_value('2026-01-01'))
        self.assertEqual(before, sr.record_map(au.select_records(after_rows, '酒店体验', 24, 40000)))

    def test_host_interview_writes_bound_private_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)/'interview'
            au.create_interview(ROOT/'examples/profiles', 'demo-rich', '酒店体验', dest, cutoff='2026-01-01')
            b = au.read_object(dest/'evidence.json')
            self.assertEqual(au.read_object(dest/'source-map.json'), b['source_map'])
            self.assertEqual((dest/'source-map.json').stat().st_mode & 0o777, 0o600)

    def test_batch_inputs_share_mapping_rules_and_audit_detects_rehashed_wrong_map(self):
        fixture = fixtures.ValidationPreparationTests(); fixture.setUp()
        try:
            inputs, judges = fixture.root/'mapped-inputs', fixture.root/'mapped-judges'
            vp.build(fixture.profiles, inputs, judges, 1, response_protocol='atomic-bound-v4')
            _, manifest, protocol, _, prompts = vw.audit_inputs(inputs)
            with self.assertRaisesRegex(au.InputError, 'Legacy reframe'):
                vp.reframe(inputs, fixture.root/'legacy-reframe')
            self.assertFalse((fixture.root/'legacy-reframe').exists())
            self.assertEqual(protocol['source_map_protocol'], sr.MAP_VERSION)
            for row in prompts.values():
                context = row['payload']['user_context']
                self.assertEqual(context['source_map'], sr.record_map(context['evidence']))
            record = manifest['inputs'][0]
            path = inputs/record['path']
            header, payload = vw.decode_prompt(path.read_text())
            payload['user_context']['source_map']['records'][0]['fields']['score'] = 'F999'
            raw = header+json.dumps(payload, ensure_ascii=False)+'\n'
            path.write_text(raw)
            record['sha256'] = vw.text_digest(raw)
            (inputs/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(au.InputError, 'Source map'): vw.audit_inputs(inputs)
        finally: fixture.tearDown()


if __name__ == '__main__': unittest.main()
