# virtual_user_skill

## v2027 预览版

[个体记忆版 Skill](skills/authentic-user-v2027/README.md) 已更新到 `2027.0.0-alpha.5`：事实选取原字段，推断单列前提、竞争解释及外部更新条件，统一生成引用。同8人回归已完整执行 **128/128次，本地完整性审计通过**，无重试、无付费回退；两组引用结构均通过，但记忆组72条推断中仍有6条仅部分支持。**已可作为研究辅助工具试用，真人模拟效果未获独立验证。** 弃答、用户配对、重复目标敏感性及限制见[本轮公开报告](skills/authentic-user-v2027/references/pilot-20261029.md)；真实档案与凭证留本地，[旧轮执行偏离](skills/authentic-user-v2027/references/pilot-20261026.md)继续保留。下方保留原版使用说明。

> **基于 54,000+ 真实用研场景的 AI 虚拟用户系统**
> 不是让 GPT 扮演用户，而是从真实数据中"重建"用户。

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://python.org)
[![Scenarios](https://img.shields.io/badge/scenarios-54%2C631-orange.svg)](#数据)
[![GitHub stars](https://img.shields.io/github/stars/chuxin-wenxiang/virtual_user_skill?style=social)](https://github.com/chuxin-wenxiang/virtual_user_skill/stargazers)

---

## 为什么做这个

市面上的"AI用研工具"本质上是 GPT 假装5个不同的人，角色之间说话方式趋同、太容易附和、永远不会提出你没想到的问题。

这个项目走了一条不同的路：**在 54,631 条真实、脱敏的用研场景上做向量检索**（来自数年旅行 App 用户研究的积累），然后让 LLM 基于检索到的数据生成有据可依的虚拟用户。效果更接近真实访谈——他们会自相矛盾、会提出意料之外的痛点、会在你的方案有问题时直接反对你。

---

## 演示

> 用自然语言提出产品问题 → 检索匹配的真实场景 → 基于真实数据生成 AI 虚拟用户

### 完整演示 (5分钟)

[![完整演示](assets/demo/virtual_user_skill_demo_full.gif)](assets/demo/virtual_user_skill_demo_full.mp4)

### 5 种工作模式

**01 · 探索模式 — 1v1 深度访谈 + 辩论赛**

生成 8-10 个差异化的用户画像，进行多轮深度访谈或多人辩论。

![探索模式](assets/demo/mode_1_exploration.gif)

**02 · PMF 验证 — Sean Ellis 量表，≥40% 即通过**

用真实用户数据对你的产品假设进行压力测试，量化 PMF 评分。

![PMF验证](assets/demo/mode_3_pmf_validation.gif)

**03 · PRD 校准 — 4维评分 + 数据验证方案**

多用户视角对需求文档进行对抗性评审，给出数据支撑的改进路径。

![PRD校准](assets/demo/mode_4_prd_calibration.gif)

**04 · 指标投票 — 上线前指标预估**

虚拟用户面板预估点击率、留存率、转化率等业务指标。

![指标投票](assets/demo/mode_5_metrics_voting.gif)

**05 · 辩论赛 — 多视角对抗**

两组用户对你的功能方案展开正反辩论，产出综合报告。

![辩论模式](assets/demo/mode_2_debate.gif)

---

## 快速开始（3步）

```bash
# 1. 克隆并安装
git clone https://github.com/chuxin-wenxiang/virtual_user_skill.git
cd virtual_user_skill
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. 初始化加密密钥
python src/encrypt.py

# 3. 提出你的第一个问题
python src/main.py "用户预订机票时最关心什么？"
```

系统会返回 8-10 个用户类型，你可以选择其中任意几个进行多轮对话。

---

## 使用场景

| 模式 | 适用场景 | 产出 |
|---|---|---|
| **探索** | "X 的用户全景是什么样的？" | 8-10 个差异化用户画像 + 痛点、情感标签 |
| **PMF 验证** | "这个需求真的存在吗？" | Sean Ellis 量表评分 + 置信度分级 + 风险评估 |
| **PRD 校准** | "用户真的会用这个功能吗？" | 4维度评分 + 数据验证方案 |
| **指标投票** | "点击率/留存率会是多少？" | 上线前业务指标预估 |
| **辩论赛** | "这个功能正反方观点是什么？" | 多视角对抗 + 综合报告 |

---

## 工作原理

```
你的问题
    ↓
[1] 在 54,631 条脱敏场景上做向量检索
    ↓
[2] Top-k 检索结果 → 聚类为差异化用户画像
    ↓
[3] LLM 生成完整虚拟用户（姓名、背景、痛点、情感）
    ↓
[4] 你选择一个或多个 → 多轮对话
    ↓
[5] 自动生成洞察报告（Markdown / HTML）
```

- **检索**: 768维 `text2vec-base-chinese` embedding，预计算
- **存储**: Fernet 加密场景库（隐私优先）
- **生成**: 可插拔 LLM（默认 GPT-4 级别，OpenAI 兼容 API）

---

## 数据

内置 `scenario_library.json.enc` 包含 54,631 条脱敏用研场景，覆盖 13 个字段：

`user_name | user_background | content_scope | is_outbound_travel | scenario | task | expected_outcome | current_solution | delight_points | pain_points | improvement_directions | underlying_needs | emotion_tags`

所有可识别个人信息已脱除。数据在磁盘上加密存储，密钥在首次运行时本地生成（`~/.virtual_user/.key`），不会上传或分享。

`data/sample_scenarios.json` 中有 50 条未加密样例，方便你在运行前查看数据结构。

---

## 对比

| 方法 | 真实感 | 多样性 | 偏差风险 | 成本 |
|---|---|---|---|---|
| Prompt 工程角色扮演 | 低 | 低（LLM 趋同） | 高 | 免费，快 |
| 真实访谈 | 高 | 中 | 低 | 慢，贵 |
| **virtual_user_skill** | 中高 | **高（数据驱动）** | **低（真实声音）** | 一次性配置 |

---

## FAQ

**这能替代真实用户访谈吗？**
不能。它是快速初筛工具——最适合在正式招募之前压力测试想法。真实访谈在全新领域仍不可替代。

**可以用自己的数据吗？**
可以。`scripts/prepare_data.py your_data.xlsx` 支持导入任何符合 13 字段 schema 的表格。

**支持什么语言？**
内置数据是中文旅行 App 场景，embedding 针对中文优化。英文/多语言支持在 roadmap 中（欢迎 PR）。

**数据真的脱敏了吗？**
是的。所有姓名、地点、日期和标识符在加密前已移除或替换。

---

## Roadmap

- [ ] 英文场景库
- [ ] CLI 模式（CI 集成）
- [ ] Web UI（Streamlit）
- [ ] 跨领域迁移（电商、金融、SaaS）
- [ ] 与真实用户的对比评估框架

欢迎到 [Issues](https://github.com/chuxin-wenxiang/virtual_user_skill/issues) 提需求或投票。

---

## 贡献

欢迎贡献，特别是：
- 垂直领域场景库（电商、金融等）
- 多语言 embedding
- 新的使用模式模板

---

## 许可证

MIT — 详见 [LICENSE](LICENSE)。

如果这个工具帮你节省了研究时间，点个 ⭐ 是最好的支持。


---

[English version](./README.md)
