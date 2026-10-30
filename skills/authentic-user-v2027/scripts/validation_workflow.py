#!/usr/bin/env python3
"""Audit, freeze, import and blind-review a local validation run; never calls a model."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import re
import sys

import authentic_user as au
import validation_prep as vp
import claim_protocol as typed
import attribution_protocol as field_typed
import atomic_protocol as atomic
import source_registry as sr

METRICS = ("fact_accuracy", "traceability", "attitude_direction", "theme_overlap",
           "fabricated_experience_rate", "unknown_restraint")


def digest(obj):
    return hashlib.sha256(au.canonical(obj).encode()).hexdigest()


def text_digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise au.InputError(message)


def safe_path(root, relative):
    require(isinstance(relative, str) and bool(relative), "Missing relative path")
    relative = Path(relative)
    require(not relative.is_absolute() and ".." not in relative.parts, "Path must stay inside its workspace")
    result = Path(root) / relative
    require(result.resolve().is_relative_to(Path(root).resolve()), "Path points outside its workspace")
    return result


def save(path, value):
    au.write_new(str(path), json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def new_dir(path):
    directory = Path(path).expanduser().resolve()
    directory.parent.mkdir(parents=True, exist_ok=True)
    try:
        directory.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise au.InputError("Output directory exists; choose a new directory") from exc
    return directory


def decode_prompt(text):
    try:
        header, data = text.split("INPUT_JSON:\n", 1)
        payload = json.loads(data)
    except (ValueError, json.JSONDecodeError) as exc:
        raise au.InputError("Prompt must contain one valid INPUT_JSON payload") from exc
    require(isinstance(payload, dict), "Prompt payload must be an object")
    require(set(payload) == {"subject_alias", "question_id", "question", "user_context"}, "Unexpected prompt fields")
    require(isinstance(payload["user_context"], dict) and isinstance(payload["user_context"].get("evidence"), list),
            "Prompt must contain an evidence list")
    return header + "INPUT_JSON:\n", payload


def call_id(call):
    return f'{call["case"]}-{call["condition"]}-{call["question_id"]}-r{call["run"]}'


def audit_inputs(input_dir):
    root = Path(input_dir).expanduser().resolve()
    manifest = au.read_object(root / "manifest.json")
    protocol = au.read_object(root / "protocol.json")
    require(manifest.get("protocol_sha256") == digest(protocol), "Protocol checksum mismatch")
    require(isinstance(protocol.get("questions"), dict) and set(protocol["questions"]) == {"Q1", "Q2", "Q3", "Q4"},
            "Expected the four frozen validation questions")
    repeat_count = protocol.get("repeats_per_question_condition")
    require(type(repeat_count) is int and 1 <= repeat_count <= 5, "Invalid repeat count")
    files = manifest.get("inputs")
    require(isinstance(files, list) and bool(files), "Input manifest has no prompt files")
    prompts = {}
    for record in files:
        require(isinstance(record, dict), "Invalid input record")
        path = record.get("path")
        require(isinstance(path, str) and path not in prompts, "Duplicate or invalid prompt path")
        raw = safe_path(root, path).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == record.get("sha256"), "Prompt checksum mismatch")
        text = raw.decode("utf-8")
        header, payload = decode_prompt(text)
        require(text_digest(header) == manifest.get("shared_instructions_sha256"), "Shared instructions changed")
        if protocol.get("response_protocol") == "atomic-bound-v4":
            require(payload["user_context"].get("source_catalogue") == sr.catalogue(payload["user_context"]["evidence"]), "Derived source catalogue differs from visible evidence")
        if protocol.get('source_map_protocol') is not None:
            require(protocol['source_map_protocol'] == sr.MAP_VERSION, 'Unsupported source map protocol')
            require(protocol.get('response_protocol') == 'atomic-bound-v4', 'Source maps require atomic answers')
            require(payload['user_context'].get('source_map') == sr.record_map(payload['user_context']['evidence']), 'Source map differs from selected records')
        else:
            require('source_map' not in payload['user_context'], 'Unregistered source map in frozen input')
        prompts[path] = {"sha256": record["sha256"], "payload": payload}
    require(manifest.get("unique_prompts") == len(prompts), "Prompt count mismatch")
    calls, keys, cases = [], set(), set()
    for line in (root / "calls.jsonl").read_text(encoding="utf-8").splitlines():
        require(bool(line.strip()), "Empty call record")
        call = json.loads(line)
        require(isinstance(call, dict), "Invalid call record")
        case, condition, qid, repeat = (call.get(k) for k in ("case", "condition", "question_id", "run"))
        require(isinstance(case, str) and re.fullmatch(r"S\d{3,}", case), "Invalid case ID")
        require(condition in ("X", "Y") and qid in ("Q1", "Q2", "Q3", "Q4"), "Invalid condition or question")
        require(type(repeat) is int and 1 <= repeat <= repeat_count, "Invalid repeat index")
        expected = f"{case}/{condition}/{qid}.txt"
        require(call.get("prompt") == expected and expected in prompts, "Call references an unexpected prompt")
        require(call.get("prompt_sha256") == prompts[expected]["sha256"], "Call prompt checksum mismatch")
        require(call.get("answer") == f"answers/{case}/{condition}/{qid}/run-{repeat}.json", "Invalid answer path")
        payload = prompts[expected]["payload"]
        require(payload["subject_alias"] == case and payload["question_id"] == qid, "Call/payload identity mismatch")
        key = call_id(call)
        require(key not in keys, "Duplicate planned call")
        keys.add(key)
        cases.add(case)
        calls.append(call)
    require(len(cases) == manifest.get("users"), "User count mismatch")
    require(len(calls) == manifest.get("planned_calls") == len(cases) * 8 * repeat_count, "Incomplete call grid")
    require(len(prompts) == len(cases) * 8, "Incomplete prompt grid")
    for case in cases:
        for qid in protocol["questions"]:
            left = prompts[f"{case}/X/{qid}.txt"]["payload"]
            right = prompts[f"{case}/Y/{qid}.txt"]["payload"]
            require(left["question"] == right["question"], "Conditions have different questions")
            rows = [left["user_context"]["evidence"], right["user_context"]["evidence"]]
            memory = [data for data in rows if data and all(r.get("kind") in ("survey", "verbatim") for r in data)]
            require(len(memory) == 1, "Expected one individual-memory condition")
            baseline = rows[1] if rows[0] is memory[0] else rows[0]
            require(baseline == vp.baseline_tags(memory[0]), "Historical tags differ from the matched memory source")
    return root, manifest, protocol, calls, prompts


def model_config(config):
    fields = {"provider", "model", "revision", "parameters", "seed_policy", "repeat_seeds", "input_token_limit", "synthetic"}
    plan = config.get("provider") == "openai-chatgpt-plan"
    require(set(config) == fields | ({"transport"} if plan else set()), "Model config fields do not match the documented schema; do not include credentials")
    for key in ("provider", "model", "revision"):
        value = config[key]
        require(isinstance(value, str) and bool(value.strip()) and value.strip().lower() not in ("latest", "default", "auto"),
                "Model provider, ID and fixed revision must be specified")
    params = config["parameters"]
    require(isinstance(params, dict) and set(params) == {"temperature", "top_p", "max_output_tokens"}, "Invalid parameter schema")
    if plan:
        require(all(value is None for value in params.values()), "Plan route does not accept temperature/top_p/max_output_tokens")
        transport = config["transport"]
        require(isinstance(transport, dict) and transport.get("route") == "https://api.openai.com/v1/responses" and
                transport.get("store") is False and transport.get("stream") is True and
                transport.get("billing_policy") == "subscription_only_no_paid_fallback", "Invalid plan-only route policy")
        require(transport.get("reasoning_effort") == "low" and transport.get("revision_policy") == "provider_alias_exploratory",
                "Plan pilot must record supported effort and unpinned alias limitation")
        require(transport.get('source_review_protocol') in (None,'clause-bound-v2','scope-bound-v3'),'Unknown source review protocol')
        if transport.get('source_review_protocol'):
            require(transport.get('response_protocol')=='atomic-bound-v4','Clause review requires atomic generation')
        if 'source_review_model' in transport:
            value=transport['source_review_model']
            require(isinstance(value,str) and bool(value.strip()) and value.strip().lower() not in ('auto','latest','default'),'Source reviewer must be explicitly frozen')
        if 'source_review_timeout_seconds' in transport:
            value=transport['source_review_timeout_seconds']
            require(type(value) is int and 30<=value<=300,'Invalid source review time guard')
        for field in ("max_input_characters", "max_output_characters", "reported_output_token_guard"):
            require(type(transport.get(field)) is int and transport[field] > 0, "Invalid local stream guard")
        require(config["seed_policy"] == "unsupported", "Plan route does not expose a seed parameter")
    else:
        for name, low, high in (("temperature", 0, 2), ("top_p", 0, 1)):
            value = params[name]
            require(type(value) in (int, float) and math.isfinite(value) and low <= value <= high,
                    "Invalid numeric model parameter")
        require(params["top_p"] > 0, "top_p must be positive")
        require(type(params["max_output_tokens"]) is int and 1 <= params["max_output_tokens"] <= 100000, "Invalid output token limit")
    require(type(config["input_token_limit"]) is int and 1 <= config["input_token_limit"] <= 1000000, "Invalid input token limit")
    require(config["seed_policy"] in ("unsupported", "same_repeat_schedule"), "Invalid seed policy")
    seeds = config["repeat_seeds"]
    if config["seed_policy"] == "unsupported":
        require(seeds is None, "Unsupported seed policy must use null repeat_seeds")
    else:
        require(isinstance(seeds, list) and 1 <= len(seeds) <= 5 and
                all(type(seed) is int and 0 <= seed < 2 ** 32 for seed in seeds), "Invalid repeat seed schedule")
    require(type(config["synthetic"]) is bool, "synthetic must be boolean")
    return config


def templates(input_dir, output_dir):
    _, manifest, _, calls, _ = audit_inputs(input_dir)
    root = new_dir(output_dir)
    config = {"provider": None, "model": None, "revision": None,
              "parameters": {"temperature": 0, "top_p": 1, "max_output_tokens": 800},
              "seed_policy": "unsupported", "repeat_seeds": None, "input_token_limit": 16000, "synthetic": False}
    review = {"inputs_manifest_sha256": digest(manifest), "reviewer": None,
              "cases": {case: {"status": "needs_review", "unsupported_parts": [], "notes": ""}
                        for case in sorted({call["case"] for call in calls})}}
    save(root / "model-config.template.json", config)
    save(root / "visible-review.template.json", review)
    return {"ok": True, "status": "templates_only_not_frozen", "directory": str(root)}


def freeze(input_dir, config_file, review_file, output_dir):
    root, manifest, protocol, calls, _ = audit_inputs(input_dir)
    config, review = model_config(au.read_object(config_file)), au.read_object(review_file)
    require(protocol.get("response_protocol", "legacy-v1") == config.get("transport", {}).get("response_protocol", "legacy-v1"), "Frozen response protocol differs from input instructions")
    if config["seed_policy"] == "same_repeat_schedule":
        require(len(config["repeat_seeds"]) == max(c["run"] for c in calls), "Seed schedule must cover each repeat exactly")
    require(review.get("inputs_manifest_sha256") == digest(manifest), "Review belongs to another input set")
    require(isinstance(review.get("reviewer"), str) and bool(review["reviewer"].strip()), "Visible-evidence reviewer is required")
    cases = {call["case"] for call in calls}
    require(isinstance(review.get("cases"), dict) and set(review["cases"]) == cases, "Review must cover all and only selected cases")
    for case in cases:
        row = review["cases"][case]
        require(isinstance(row, dict) and row.get("status") == "reviewed", "Unknown-question scope is not reviewed")
        parts = row.get("unsupported_parts")
        require(isinstance(parts, list) and parts and all(isinstance(p, str) and p.strip() for p in parts),
                "Record which parts of the unknown question lack visible evidence")
    directory = new_dir(output_dir)
    run = {"schema_version": 1, "skill_version": au.VERSION, "input_dir": str(root),
           "inputs_manifest_sha256": digest(manifest), "model_config": config,
           "model_config_sha256": digest(config), "visible_review": review,
           "initial_status": "frozen_waiting_for_imports", "calls": calls,
           "automatic_model_calls": 0, "provider_verification": "not_implemented"}
    run["run_sha256"] = digest(run)
    save(directory / "run.json", run)
    return {"ok": True, "directory": str(directory), "run_sha256": run["run_sha256"],
            "planned_calls": len(calls), "automatic_model_calls": 0}


def load_run(run_dir):
    directory = Path(run_dir).expanduser().resolve()
    run = au.read_object(directory / "run.json")
    require(run.get("schema_version") == 1, "Unsupported run schema")
    require(run.get("run_sha256") == digest({k: v for k, v in run.items() if k != "run_sha256"}), "Frozen run checksum mismatch")
    model_config(run["model_config"])
    require(digest(run["model_config"]) == run.get("model_config_sha256"), "Frozen model config mismatch")
    _, manifest, _, calls, prompts = audit_inputs(run["input_dir"])
    require(digest(manifest) == run.get("inputs_manifest_sha256") and calls == run.get("calls"), "Frozen inputs changed")
    return directory, run, {call_id(c): c for c in calls}, prompts


def check_common_answer(payload, answer):
    require(isinstance(answer, dict), "Response answer must be an object")
    require(isinstance(answer.get("answer"), str) and answer["answer"].strip(), "Answer text is required")
    require(answer.get("direction") in ("promoter", "passive", "detractor", "unknown"), "Invalid attitude direction")
    if answer.get("protocol_version") in (2,3,4):
        try:
            renderer = atomic if answer.get("protocol_version")==4 else field_typed if answer.get("protocol_version")==3 else typed
            expected = renderer.render(payload["user_context"]["evidence"], answer.get("wire_answer"))
        except typed.ProtocolError as exc:
            raise au.InputError(str(exc)) from exc
        require(answer == expected, "Rendered answer differs from original typed wire answer")
    claims, unknowns = answer.get("claims"), answer.get("unknowns")
    require(isinstance(claims, list) and isinstance(unknowns, list), "Answer requires claims and unknowns lists")
    require(all(isinstance(u, str) and u.strip() for u in unknowns), "Invalid unknown statement")
    require(bool(claims) or bool(unknowns), "Answer must contain claims or explicit unknowns")
    lookup = {r["id"] for r in payload["user_context"]["evidence"]}
    declared = set()
    for claim in claims:
        require(isinstance(claim, dict) and isinstance(claim.get("text"), str) and claim["text"].strip(), "Invalid claim")
        refs = claim.get("evidence_ids")
        require(isinstance(refs, list) and refs and all(isinstance(r, str) and r in lookup for r in refs), "Unknown claim evidence")
        require(claim.get("kind") in ("fact", "inference") and claim.get("confidence") in ("low", "medium", "high"), "Invalid claim type/confidence")
        require(not (claim["kind"] == "inference" and claim["confidence"] == "high"), "Inference confidence exceeds medium")
        declared.update(refs)
    inline = set(re.findall(r"\[(E\d+)\]", answer["answer"]))
    require(inline == declared, "Body citations and declared evidence do not match")


def validate_response(run, calls, prompts, response, *, check_answer=True):
    key = response.get("call_id")
    require(isinstance(key, str) and key in calls, "Response references an unknown call")
    call = calls[key]
    require(response.get("run_sha256") == run["run_sha256"], "Response belongs to another frozen run")
    require(response.get("prompt_sha256") == call["prompt_sha256"], "Response prompt checksum mismatch")
    require(response.get("model_config_sha256") == run["model_config_sha256"], "Response model config mismatch")
    require(response.get("origin") in ("provider_response", "synthetic_test"), "Response origin must be explicit")
    if response["origin"] == "provider_response":
        require(not run["model_config"]["synthetic"], "Synthetic model config cannot claim provider execution")
        require(isinstance(response.get("provider_request_id"), str) and response["provider_request_id"].strip(), "Provider request ID is required")
    require(response.get("model") == run["model_config"]["model"] and response.get("revision") == run["model_config"]["revision"],
            "Reported model/revision differs from frozen config")
    config = run["model_config"]
    seed = None if config["seed_policy"] == "unsupported" else config["repeat_seeds"][call["run"] - 1]
    require("seed" in response and response["seed"] == seed, "Reported seed differs from frozen repeat schedule")
    usage = response.get("usage")
    require(isinstance(usage, dict), "Response usage metadata is required")
    output_limit = config["transport"]["reported_output_token_guard"] if config["provider"] == "openai-chatgpt-plan" else config["parameters"]["max_output_tokens"]
    for field, limit in (("input_tokens", config["input_token_limit"]), ("output_tokens", output_limit)):
        require(type(usage.get(field)) is int and 0 <= usage[field] <= limit, "Reported token usage violates frozen limits")
    if check_answer:
        check_common_answer(prompts[call["prompt"]]["payload"], response.get("answer"))
    return key


def ingest(run_dir, response_file):
    directory, run, calls, prompts = load_run(run_dir)
    response = au.read_object(response_file)
    key = validate_response(run, calls, prompts, response)
    save(directory / "responses" / f"{key}.json", response)
    return {"ok": True, "call_id": key, "origin": response["origin"], "provider_verified": False}


def responses_for(directory, run, calls, prompts):
    responses = {}
    for path in (directory / "responses").glob("*.json"):
        response = au.read_object(path)
        key = validate_response(run, calls, prompts, response)
        require(path.name == f"{key}.json" and key not in responses, "Duplicate/misnamed response")
        responses[key] = response
    return responses


def raw_responses_for(source, run, calls, prompts):
    """Review every unmodified envelope, including answer-contract failures."""
    responses, failures = {}, {}
    for path in Path(source).glob("*.json"):
        response = au.read_object(path)
        key = validate_response(run, calls, prompts, response, check_answer=False)
        require(path.name == f"{key}.json" and key not in responses, "Duplicate/misnamed raw response")
        require(isinstance(response.get("answer"), dict), "Raw JSON answer object required")
        try:
            check_common_answer(prompts[calls[key]["prompt"]]["payload"], response["answer"])
        except au.InputError as exc:
            failures[key] = str(exc)
        responses[key] = response
    return responses, failures


def status(run_dir):
    directory, run, calls, prompts = load_run(run_dir)
    responses = responses_for(directory, run, calls, prompts)
    counts = Counter(r["origin"] for r in responses.values())
    return {"planned_calls": len(calls), "imported_responses": len(responses),
            "missing_responses": len(calls) - len(responses), "provider_response_imports": counts["provider_response"],
            "synthetic_test_imports": counts["synthetic_test"], "provider_verified": False,
            "automatic_model_calls": 0, "status": "imports_complete" if len(calls) == len(responses) else "awaiting_imports"}


def load_judges(judge_dir, run):
    root = Path(judge_dir).expanduser().resolve()
    manifest = au.read_object(root / "manifest.json")
    require(manifest.get("inputs_manifest_sha256") == run["inputs_manifest_sha256"], "Judge material belongs to another input set")
    files = manifest.get("case_files")
    require(isinstance(files, list), "Judge manifest requires case files")
    result = {}
    for record in files:
        path = safe_path(root, record.get("path"))
        require(hashlib.sha256(path.read_bytes()).hexdigest() == record.get("sha256"), "Hidden judge material checksum mismatch")
        obj = au.read_object(path)
        require(isinstance(obj.get("case"), str) and obj["case"] not in result, "Duplicate judge case")
        mapping = obj.get("condition_map")
        require(isinstance(mapping, dict) and set(mapping) == {"X", "Y"} and
                set(mapping.values()) == {"historical_tag_baseline", "individual_memory"}, "Invalid hidden condition map")
        result[obj["case"]] = obj
    require(set(result) == {c["case"] for c in run["calls"]}, "Judge cases do not match frozen inputs")
    return root, result


def audit(input_dir, judge_dir=None):
    _, manifest, _, calls, prompts = audit_inputs(input_dir)
    result = {"ok": True, "users": manifest["users"], "prompts": manifest["unique_prompts"],
              "planned_calls": len(calls), "model_calls_performed": 0,
              "scope": "Checksums, grid, shared instructions and matched tag sources; no semantic efficacy check"}
    if judge_dir:
        _, judges = load_judges(judge_dir, {"inputs_manifest_sha256": digest(manifest), "calls": calls})
        for case, hidden in judges.items():
            boundary = au.date_value(hidden["cutoff_exclusive"])
            require(au.date_value(hidden["holdout"]["date"]) == boundary, "Hidden record does not match its cutoff")
            memory_label = next(k for k, v in hidden["condition_map"].items() if v == "individual_memory")
            for qid in ("Q1", "Q2", "Q3", "Q4"):
                rows = prompts[f"{case}/{memory_label}/{qid}.txt"]["payload"]["user_context"]["evidence"]
                require(all(au.date_value(row["date"]) < boundary for row in rows), "Visible evidence violates the exclusive cutoff")
        result["judge_checksums_verified"] = True
        result["time_boundary_violations"] = 0
    return result


def blind(run_dir, judge_dir, output_dir, allow_synthetic=False, raw_response_dir=None):
    directory, run, calls, prompts = load_run(run_dir)
    responses, failures = raw_responses_for(raw_response_dir, run, calls, prompts) if raw_response_dir else (responses_for(directory, run, calls, prompts), {})
    require(set(responses) == set(calls), "All planned responses are required before blind export")
    require(allow_synthetic or not any(r["origin"] == "synthetic_test" for r in responses.values()), "Synthetic answers require explicit demo export")
    judge_root, judges = load_judges(judge_dir, run)
    target = Path(output_dir).expanduser().resolve()
    for private in (directory, judge_root):
        require(not target.is_relative_to(private) and not private.is_relative_to(target), "Review pack must be separate from run and judge directories")
    require(not (directory / "review-key.json").exists(), "Review key already exists; use the existing review pack")
    target = new_dir(target)
    tasks, key_rows, grade_rows, repeat_map = [], {}, [], {}
    order = sorted(calls, key=lambda key: digest({"seed": run["run_sha256"], "call": key, "mode": "blind-v1"}))
    for index, key in enumerate(order, 1):
        call, response = calls[key], responses[key]
        identity = f"B{index:04d}"
        hidden = judges[call["case"]]
        payload = prompts[call["prompt"]]["payload"]
        memory_label = next(k for k, v in hidden["condition_map"].items() if v == "individual_memory")
        history = prompts[f'{call["case"]}/{memory_label}/{call["question_id"]}.txt']["payload"]["user_context"]["evidence"]
        reference = {k: hidden["holdout"][k] for k in ("date", "industry", "score", "text")}
        tasks.append({"review_id": identity, "question_id": call["question_id"], "question": payload["question"],
                      "mechanical_check": {"passed": key not in failures, "error": failures.get(key)},
                      "answer": response["answer"], "provided_evidence": payload["user_context"]["evidence"],
                      "reference_history": history, "hidden_reference": reference})
        key_rows[identity] = {"case": call["case"], "condition": hidden["condition_map"][call["condition"]],
                              "question_id": call["question_id"], "run": call["run"], "origin": response["origin"]}
        grade_rows.append({"review_id": identity, "status": "unscored", "scores": {m: None for m in METRICS},
                           "na_reasons": {}, "notes": ""})
        repeat_map.setdefault((call["case"], call["condition"], call["question_id"]), []).append(identity)
    repeat_groups = [{"review_group_id": f"R{i:04d}", "review_ids": sorted(ids)}
                     for i, (_, ids) in enumerate(sorted(repeat_map.items(), key=lambda row: digest(row[1])), 1)]
    task_index = []
    for task in tasks:
        relative = f'tasks/{task["review_id"]}.json'
        save(target / relative, task)
        task_index.append({"review_id": task["review_id"], "path": relative,
                           "sha256": hashlib.sha256((target / relative).read_bytes()).hexdigest()})
    pack_hash = digest({"run_sha256": run["run_sha256"], "tasks": task_index, "repeat_groups": repeat_groups})
    pack = {"review_pack_sha256": pack_hash, "tasks": task_index, "repeat_groups": repeat_groups,
            "status": "unscored", "synthetic_present": any(r["origin"] == "synthetic_test" for r in responses.values()),
            "blinding_scope": "Condition labels and private identity map removed; content may reveal information depth"}
    grades = {"review_pack_sha256": pack_hash, "reviewer": None, "origin": "human_review",
              "scores": grade_rows, "repeat_scores": [{"review_group_id": g["review_group_id"], "status": "unscored",
                                                        "score": None, "na_reason": "", "notes": ""} for g in repeat_groups]}
    save(target / "review-pack.json", pack)
    save(target / "scores.template.json", grades)
    private_key = {"run_sha256": run["run_sha256"], "responses_sha256": digest(responses),
                   "review_pack_sha256": pack_hash, "review_pack_file": str(target / "review-pack.json"),
                   "reviews": key_rows, "repeat_groups": repeat_groups}
    if raw_response_dir:
        private_key["raw_response_dir"] = str(Path(raw_response_dir).resolve())
        private_key["mechanical_failures"] = failures
    private_key["key_sha256"] = digest(private_key)
    save(directory / "review-key.json", private_key)
    return {"ok": True, "review_tasks": len(tasks), "repeat_groups": len(repeat_groups), "directory": str(target)}


def paired_summary(values):
    users = sorted({case for case, _ in values})
    pairs = []
    for case in users:
        left, right = values.get((case, "historical_tag_baseline"), []), values.get((case, "individual_memory"), [])
        if left and right:
            pairs.append((sum(left) / len(left), sum(right) / len(right)))
    if not pairs:
        return {"paired_users": 0, "baseline_mean": None, "memory_mean": None, "difference_pp": None, "ci95_pp": None}
    differences = [(b - a) * 100 for a, b in pairs]
    rng = random.Random(20261026)
    samples = sorted(sum(rng.choice(differences) for _ in differences) / len(differences) for _ in range(1000))
    return {"paired_users": len(pairs), "baseline_mean": sum(a for a, _ in pairs) / len(pairs),
            "memory_mean": sum(b for _, b in pairs) / len(pairs),
            "difference_pp": sum(differences) / len(differences), "ci95_pp": [samples[24], samples[974]]}


def summarize(run_dir, scores_file):
    directory, run, calls, prompts = load_run(run_dir)
    key = au.read_object(directory / "review-key.json")
    require(key.get("run_sha256") == run["run_sha256"] and key.get("key_sha256") ==
            digest({k: v for k, v in key.items() if k != "key_sha256"}), "Private review key checksum mismatch")
    responses = raw_responses_for(key["raw_response_dir"], run, calls, prompts)[0] if key.get("raw_response_dir") else responses_for(directory, run, calls, prompts)
    require(digest(responses) == key.get("responses_sha256"), "Responses changed after blind export")
    pack = au.read_object(key["review_pack_file"])
    actual_hash = digest({"run_sha256": run["run_sha256"], "tasks": pack["tasks"], "repeat_groups": pack["repeat_groups"]})
    require(actual_hash == key.get("review_pack_sha256") == pack.get("review_pack_sha256"), "Review pack checksum mismatch")
    for task in pack["tasks"]:
        path = safe_path(Path(key["review_pack_file"]).parent, task["path"])
        require(hashlib.sha256(path.read_bytes()).hexdigest() == task["sha256"], "Review task checksum mismatch")
    scores = au.read_object(scores_file)
    require(scores.get("review_pack_sha256") == actual_hash, "Scores belong to another review pack")
    require(isinstance(scores.get("reviewer"), str) and scores["reviewer"].strip(), "Reviewer must be recorded")
    require(scores.get("origin") in ("human_review", "assistant_review", "synthetic_test"), "Score origin must be explicit")
    rows = scores.get("scores")
    require(isinstance(rows, list), "scores must be a list")
    seen, graded, missing = set(), {metric: {} for metric in METRICS}, 0
    target_question = {"attitude_direction": "Q2", "theme_overlap": "Q3", "unknown_restraint": "Q4"}
    for row in rows:
        require(isinstance(row, dict), "Invalid score row")
        identity = row.get("review_id")
        require(isinstance(identity, str) and identity in key["reviews"] and identity not in seen, "Unknown or duplicate review ID")
        seen.add(identity)
        meta = key["reviews"][identity]
        if row.get("status") != "scored":
            missing += 1
            continue
        require(isinstance(row.get("scores"), dict) and set(row["scores"]) == set(METRICS), "Score metric fields differ")
        require(isinstance(row.get("na_reasons"), dict), "NA reasons must be an object")
        for metric, value in row["scores"].items():
            if metric in target_question and meta["question_id"] != target_question[metric]:
                require(value is None, "Question-specific score filled for another question")
                continue
            if value is None:
                require(isinstance(row["na_reasons"].get(metric), str) and row["na_reasons"][metric].strip(), "Applicable NA score needs a reason")
                continue
            require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1, "Scores must be numbers from 0 to 1")
            if metric == "theme_overlap":
                require(value in (0, 0.5, 1), "Theme overlap must use normalized 0/1/2 scoring")
            if metric in ("attitude_direction", "fabricated_experience_rate", "unknown_restraint"):
                require(value in (0, 1), "Direction, fabrication and restraint use binary scoring")
            graded[metric].setdefault((meta["case"], meta["condition"]), []).append(value)
    missing += len(set(key["reviews"]) - seen)
    repeat_rows = scores.get("repeat_scores")
    require(isinstance(repeat_rows, list), "repeat_scores must be a list")
    expected = {g["review_group_id"]: g for g in key["repeat_groups"]}
    repeat_seen, repeat_values = set(), {}
    for row in repeat_rows:
        require(isinstance(row, dict), "Invalid repeat score row")
        identity = row.get("review_group_id")
        require(isinstance(identity, str) and identity in expected and identity not in repeat_seen, "Unknown or duplicate repeat group")
        repeat_seen.add(identity)
        if row.get("status") != "scored":
            missing += 1
            continue
        value = row.get("score")
        if value is None:
            require(isinstance(row.get("na_reason"), str) and row["na_reason"].strip(), "Repeat NA needs a reason")
            continue
        require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1, "Invalid repeat consistency score")
        meta = key["reviews"][expected[identity]["review_ids"][0]]
        repeat_values.setdefault((meta["case"], meta["condition"]), []).append(value)
    missing += len(set(expected) - repeat_seen)
    metrics = {name: paired_summary(value) for name, value in graded.items()}
    metrics["repeat_consistency"] = paired_summary(repeat_values)
    return {"status": "partial_scores" if missing else "scored_exploratory", "unscored_items": missing,
            "metrics": metrics, "score_origin": scores["origin"], "synthetic_present": pack["synthetic_present"],
            "provider_verified": False, "automatic_model_calls": 0,
            "answer_contract_failures": len(key.get("mechanical_failures", {})),
            "reviewed_answers": len(responses),
            "interpretation": "User-paired exploratory summary; lower fabrication rate is better; no automatic efficacy verdict"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("audit", "templates", "freeze", "ingest", "status", "blind", "summarize"))
    for field in ("input-dir", "output-dir", "run-dir", "judge-dir", "config", "review", "response", "scores", "output", "raw-response-dir"):
        parser.add_argument(f"--{field}")
    parser.add_argument("--allow-synthetic", action="store_true")
    args = parser.parse_args()
    try:
        needed = {"audit": ("input_dir",), "templates": ("input_dir", "output_dir"),
                  "freeze": ("input_dir", "config", "review", "output_dir"), "ingest": ("run_dir", "response"),
                  "status": ("run_dir",), "blind": ("run_dir", "judge_dir", "output_dir"),
                  "summarize": ("run_dir", "scores")}[args.command]
        require(all(getattr(args, field) for field in needed), "Missing command arguments: " + ", ".join(needed))
        if args.command == "audit":
            result = audit(args.input_dir, args.judge_dir)
        elif args.command == "templates":
            result = templates(args.input_dir, args.output_dir)
        elif args.command == "freeze":
            result = freeze(args.input_dir, args.config, args.review, args.output_dir)
        elif args.command == "ingest":
            result = ingest(args.run_dir, args.response)
        elif args.command == "status":
            result = status(args.run_dir)
        elif args.command == "blind":
            result = blind(args.run_dir, args.judge_dir, args.output_dir, args.allow_synthetic, args.raw_response_dir)
        else:
            result = summarize(args.run_dir, args.scores)
        au.write_new(args.output, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        return 0
    except (au.InputError, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        # Field-level JSON errors are reported without printing source records or credentials.
        message = str(exc) if isinstance(exc, au.InputError) else f"Invalid local input ({type(exc).__name__})"
        print(json.dumps({"ok": False, "error": message}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
