#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
demo_main.py — Offline zero-setup demo for virtual_user_skill.

Purpose
-------
Let anyone clone the repo and immediately try the "virtual user
interview" workflow with NO secrets, NO heavy dependencies, NO
encrypted library. Uses the 50-record sanitized public sample at
data/sample_scenarios.json.

Usage
-----
    python3 demo_main.py "your product question"
    python3 demo_main.py "用户对火车票退改签的真实痛点是什么" --top 5

Difference from production
--------------------------
- Production: 140k records, sentence-transformers + cosine on float32
  embeddings, encrypted Fernet library at data/scenario_library.json.enc
- Demo: 50 records, naive keyword Jaccard ranking, plain-text JSON.
  No model download, no internet, no GPU, runs in <1 s.

The output JSON shape matches search_scenarios.py so downstream
prompt-templates and notebook examples work unchanged.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).parent / "data" / "sample_scenarios.json"

# Fields used to build the matchable "document" text for each scenario.
INDEX_FIELDS = [
    "用户具体场景",
    "任务",
    "期待效果",
    "当前方案",
    "爽点",
    "痛点",
    "改进方向",
    "底层需求",
    "情绪标签",
    "内容范围",
]

# Lightweight stopwords (Chinese + English) to denoise the keyword set.
STOP = set("""
的 了 着 过 和 与 及 或 而 也 都 是 在 有 没 不 又 还 就 但 让 把 被
对 从 到 以 于 上 下 之 其 此 这 那 我 你 他 她 它 我们 你们 他们
一 二 三 个 些 啊 吗 呢 吧 哇 吧 啦 哦 哈 哎 喔 嗯
the a an of and or to in on at for with by is are was were be been being have has had
i you he she it we they this that these those my your his her our their
""".split())

WORD_RE = re.compile(r"[\u4e00-\u9fa5]+|[A-Za-z0-9]+")


def tokenize(text: str) -> set[str]:
    """Extract a bag of 1-2 char Chinese ngrams + Latin words."""
    if not text:
        return set()
    tokens: set[str] = set()
    for chunk in WORD_RE.findall(text):
        if re.match(r"[A-Za-z0-9]+", chunk):
            w = chunk.lower()
            if w not in STOP and len(w) > 1:
                tokens.add(w)
        else:
            # Chinese: include unigrams (>=2 chars) and bigrams
            for i in range(len(chunk)):
                if i + 2 <= len(chunk):
                    tokens.add(chunk[i : i + 2])
            if len(chunk) >= 2 and chunk not in STOP:
                tokens.add(chunk)
    return tokens


def doc_text(scenario: dict[str, Any]) -> str:
    return " ".join(str(scenario.get(f, "")) for f in INDEX_FIELDS)


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def search(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    if not DATA_FILE.exists():
        print(
            f"[ERROR] sample data not found at {DATA_FILE}.\n"
            f"        run scripts/extract_sample.py first, "
            f"or pull the repo with the data file committed.",
            file=sys.stderr,
        )
        sys.exit(2)

    scenarios: list[dict[str, Any]] = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    q_tokens = tokenize(query)

    scored: list[tuple[float, dict[str, Any]]] = []
    for s in scenarios:
        score = jaccard(q_tokens, tokenize(doc_text(s)))
        if score > 0:
            scored.append((score, s))

    scored.sort(key=lambda x: x[0], reverse=True)

    out: list[dict[str, Any]] = []
    for score, s in scored[:top_k]:
        item = dict(s)
        item["similarity_score"] = round(score, 4)
        out.append(item)
    return out


def render_human(query: str, results: list[dict[str, Any]]) -> str:
    if not results:
        return f'No matching scenarios for "{query}". Try broader keywords.'

    lines = [
        f'🔎 Query: {query}',
        f'📚 Sample library: 50 records (public demo subset)',
        f'✅ Top {len(results)} matches:',
        "",
    ]
    for i, r in enumerate(results, 1):
        bg = (r.get("用户姓名和背景信息") or "").splitlines()[0][:60]
        lines.append(f'#{i}  score={r["similarity_score"]:.3f}  序号={r.get("序号", "?")}')
        lines.append(f'    背景: {bg}...')
        lines.append(f'    范围: {r.get("内容范围", "")}')
        lines.append(f'    场景: {(r.get("用户具体场景") or "")[:120]}')
        lines.append(f'    痛点: {(r.get("痛点") or "")[:120]}')
        lines.append(f'    情绪: {r.get("情绪标签", "")}')
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Offline demo: keyword-search the 50-record public sample."
    )
    p.add_argument("query", help="natural-language product question (Chinese or English)")
    p.add_argument("--top", "-k", type=int, default=5, help="number of results (default 5)")
    p.add_argument("--json", action="store_true", help="emit raw JSON instead of human-readable")
    args = p.parse_args()

    results = search(args.query, top_k=args.top)

    if args.json:
        print(
            json.dumps(
                {
                    "query": args.query,
                    "total_scenarios": 50,
                    "returned": len(results),
                    "scenarios": results,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(render_human(args.query, results))


if __name__ == "__main__":
    main()
