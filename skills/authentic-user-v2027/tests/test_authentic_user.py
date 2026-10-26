"""Behavior checks on synthetic data; these are not simulation-effect experiments."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("authentic_user", ROOT / "scripts/authentic_user.py")
au = importlib.util.module_from_spec(spec)
spec.loader.exec_module(au)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for tier in ("archives_v2027", "archives_extended"):
            (self.root / tier).mkdir()
            for source in (ROOT / "examples/profiles" / tier).glob("*.json"):
                (self.root / tier / source.name).write_bytes(source.read_bytes())

    def tearDown(self):
        self.temp.cleanup()

    def read_rich(self):
        return json.loads((self.root / "archives_v2027/demo-rich.json").read_text())

    def save_rich(self, data):
        (self.root / "archives_v2027/demo-rich.json").write_text(json.dumps(data), encoding="utf-8")

    def bundle(self, **kwargs):
        return au.prepare(self.root, "demo-rich", "酒店退改和价格透明，你更在意什么？", cutoff="2026-01-01", **kwargs)

    def answer(self):
        return json.loads((ROOT / "examples/answer-demo.json").read_text())

    def test_cutoff_excludes_hidden_and_full_history_derivatives(self):
        bundle = self.bundle()
        text = au.canonical(bundle)
        for marker in ("HIDDEN_DEMO", "DO_NOT_USE", "buyer_nick", '"age"', '"buyer_id"'):
            self.assertNotIn(marker, text)
        self.assertEqual(len(bundle["evidence"]), 6)
        self.assertEqual(bundle["derived_summary"]["avg_score"], 7.667)
        self.assertEqual(bundle["capability"]["level"], "individual_memory")

    def test_appending_hidden_records_cannot_change_any_bundle_field(self):
        before = self.bundle()
        data = self.read_rich()
        data["L2_attitude"]["nps_history"].insert(0, {
            "date": "2026-06-01", "industry": "domestic_hotel", "score": 0, "tags": ["SECRET"]})
        data["L2_attitude"]["verbatims"].insert(0, {
            "date": "2026-06-01", "industry": "domestic_hotel", "score": 0, "text": "SECRET FUTURE"})
        data["L1_facts"]["demographics"] = {"age": 20, "buyer_nick": "SECRET"}
        data["L3_personality"] = {"traits": "SECRET"}
        self.save_rich(data)
        self.assertEqual(before, self.bundle())

    def test_boundary_is_exclusive_and_timezone_aware(self):
        self.assertEqual(len(au.prepare(self.root, "demo-rich", "体验", cutoff="2025-01-10T02:00:00Z")["evidence"]), 0)
        after = au.prepare(self.root, "demo-rich", "体验", cutoff="2025-01-10T02:00:01Z")
        self.assertEqual(len(after["evidence"]), 2)
        self.assertEqual(len(au.prepare(self.root, "demo-rich", "体验", cutoff="2025-01-10")["evidence"]), 0)

    def test_zero_is_valid_and_sparse_users_do_not_get_personalities(self):
        bundle = au.prepare(self.root, "demo-sparse", "火车票体验")
        self.assertEqual(bundle["source_tier"], "extended")
        self.assertEqual(bundle["derived_summary"]["avg_score"], 4)
        self.assertEqual(bundle["derived_summary"]["first_score"], 0)
        self.assertEqual(bundle["capability"]["level"], "facts_only")
        self.assertNotIn("L3_personality", bundle)

    def test_unknown_date_and_corrupt_industry_are_excluded(self):
        data = self.read_rich()
        for date, industry in (("unknown", "domestic_hotel"), ("2025-01-01", ["broken"])):
            data["L2_attitude"]["verbatims"].append({"date": date, "industry": industry, "text": "SECRET UNDATED"})
        self.save_rich(data)
        self.assertNotIn("SECRET UNDATED", au.canonical(self.bundle()))

    def test_industry_filter_has_no_cross_industry_evidence(self):
        data = self.read_rich()
        data["L2_attitude"]["nps_history"].append({"date": "2025-07-01", "industry": "train", "score": 1, "tags": []})
        self.save_rich(data)
        bundle = self.bundle(industry="domestic_hotel")
        self.assertTrue(all(row["industry"] == "domestic_hotel" for row in bundle["evidence"]))
        empty = self.bundle(industry="rental")
        self.assertEqual(empty["capability"]["level"], "insufficient")

    def test_invalid_scores_do_not_bias_mean_or_become_zero(self):
        data = self.read_rich()
        rows = data["L2_attitude"]["nps_history"]
        for index, bad in enumerate((True, -1, 11, "8.5", "NaN")):
            rows.append({"date": f"2025-08-{index + 1:02d}", "industry": "domestic_hotel", "score": bad, "tags": ["有来源的标签"]})
        self.save_rich(data)
        bundle = self.bundle()
        self.assertEqual(bundle["derived_summary"]["scored_survey_records"], 3)
        self.assertEqual(bundle["derived_summary"]["avg_score"], 7.667)

    def test_duplicate_records_are_not_double_counted(self):
        data = self.read_rich()
        data["L2_attitude"]["nps_history"].append(copy.deepcopy(data["L2_attitude"]["nps_history"][0]))
        data["L2_attitude"]["verbatims"].append(copy.deepcopy(data["L2_attitude"]["verbatims"][0]))
        self.save_rich(data)
        self.assertEqual(self.bundle()["capability"]["survey_records"], 3)
        self.assertEqual(self.bundle()["capability"]["verbatim_records"], 3)

    def test_l1_history_fallback(self):
        data = self.read_rich()
        data["L1_facts"]["nps_history"] = data["L2_attitude"].pop("nps_history")
        self.save_rich(data)
        bundle = self.bundle()
        self.assertEqual(bundle["derived_summary"]["avg_score"], 7.667)
        self.assertTrue(any(row["source_field"] == "L1_facts.nps_history" for row in bundle["evidence"]))

    def test_unknown_user_and_path_traversal_fail_without_fallback(self):
        for identity in ("nonexistent", "../demo-rich", "/etc/passwd"):
            with self.assertRaises(au.InputError):
                au.prepare(self.root, identity, "问题")

    def test_mismatched_user_and_malformed_archive_fail(self):
        data = self.read_rich()
        data["buyer_id"] = "another-user"
        self.save_rich(data)
        with self.assertRaises(au.InputError):
            self.bundle()
        (self.root / "archives_v2027/demo-rich.json").write_text("not json")
        with self.assertRaises(au.InputError):
            self.bundle()

    def test_symlink_outside_archive_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as external:
            source = Path(external) / "demo-other.json"
            source.write_text('{"buyer_id":"demo-other"}')
            (self.root / "archives_v2027/demo-other.json").symlink_to(source)
            with self.assertRaises(au.InputError):
                au.prepare(self.root, "demo-other", "问题")

    def test_selection_limit_and_budget_are_respected(self):
        bundle = self.bundle(max_records=2)
        self.assertEqual(len(bundle["evidence"]), 2)
        short = self.bundle(max_chars=500)
        cost = sum(len(au.canonical({k: v for k, v in r.items() if k != "id"})) for r in short["evidence"])
        self.assertLessEqual(cost, 500)
        self.assertEqual(au.validate_bundle(short), short)

    def test_known_protocol_answer_passes_mechanical_checks(self):
        result = au.check_answer(self.bundle(), self.answer())
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["semantic_review_required"])

    def test_unknown_refs_and_fabricated_quotes_are_rejected(self):
        answer = self.answer()
        answer["claims"][0]["evidence_ids"] = ["E999"]
        answer["quotes"][0]["text"] = "我已经投诉并获得赔付"
        answer["answer"] += "[E998]"
        result = au.check_answer(self.bundle(), answer)
        self.assertFalse(result["ok"])
        self.assertEqual(len(result["errors"]), 3)

    def test_unsupported_high_confidence_inference_is_rejected(self):
        answer = self.answer()
        answer["claims"][-1]["confidence"] = "high"
        self.assertFalse(au.check_answer(self.bundle(), answer)["ok"])

    def test_facts_only_and_empty_bundle_cannot_simulate(self):
        sparse = au.prepare(self.root, "demo-sparse", "问题")
        self.assertFalse(au.check_answer(sparse, self.answer())["ok"])
        empty = self.bundle(industry="rental")
        self.assertFalse(au.check_answer(empty, self.answer())["ok"])
        unknown = {"answer_mode": "insufficient_evidence", "answer": "证据不足，无法模拟。",
                   "claims": [], "quotes": [], "unknowns": ["没有符合条件的租车记录"]}
        self.assertTrue(au.check_answer(empty, unknown)["ok"])

    def test_checksum_detects_edited_bundle(self):
        bundle = self.bundle()
        bundle["evidence"][0]["score"] = 10
        with self.assertRaises(au.InputError):
            au.render_prompt(bundle)

    def test_rehashed_cutoff_violation_still_fails(self):
        bundle = self.bundle()
        bundle["evidence"][0]["date"] = "2027-01-01T00:00:00+08:00"
        bundle["bundle_sha256"] = au.bundle_digest(bundle)
        with self.assertRaises(au.InputError):
            au.validate_bundle(bundle)

    def test_existing_output_is_preserved_and_private_permissions_used(self):
        path = self.root / "output.json"
        au.write_new(str(path), "first")
        with self.assertRaises(au.InputError):
            au.write_new(str(path), "second")
        self.assertEqual(path.read_text(), "first")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_cli_prepare_prompt_and_check_complete(self):
        script = str(ROOT / "scripts/authentic_user.py")
        bundle = self.root / "memory.json"
        prompt = self.root / "prompt.txt"
        commands = [
            ["doctor", "--profiles-dir", str(self.root)],
            ["prepare", "--profiles-dir", str(self.root), "--buyer-id", "demo-rich", "--question", "问题",
             "--cutoff", "2026-01-01", "--output", str(bundle)],
            ["prompt", "--bundle", str(bundle), "--output", str(prompt)],
            ["check-answer", "--bundle", str(bundle), "--answer", str(ROOT / "examples/answer-demo.json")],
        ]
        for command in commands:
            proc = subprocess.run([sys.executable, script, *command], text=True, capture_output=True)
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("BEGIN_UNTRUSTED_EVIDENCE_JSON", prompt.read_text())
        self.assertNotIn("HIDDEN_DEMO", prompt.read_text())


if __name__ == "__main__":
    unittest.main()
