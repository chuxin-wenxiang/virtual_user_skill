# virtual_user_skill

## v2027 preview

[Individual-memory Skill](skills/authentic-user-v2027/README.md), version `2027.0.0-alpha.11`, adds question-anchor retrieval with recent same-industry context, explicit handling of same-time score ambiguity, and capability checks throughout the new batch workflow. A single-memory design uses 64 generations and at most 16 source-review batches for eight people, with simple attitude baselines computed locally. All 176 offline checks pass. One existing-plan probe sent no user data; the next eight users are frozen and awaiting their batch-specific transmission consent. No new-user effectiveness result is available. See the [implementation and preparation record](skills/authentic-user-v2027/references/context-20261031.md).

The last [alpha.9 trial](skills/authentic-user-v2027/references/pilot-20261030-scope.md) completed 128 generations (108 strict passes), but source review stopped after a connection error with only 8/128 final answers. Memory attitude hits were 6/16, below last-NPS persistence at 14/16. **Research preview: full source validation remains incomplete and predictive validity is unproven.** Ordinary use runs on the host model without requiring a separately purchased API; real archives, responses and credentials stay local.

The [open-source comparison and upgrade plan](docs/v2027-open-source-review-20261031.md) reviews pinned code, licenses and author papers from Stanford genagents, TinyTroupe, τ-bench, Smallville and AgentSociety. Mapping, reporting and retrieval heuristics are implemented; independent human scoring and new-user effect validation remain outstanding. The existing implementation below remains available.

