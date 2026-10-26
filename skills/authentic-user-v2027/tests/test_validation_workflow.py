"""Full lifecycle checks with synthetic responses and grades, never real model results."""

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
import validation_workflow as vw
import test_validation_prep as fixtures


class ValidationWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ValidationPreparationTests()
        self.fixture.setUp()
        self.root = self.fixture.root
        self.inputs, self.judges = self.root / "inputs", self.root / "judge"
        vp.build(self.fixture.profiles, self.inputs, self.judges, per_group=1, repeats=2)
        self.config_file, self.review_file = self.root / "config.json", self.root / "review.json"
        self.config = au.read_object(ROOT / "examples/model-config.synthetic.json")
        self.config_file.write_text(json.dumps(self.config))
        _, manifest, _, calls, _ = vw.audit_inputs(self.inputs)
        review = {"inputs_manifest_sha256": vw.digest(manifest), "reviewer": "synthetic-test",
                  "cases": {case: {"status": "reviewed", "unsupported_parts": ["synthetic amount not recorded"]}
                            for case in {c["case"] for c in calls}}}
        self.review_file.write_text(json.dumps(review))
        self.run_dir = self.root / "run"

    def tearDown(self):
        self.fixture.tearDown()

    def freeze(self):
        return vw.freeze(self.inputs, self.config_file, self.review_file, self.run_dir)

    def response(self, run, call, prompts):
        rows = prompts[call["prompt"]]["payload"]["user_context"]["evidence"]
        ref = rows[0]["id"] if rows else None
        answer = {"answer": f"AI 模拟：这是合成测试断言。[{ref}]" if ref else "AI 模拟：资料不足。",
                  "direction": "unknown", "claims": [{"text": "合成测试断言", "kind": "inference",
                                                       "evidence_ids": [ref], "confidence": "low"}] if ref else [],
                  "unknowns": ["合成测试未知项"]}
        return {"call_id": vw.call_id(call), "run_sha256": run["run_sha256"],
                "prompt_sha256": call["prompt_sha256"], "model_config_sha256": run["model_config_sha256"],
                "origin": "synthetic_test", "provider_request_id": None,
                "model": self.config["model"], "revision": self.config["revision"],
                "seed": None, "usage": {"input_tokens": 100, "output_tokens": 30}, "answer": answer}

    def fill_responses(self):
        self.freeze()
        _, run, calls, prompts = vw.load_run(self.run_dir)
        for call in calls.values():
            response = self.response(run, call, prompts)
            file = self.root / "incoming.json"
            file.write_text(json.dumps(response))
            vw.ingest(self.run_dir, file)
        return run

    def test_audit_checks_full_grid_and_identical_templates(self):
        _, manifest, _, calls, _ = vw.audit_inputs(self.inputs)
        self.assertEqual(manifest["users"], 4)
        self.assertEqual(len(calls), 64)
        first = self.inputs / "calls.jsonl"
        lines = first.read_text().splitlines()
        first.write_text("\n".join(lines + [lines[0]]) + "\n")
        with self.assertRaises(au.InputError):
            vw.audit_inputs(self.inputs)

    def test_input_tampering_is_detected(self):
        path = next(self.inputs.glob("S*/X/Q1.txt"))
        path.write_text(path.read_text() + "extra")
        with self.assertRaises(au.InputError):
            vw.audit_inputs(self.inputs)

    def test_templates_do_not_claim_review_or_freeze(self):
        result = vw.templates(self.inputs, self.root / "templates")
        self.assertEqual(result["status"], "templates_only_not_frozen")
        review = au.read_object(self.root / "templates/visible-review.template.json")
        self.assertTrue(all(row["status"] == "needs_review" for row in review["cases"].values()))
        with self.assertRaises(au.InputError):
            vw.freeze(self.inputs, self.root / "templates/model-config.template.json", self.review_file, self.run_dir)

    def test_freeze_rejects_mutable_revision_and_unreviewed_unknown_scope(self):
        bad = copy.deepcopy(self.config)
        bad["revision"] = "latest"
        self.config_file.write_text(json.dumps(bad))
        with self.assertRaises(au.InputError):
            self.freeze()
        self.config_file.write_text(json.dumps(self.config))
        review = au.read_object(self.review_file)
        next(iter(review["cases"].values()))["status"] = "needs_review"
        self.review_file.write_text(json.dumps(review))
        with self.assertRaises(au.InputError):
            self.freeze()

    def test_frozen_run_binds_inputs_and_records_zero_automatic_calls(self):
        result = self.freeze()
        self.assertEqual(result["automatic_model_calls"], 0)
        self.assertEqual(vw.status(self.run_dir)["missing_responses"], 64)
        protocol = au.read_object(self.inputs / "protocol.json")
        protocol["status"] = "changed"
        (self.inputs / "protocol.json").write_text(json.dumps(protocol))
        with self.assertRaises(au.InputError):
            vw.status(self.run_dir)

    def test_cross_run_response_and_wrong_seed_are_rejected(self):
        self.freeze()
        _, run, calls, prompts = vw.load_run(self.run_dir)
        response = self.response(run, next(iter(calls.values())), prompts)
        response["run_sha256"] = "wrong"
        with self.assertRaises(au.InputError):
            vw.validate_response(run, calls, prompts, response)
        response["run_sha256"] = run["run_sha256"]
        response["seed"] = 42
        with self.assertRaises(au.InputError):
            vw.validate_response(run, calls, prompts, response)

    def test_synthetic_config_cannot_claim_provider_execution(self):
        self.freeze()
        _, run, calls, prompts = vw.load_run(self.run_dir)
        response = self.response(run, next(iter(calls.values())), prompts)
        response.update(origin="provider_response", provider_request_id="not-a-real-request")
        with self.assertRaises(au.InputError):
            vw.validate_response(run, calls, prompts, response)

    def test_import_rejects_unknown_evidence_over_budget_and_duplicate(self):
        self.freeze()
        _, run, calls, prompts = vw.load_run(self.run_dir)
        response = self.response(run, next(iter(calls.values())), prompts)
        bad = copy.deepcopy(response)
        bad["answer"]["claims"][0]["evidence_ids"] = ["E999"]
        with self.assertRaises(au.InputError):
            vw.validate_response(run, calls, prompts, bad)
        bad = copy.deepcopy(response)
        bad["usage"]["input_tokens"] = 999999
        with self.assertRaises(au.InputError):
            vw.validate_response(run, calls, prompts, bad)
        path = self.root / "incoming.json"
        path.write_text(json.dumps(response))
        vw.ingest(self.run_dir, path)
        with self.assertRaises(au.InputError):
            vw.ingest(self.run_dir, path)

    def test_incomplete_or_synthetic_runs_cannot_be_silently_exported(self):
        self.freeze()
        with self.assertRaises(au.InputError):
            vw.blind(self.run_dir, self.judges, self.root / "review")

    def test_hidden_judge_integrity_is_checked(self):
        self.freeze()
        _, run, _, _ = vw.load_run(self.run_dir)
        path = next(self.judges.glob("S*.json"))
        path.write_text(path.read_text() + " ")
        with self.assertRaises(au.InputError):
            vw.load_judges(self.judges, run)

    def test_full_synthetic_lifecycle_and_user_paired_summary(self):
        self.fill_responses()
        status = vw.status(self.run_dir)
        self.assertEqual(status["synthetic_test_imports"], 64)
        self.assertEqual(status["provider_response_imports"], 0)
        with self.assertRaises(au.InputError):
            vw.blind(self.run_dir, self.judges, self.root / "review")
        vw.blind(self.run_dir, self.judges, self.root / "review", allow_synthetic=True)
        pack = au.read_object(self.root / "review/review-pack.json")
        for entry in pack["tasks"]:
            row = au.read_object(self.root / "review" / entry["path"])
            self.assertNotIn("case", row)
            self.assertNotIn("condition", row)
            self.assertNotIn("buyer_id", row["hidden_reference"])
        key = au.read_object(self.run_dir / "review-key.json")
        grades = au.read_object(self.root / "review/scores.template.json")
        grades.update(reviewer="synthetic-test", origin="synthetic_test")
        for row in grades["scores"]:
            row["status"] = "scored"
            meta = key["reviews"][row["review_id"]]
            value = 0.75 if meta["condition"] == "individual_memory" else 0.25
            for metric in vw.METRICS:
                target = {"attitude_direction": "Q2", "theme_overlap": "Q3", "unknown_restraint": "Q4"}.get(metric)
                row["scores"][metric] = value if not target or target == meta["question_id"] else None
                if metric == "theme_overlap" and target == meta["question_id"]:
                    row["scores"][metric] = 1 if meta["condition"] == "individual_memory" else 0
                if metric in ("attitude_direction", "unknown_restraint") and target == meta["question_id"]:
                    row["scores"][metric] = 1 if meta["condition"] == "individual_memory" else 0
                if metric == "fabricated_experience_rate":
                    row["scores"][metric] = 0 if meta["condition"] == "individual_memory" else 1
        for row in grades["repeat_scores"]:
            row.update(status="scored", score=1)
        score_file = self.root / "scores.json"
        score_file.write_text(json.dumps(grades))
        report = vw.summarize(self.run_dir, score_file)
        self.assertEqual(report["status"], "scored_exploratory")
        self.assertTrue(report["synthetic_present"])
        self.assertFalse(report["provider_verified"])
        self.assertEqual(report["metrics"]["fact_accuracy"]["paired_users"], 4)
        self.assertEqual(report["metrics"]["fact_accuracy"]["difference_pp"], 50)
        grades["scores"][0]["status"] = "unscored"
        score_file.write_text(json.dumps(grades))
        self.assertEqual(vw.summarize(self.run_dir, score_file)["status"], "partial_scores")
        task_file = self.root / "review" / pack["tasks"][0]["path"]
        task_file.write_text(task_file.read_text() + " ")
        with self.assertRaises(au.InputError):
            vw.summarize(self.run_dir, score_file)

    def test_overlap_and_parent_paths_are_rejected(self):
        with self.assertRaises(au.InputError):
            vw.safe_path(self.root, "../elsewhere")
        with self.assertRaises(au.InputError):
            vw.safe_path(self.root, "/tmp/elsewhere")

    def test_temporal_audit_checks_hidden_manifest_and_cutoff(self):
        result = vw.audit(self.inputs, self.judges)
        self.assertEqual(result["time_boundary_violations"], 0)
        path = next(self.judges.glob("S*.json"))
        hidden = au.read_object(path)
        hidden["cutoff_exclusive"] = hidden["holdout"]["date"] = "2025-01-01T00:00:00+08:00"
        path.write_text(json.dumps(hidden))
        manifest = au.read_object(self.judges / "manifest.json")
        for record in manifest["case_files"]:
            if record["path"] == path.name:
                record["sha256"] = vw.hashlib.sha256(path.read_bytes()).hexdigest()
        (self.judges / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaises(au.InputError):
            vw.audit(self.inputs, self.judges)


if __name__ == "__main__":
    unittest.main()
