"""Synthetic holdout-preparation tests, not model evaluation results."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import authentic_user as au
import validation_prep as vp


class ValidationPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.profiles = self.root / "profiles"
        (self.profiles / "archives_v2027").mkdir(parents=True)
        base = json.loads((ROOT / "examples/profiles/archives_v2027/demo-rich.json").read_text())
        base["L2_attitude"]["nps_history"].append({"date": "2025-02-01", "industry": "domestic_hotel", "score": 8, "tags": ["合成标签"]})
        for group in ("promoter", "nonpromoter", "transition", "complex"):
            for index in range(2):
                obj = copy.deepcopy(base)
                obj["buyer_id"] = f"demo-{group}-{index}"
                for row in obj["L2_attitude"]["nps_history"] + obj["L2_attitude"]["verbatims"]:
                    row["score"] = 5 if group == "nonpromoter" else 9
                    if row["date"].startswith("2026-") and group == "transition":
                        row["score"] = 2
                if group == "complex":
                    obj["L2_attitude"]["nps_history"].append({"date": "2025-06-01", "industry": "train", "score": 8, "tags": []})
                (self.profiles / "archives_v2027" / f'{obj["buyer_id"]}.json').write_text(json.dumps(obj), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_strict_candidates_and_quotas_use_distinct_users(self):
        candidates, summary = vp.scan(self.profiles)
        self.assertEqual(summary["strict_candidates"], 8)
        selected = vp.choose(candidates, 2)
        self.assertEqual(len({c["buyer_id"] for _, c in selected}), 8)
        self.assertEqual(sorted(g for g, _ in selected), sorted(["transition", "stable_nonpromoter", "complex", "stable_promoter"] * 2))

    def test_shared_inputs_exclude_holdout_identity_and_condition_map(self):
        inputs, judge = self.root / "inputs", self.root / "judge"
        result = vp.build(self.profiles, inputs, judge, per_group=1, repeats=2)
        self.assertEqual(result["users"], 4)
        self.assertEqual(result["unique_prompts"], 32)
        self.assertEqual(result["planned_calls"], 64)
        self.assertEqual(result["model_calls_completed"], 0)
        all_inputs = "\n".join(p.read_text() for p in inputs.rglob("*") if p.is_file())
        for token in ("HIDDEN_DEMO", "buyer_id", "condition_map", "hidden_segment", "demo-transition"):
            self.assertNotIn(token, all_inputs)
        self.assertIn("HIDDEN_DEMO", "\n".join(p.read_text() for p in judge.glob("S*.json")))
        manifest = au.read_object(inputs / "manifest.json")
        for record in manifest["inputs"]:
            self.assertEqual(vp.hashlib.sha256((inputs / record["path"]).read_bytes()).hexdigest(), record["sha256"])
        self.assertFalse((inputs / "answers").exists())

    def test_zero_exclusion_is_pilot_option_not_runtime_policy(self):
        source = next((self.profiles / "archives_v2027").glob("demo-transition-*.json"))
        obj = json.loads(source.read_text())
        for row in obj["L2_attitude"]["verbatims"]:
            if row["date"].startswith("2026-"):
                row["score"] = 0
        excluded = vp.candidate_from(obj, obj["buyer_id"], include_zero=False)
        included = vp.candidate_from(obj, obj["buyer_id"], include_zero=True)
        self.assertIsNone(excluded)
        self.assertEqual(included["holdout"]["score"], 0)

    def test_output_overlap_and_reuse_are_rejected(self):
        with self.assertRaises(au.InputError):
            vp.build(self.profiles, self.root / "inputs", self.root / "inputs/judge", 1)
        vp.build(self.profiles, self.root / "inputs", self.root / "judge", 1)
        with self.assertRaises(au.InputError):
            vp.build(self.profiles, self.root / "inputs", self.root / "judge", 1)

    def test_historical_tag_baseline_contains_no_quotes_or_scores(self):
        obj = au.read_object(next((self.profiles / "archives_v2027").glob("*.json")))
        rows = au.records_from(obj, au.date_value("2026-01-01"))
        baseline = vp.baseline_tags(rows)
        self.assertTrue(baseline)
        self.assertTrue(all(set(row) == {"id", "kind", "industry", "tag", "count"} for row in baseline))
        self.assertNotIn("HIDDEN_DEMO", au.canonical(baseline))

    def test_selection_audit_does_not_change_default_candidates(self):
        before, _ = vp.scan(self.profiles)
        result = vp.audit_selection(self.profiles)
        after, _ = vp.scan(self.profiles)
        self.assertEqual(before, after)
        self.assertEqual(result["candidate_counts"]["visible_only"], len(before))
        self.assertFalse(result["historical_implementation_available"])


if __name__ == "__main__":
    unittest.main()