> **AI virtual users powered by 54k+ real, anonymized user-research scenarios.**
> Stop interviewing prompt-engineered personas. Start talking to ones built from actual data.

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://python.org)
[![Scenarios](https://img.shields.io/badge/scenarios-54%2C631-orange.svg)](#data)
[![GitHub stars](https://img.shields.io/github/stars/chuxin-wenxiang/virtual_user_skill?style=social)](https://github.com/chuxin-wenxiang/virtual_user_skill/stargazers)

---

## Why this exists

Most "AI user research" tools today are GPT pretending to be five different people. The personas all talk the same, agree too easily, and never bring up the things you didn't already know to ask about.

This project takes a different route: **vector-search over 54,631 real, anonymized user scenarios** (collected from years of travel-app user research), then lets an LLM generate distinct virtual users grounded in that retrieved data. The result feels closer to interviewing actual humans — they contradict themselves, surface unexpected pain points, and disagree with you when warranted.

---

## Demo

> Ask a product question in natural language → retrieve matching real-world scenarios → ground your AI personas in actual data.

### Full Demo (5 min)

[![Full Demo](assets/demo/virtual_user_skill_demo_full.gif)](assets/demo/virtual_user_skill_demo_full.mp4)

### 5 Working Modes

**01 · Exploration — 1v1 Interview + Debate**

Generate 8-10 distinct user archetypes, then conduct multi-turn interviews or set up a user debate.

![Exploration Mode](assets/demo/mode_1_exploration.gif)

**02 · PMF Validation — Sean Ellis Scale, ≥40% = Pass**

Stress-test your product hypothesis against real user data with quantified PMF scoring.

![PMF Validation](assets/demo/mode_3_pmf_validation.gif)

**03 · PRD Calibration — 4-Dimension Scoring + Data Plan**

Multi-user critique on your spec with adversarial feedback and data-backed improvement paths.

![PRD Calibration](assets/demo/mode_4_prd_calibration.gif)

**04 · Metrics Voting — Pre-Launch Metric Estimation**

Virtual users estimate click-through rates, retention, and conversion before you ship.

![Metrics Voting](assets/demo/mode_5_metrics_voting.gif)

**05 · Debate — Multi-Perspective Confrontation**

Two user groups argue opposing views on your feature, producing a synthesis report.

![Debate Mode](assets/demo/mode_2_debate.gif)

---

## Quick start (3 steps)

```bash
# 1. Clone and set up
git clone https://github.com/chuxin-wenxiang/virtual_user_skill.git
cd virtual_user_skill
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Initialize encryption key for the bundled scenario library
python src/encrypt.py

# 3. Ask your first question
python src/main.py "What do users care about most when booking a flight?"
```

You'll get 8-10 user types back. Pick which to converse with, and the tool runs a multi-turn interview against each.

---

## Use cases

| Mode | When to use | What you get |
|---|---|---|
| **Exploration** | "What's the user landscape for X?" | 8-10 distinct user types with backgrounds, pain points, emotions |
| **PMF Validation** | "Does this need actually exist?" | Sean Ellis scale scoring, confidence grading, risk assessment |
| **PRD Calibration** | "Will users actually use this?" | 4-dimension scoring + data validation plan |
| **Metrics Voting** | "What will click-through / retention look like?" | Pre-launch metric estimation from virtual user panels |
| **Debate** | "What are the opposing views on this feature?" | Multi-perspective confrontation + synthesis report |

---

## How it works

```
Your question
    ↓
[1] Vector search over 54,631 anonymized scenarios
    ↓
[2] Top-k retrieved scenarios → cluster into distinct user archetypes
    ↓
[3] LLM generates fully-fleshed virtual users with names, backgrounds, pain points, emotions
    ↓
[4] You pick one or more → multi-turn dialogue
    ↓
[5] Auto-generated insight report (Markdown)
```

- **Retrieval**: 768-dim `text2vec-base-chinese` embeddings, pre-computed
- **Storage**: Fernet-encrypted scenario library (privacy by default)
- **Generation**: pluggable LLM (defaults to GPT-4-class via OpenAI-compatible API)

---

## Data

The bundled `scenario_library.json.enc` contains 54,631 anonymized user research scenarios across 13 fields:

`user_name | user_background | content_scope | is_outbound_travel | scenario | task | expected_outcome | current_solution | delight_points | pain_points | improvement_directions | underlying_needs | emotion_tags`

All personally identifiable information has been stripped. The data is encrypted at rest with a key generated locally on first run (`~/.virtual_user/.key`) — never shared, never uploaded.

A small **sample of 50 anonymized scenarios** ships unencrypted in `data/sample_scenarios.json` so you can inspect the structure before running anything.

---

## Comparison

| Approach | Realism | Diversity | Bias risk | Setup |
|---|---|---|---|---|
| Prompt-engineered persona | Low | Low (LLM convergence) | High | Free, fast |
| Real interviews | High | Medium | Low | Slow, expensive |
| **virtual_user_skill** | Medium-High | **High (data-driven)** | **Low (real voices)** | One-time setup |

---

## FAQ

**Is this a replacement for real user interviews?**
No. It's a fast first-pass screen — best for stress-testing ideas before committing to recruitment. Real interviews still win for novel domains.

**Can I use my own data instead?**
Yes. `scripts/prepare_data.py your_data.xlsx` ingests any spreadsheet matching the 13-field schema.

**What languages does it support?**
The bundled data is Chinese travel-app scenarios. Embeddings are Chinese-tuned. English/multilingual support is on the roadmap (PRs welcome).

**Is the data really anonymized?**
Yes. All names, locations, dates, and identifiers were replaced or removed before encryption. The repo is licensed MIT specifically because the data is safe to share.

---

## Roadmap

- [ ] English scenario library
- [ ] CLI mode for CI integration
- [ ] Web UI (Streamlit)
- [ ] Cross-domain transfer (e-commerce, fintech, SaaS)
- [ ] Compare-with-real-users evaluation framework

Open an [issue](https://github.com/chuxin-wenxiang/virtual_user_skill/issues) to vote or propose.

---

## Contributing

Contributions welcome — especially:
- Domain-specific scenario libraries (e-commerce, fintech, etc.)
- Multilingual embeddings
- New use case templates

See [CONTRIBUTING.md](CONTRIBUTING.md) (TODO) for details.

---

## License

MIT — see [LICENSE](LICENSE).

If this saves you research time, a ⭐ helps a lot. Thanks for reading.


---

[中文版 / Chinese version](./README_zh.md)
