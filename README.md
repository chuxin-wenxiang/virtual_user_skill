# virtual_user_skill

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

![demo](docs/demo.gif)

> 30-second walkthrough: ask a product question → get 8 distinct user types built from real research → pick which to interview in depth.

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
| **PMF check** | "Does this need actually exist?" | Stress-test your hypothesis against retrieved scenarios |
| **PRD review** | "Will users actually use this?" | Multi-user critique on a spec, including dissent |
| **Design crit** | "What would real users miss?" | Adversarial feedback grounded in past complaints |

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
