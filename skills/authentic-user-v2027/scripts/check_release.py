#!/usr/bin/env python3
"""Check the exact public release file set. Does not inspect private archives."""

import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FILES = {
    "scripts/source_registry.py", "scripts/atomic_protocol.py", "scripts/atomic_review.py",
    "tests/test_atomic.py", "examples/answer-atomic-demo.json", "references/pilot-20261029-atomic.md",
    ".gitignore", "SKILL.md", "VERSION", "README.md", "RELEASE_NOTES.md", "LICENSE",
    "agents/openai.yaml", "references/data-contract.md", "references/validation.md",
    "scripts/attribution_protocol.py", "scripts/attribution_review.py", "scripts/plan_review.py",
    "tests/test_attribution.py", "tests/test_plan_review.py", "examples/answer-field-demo.json",
    "references/pilot-20261029-fresh.md",
    "scripts/authentic_user.py", "scripts/check_release.py", "scripts/package_release.py",
    "examples/profiles/archives_v2027/demo-rich.json",
    "examples/profiles/archives_extended/demo-sparse.json", "examples/answer-demo.json",
    "tests/test_authentic_user.py", "scripts/validation_prep.py", "tests/test_validation_prep.py",
    "scripts/claim_protocol.py", "scripts/trial_audit.py", "tests/test_claim_protocol.py",
    "examples/answer-typed-demo.json", "references/evidence-reasoning.md",
    "scripts/chatgpt_plan.py", "scripts/plan_trial.py", "tests/test_chatgpt_plan.py",
    "tests/test_plan_trial.py", "references/chatgpt-plan.md", "references/pilot-20261026.md", "references/pilot-20261029.md",
    "scripts/validation_workflow.py", "tests/test_validation_workflow.py", "examples/model-config.synthetic.json",
}
LOCAL_ONLY = {".git", "__pycache__", ".venv", "outputs", "dist"}


def check_release(root=ROOT):
    root = Path(root)
    errors = []
    found = set()
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if any(part in LOCAL_ONLY for part in rel.parts) or path.name == ".DS_Store":
            continue
        if path.is_symlink():
            errors.append(f"Symlink not allowed: {rel.as_posix()}")
        if not path.is_file():
            continue
        found.add(rel.as_posix())
    for name in sorted(found - PUBLIC_FILES):
        errors.append(f"Unlisted file: {name}")
    for name in sorted(PUBLIC_FILES - found):
        errors.append(f"Missing file: {name}")
    patterns = [
        re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
        re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
        re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{24,}"),
        re.compile(r"LTAI[A-Za-z0-9]{12,}"),
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    ]
    for name in sorted(PUBLIC_FILES & found):
        text = (root / name).read_text(encoding="utf-8")
        if any(pattern.search(text) for pattern in patterns):
            errors.append(f"Potential private data or credential in {name}; value suppressed")
        if name.endswith(".json"):
            obj = json.loads(text)
            if obj.get("synthetic") is not True:
                errors.append(f"Example must explicitly be synthetic: {name}")
            if "buyer_id" in obj and not str(obj["buyer_id"]).startswith("demo-"):
                errors.append(f"Non-demo user ID in {name}")
        if name.endswith(".md"):
            for link in re.findall(r"\]\(([^)]+)\)", text):
                if "://" in link or link.startswith("#"):
                    continue
                target = link.split("#", 1)[0]
                if target and not (root / name).parent.joinpath(target).exists():
                    errors.append(f"Broken local link in {name}: {target}")
    if (root / "VERSION").is_file():
        version = (root / "VERSION").read_text().strip()
        for name in ("SKILL.md", "README.md", "RELEASE_NOTES.md", "scripts/authentic_user.py"):
            if (root / name).is_file() and version not in (root / name).read_text():
                errors.append(f"Version mismatch in {name}")
    return {"ok": not errors, "public_file_count": len(PUBLIC_FILES), "errors": errors,
            "scan_scope": "Release allowlist, obvious credential patterns, synthetic examples, links, version"}


if __name__ == "__main__":
    result = check_release()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)
