"""Extract 50 sanitized sample scenarios from the encrypted library.

This script is committed to the repo so contributors can regenerate samples
from their own data. It does NOT decrypt without the local key file.
"""
import base64
import json
import random
import re
import sys
from pathlib import Path
from cryptography.fernet import Fernet

KEY_FILE = Path.home() / ".virtual_user" / ".key"
ENC_FILE = Path("data/scenario_library.json.enc")
OUT_FILE = Path("data/sample_scenarios.json")

# ---- regex sentinels for re-checking PII even though library is anonymized ----
PII_PATTERNS = {
    "phone_11digit": re.compile(r"1[3-9]\d{9}"),
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "order_no_15plus": re.compile(r"\b\d{15,}\b"),
    "idcard_18": re.compile(r"\b\d{17}[\dX]\b"),
    "alibaba_workid_9": re.compile(r"\b1\d{8}\b"),  # employee ids
}


def has_pii(record: dict) -> list:
    text = json.dumps(record, ensure_ascii=False)
    hits = []
    for name, pat in PII_PATTERNS.items():
        if pat.search(text):
            hits.append(name)
    return hits


def main(n: int = 50, seed: int = 20260608):
    if not KEY_FILE.exists():
        sys.exit(f"❌ Decryption key not found at {KEY_FILE}. Run `python src/encrypt.py` first.")
    if not ENC_FILE.exists():
        sys.exit(f"❌ Encrypted library not found at {ENC_FILE}.")

    key = KEY_FILE.read_bytes()
    enc_data = ENC_FILE.read_bytes()
    print(f"🔓 Decrypting {len(enc_data)/1024/1024:.1f} MB...")
    # Library is stored as base64-of-Fernet-token; decode once before Fernet.
    fernet_token = base64.b64decode(enc_data)
    data = json.loads(Fernet(key).decrypt(fernet_token).decode("utf-8"))
    print(f"✓ Loaded {len(data)} scenarios")

    # deterministic sample
    random.seed(seed)
    sample = random.sample(data, min(n, len(data)))

    # PII safety pass
    flagged = []
    safe = []
    for s in sample:
        hits = has_pii(s)
        if hits:
            flagged.append((s.get("序号", "?"), hits))
        else:
            safe.append(s)

    if flagged:
        print(f"⚠️  Dropped {len(flagged)} records flagged for PII:")
        for sn, h in flagged[:5]:
            print(f"   #{sn}: {h}")
        # top up by re-sampling until we hit n safe records
        attempts = 0
        while len(safe) < n and attempts < n * 5:
            extra = random.choice(data)
            if not has_pii(extra) and extra not in safe:
                safe.append(extra)
            attempts += 1

    print(f"✓ {len(safe)} safe records kept")

    OUT_FILE.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
    size_kb = OUT_FILE.stat().st_size / 1024
    print(f"💾 Wrote {OUT_FILE} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    main(n)
