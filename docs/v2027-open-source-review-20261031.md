# v2027：GitHub 同类项目审阅与升级建议

审阅日期：2026-10-31（Asia/Shanghai）。对应调研时发布版：[v2027.0.0-alpha.9](https://github.com/chuxin-wenxiang/virtual_user_skill/releases/tag/v2027.0.0-alpha.9)。本文是公开代码、作者论文与方法的比较，以及升级方案与后续实现范围；没有运行这些项目，也没有新增模型请求、购买服务或复制第三方代码。

最值得借鉴的是 Stanford 的真人个体代理验证方法、TinyTroupe 的实验与验证分层，以及 τ-bench 的场景约束和可核验任务。它们分别改善“凭什么代表这个人”“怎样证明有效”和“怎样限制越界回答”。没有找到足以证明其在我们的稀疏历史 NPS 任务上更有效的同条件结果；项目知名度、自然对话和群体分布相似都不能替代这种证据。

## 先把本项目状态说清楚

alpha.9 已发布，139 项离线检查通过，新 8 人的 128 次生成全部完成，108 次通过原始严格契约。来源审核在第 3 批连接错误后停止，仅 8/128 份得到最终结果，120 份缺失；没有重发或恢复后续模型请求。不能宣称完整独立验证通过，也不能把本地评分回填成模型审核结果。[本轮汇总与限制](../skills/authentic-user-v2027/references/pilot-20261030-scope.md)。

全部原回答共 364 条判断，当前实现 assistant 评分为 343 条充分支持、18 条部分支持、3 条不支持；评审者不独立。个体记忆的原始态度命中为 6/16，最近同业 NPS 延续为 7/8 人，按相同两次重复展开为 14/16。原始原因主题分较好，但优势受标签条件结构失败影响，事后只比较内容时差异缩小。来源审核后的零散子集不足以判断效果是否改善。[具体分母、争议与敏感性分析](../skills/authentic-user-v2027/references/pilot-20261030-scope.md)。

旧轮剩余的 3 条支持不足已归为证据范围越界，原记 5 条误撤重新分为 4 条明确的未来条件误撤、1 条属性粒度争议；修复有工程和合成回归证据，真实新用户上的新边界政策触发效果仍未验证。下一轮应同时解决证据选择和验证设计，不能仅以增加审核层数作为升级。

## 五项值得看的项目

下表中的“证据”指项目已经公开展示的研究或工程能力，不表示我们独立复现过。许可证指本次核对的仓库根许可证；参与者资料、模型与其他依赖仍需分别确认使用条件。

| 项目 | 与我们的关系 | 已有证据与边界 | 最值得借鉴 | 根许可证 |
|---|---|---|---|---|
| [StanfordHCI/genagents](https://github.com/StanfordHCI/genagents) | 最接近“依据某个真人资料模拟同一个人” | 作者研究使用真人自述、留出题与本人复测；GitHub 示例代码与最新论文版本不能混同 | 原始记忆与反思分型、来源指针、同人留出和信息来源消融 | [MIT](https://github.com/StanfordHCI/genagents/blob/96854071ef4c2d79c93144c973c7820722d52bab/LICENSE) |
| [microsoft/TinyTroupe](https://github.com/microsoft/TinyTroupe) | 贴近产品方案讨论、消费者模拟和实验 | 有工具包、实验与初步真人对照；README 仍明确属于实验性项目 | 分开检查角色一致性、来源质量和真实结果；受控实验与费用记录 | [MIT](https://github.com/microsoft/TinyTroupe/blob/7ce8be378a37ee73f9745d6781452712318afa04/LICENSE) |
| [sierra-research/tau2-bench](https://github.com/sierra-research/tau2-bench) | 适合借鉴用户模拟与评测工程 | 在有工具、共享状态的服务任务里验证；不是某个真人的态度预测研究 | 统一场景指令、已知信息边界、可核验的任务结果与错误拆分 | [MIT](https://github.com/sierra-research/tau2-bench/blob/da0835f6c67baef58bdda18f2a3b037dfb3a1754/LICENSE) |
| [joonspk-research/generative_agents](https://github.com/joonspk-research/generative_agents) | 提供经典的记忆检索与反思思路 | 2023 年 Smallville 模拟，与上面的真人个体研究是不同项目 | 按问题检索相关历史；把反思与观测区分保存 | [Apache-2.0](https://github.com/joonspk-research/generative_agents/blob/fe05a71d3e4ed7d10bf68aa4eda6dd995ec070f4/LICENSE) |
| [tsinghua-fib-lab/AgentSociety](https://github.com/tsinghua-fib-lab/AgentSociety) | 更适合社会互动和研究流程编排 | 当前仓库推荐 v2，论文有多层次社会实验示例；不证明稀疏个人历史预测有效 | 实验配置、执行轨迹、回放和环境边界 | [Apache-2.0](https://github.com/tsinghua-fib-lab/AgentSociety/blob/3d359288d3c513f6c9f77afbaa9c16e205693f83/LICENSE) |

## 读到代码层面后，可以怎么借鉴

**1. Stanford：借验证方法，谨慎使用“反思”。** 最新作者论文 v3 对 1,052 人比较访谈、结构化调查与两者结合。在留出 GSS 题上，三者准确率分别相当于本人两周复测一致性的 83%、82%、86%，人口属性条件为 74%。这些是相对本人复测的比值，不是通用绝对准确率。论文还筛查访谈与留出题的近重复，并移除 27 项；这说明不能只检查隐藏答案文件没有传出，还要排查问题本身已被输入材料回答的情况。[版本固定的论文摘要](https://arxiv.org/abs/2411.10109v3)、[方法与去重说明，PDF 第 11–12 页](https://arxiv.org/pdf/2411.10109v3)。

源码 `MemoryStream` 有 observation/reflection 类型；`reflect()` 将反思保存为独立节点，并带父记录 `pointer_id`。`retrieve()` 可按类型过滤，但默认 all 会混合两种内容，交互函数又将检索结果放入同一个上下文。这是可追溯的起点，尚不等于每条推断均被原话支持。[memory_stream.py](https://github.com/StanfordHCI/genagents/blob/96854071ef4c2d79c93144c973c7820722d52bab/genagents/modules/memory_stream.py#L309)、[interaction.py](https://github.com/StanfordHCI/genagents/blob/96854071ef4c2d79c93144c973c7820722d52bab/genagents/modules/interaction.py#L17)。

对 v2027 的启发：历史原话、脚本提取的事实、模型概括、待验证假设继续分开，反思只能指回原来源，不能作为“真人又提供了一条事实”再次进入档案。心理学概念可以帮助组织假设和提问，不能凭人口属性、一次差评或少量语料推定稳定人格。我们目前缺少本人同期复测，不能照搬论文的归一化分数；近期先诚实比较简单基线，后续有新实测才能估计可靠性上限。

**2. TinyTroupe：验证层次值得借鉴，综合分不直接照搬。** `SimulationExperimentEmpiricalValidator` 将模拟与经验数据比较，并同时支持统计与语义结果；源码的 overall score 是组合规则，某些情况下统计与语义按 70%/30% 加权。这个分数不是个人预测准确率，也不能将差异检验“不显著”解释成已证明等效。[验证器源码](https://github.com/microsoft/TinyTroupe/blob/7ce8be378a37ee73f9745d6781452712318afa04/tinytroupe/validation/simulation_validator.py#L900)。作者论文亦将真人对照描述为初步实验。[论文 v3](https://arxiv.org/abs/2507.09788v3)。

对 v2027 的启发：报告并列展示来源忠实度、有效回答覆盖、重复一致性和真实留出命中，不折成单一“仿真度”。先按用户汇总，再比较条件，保持重复回答与独立用户的分母区别。若未来要检验等效，应事先定义业务可接受差异和分析方案；8 人探索结果不承担这种认证。

**3. τ-bench：用户知道什么、任务发生了什么，应有明确边界。** 当前 `build_user_system_prompt()` 为运行和离线审阅共用指令拼装；`UserSimulator` 明确列出全局、任务与运行时 persona 三个控制位置，要求一致。guidelines 限制模拟用户只使用场景明确给出的信息。[user_simulator.py](https://github.com/sierra-research/tau2-bench/blob/da0835f6c67baef58bdda18f2a3b037dfb3a1754/src/tau2/user/user_simulator.py#L40)、[guidelines.py](https://github.com/sierra-research/tau2-bench/blob/da0835f6c67baef58bdda18f2a3b037dfb3a1754/src/tau2/user/guidelines.py#L76)。原始 τ² 论文通过共享环境、工具和可观测状态约束任务，并拆分推理与沟通问题；当前 main 已增加后续语音、多语言能力，不能将整个 main 称为原论文快照。[τ² 论文](https://arxiv.org/abs/2506.07982)、[本次仓库快照](https://github.com/sierra-research/tau2-bench/tree/da0835f6c67baef58bdda18f2a3b037dfb3a1754)。

对 v2027 的启发：继续统一 Skill、宿主指令、批试提示和审核契约；用户已知事实、产品方案假设、真实结果分别管理。退款到账、赔付金额等客观项目优先用数据或任务状态核验。场景未提供就保留未知；未来条件可用于探讨，但不能回写成此人的过去。审核判断可以解释结果，不能更改留出真值。

**4. 2023 Smallville：借问题相关检索，避免把“重要”当成“真”。** `new_retrieve()` 将相关性、最近访问和重要性组合排序；代码同时检索事件与想法。它解决的是模拟世界里记忆使用问题，不是逐条事实认证。[retrieve.py](https://github.com/joonspk-research/generative_agents/blob/fe05a71d3e4ed7d10bf68aa4eda6dd995ec070f4/reverie/backend_server/persona/cognitive_modules/retrieve.py#L197)。

v2027 已有 `select_records()`，按词项重合、日期等确定性规则选记录，并有来源哈希。可改进的重点是保留完整的评分—标签—原话关联，以及多前提判断所需的全部来源，不能只提升向量相似度。先用本地规则做有解释的重排和覆盖检查，不引入付费 embedding。对“经常”“一直”“没有提及”这类范围断言，检索到几条相关记录不能代表全部历史。

**5. AgentSociety：借回放与实验配置，暂不引入完整平台。** 当前 v2 文档将环境、模型、轨迹和回放放在统一运行边界内；论文展示七项不同尺度的研究案例。[固定快照 README](https://github.com/tsinghua-fib-lab/AgentSociety/blob/3d359288d3c513f6c9f77afbaa9c16e205693f83/README.md#L55)、[作者论文 v2](https://arxiv.org/abs/2607.11895v2)。

对 v2027 的启发：保留输入、版本、原始候选、请求状态和评分变化的可回放记录。我们已有冻结与回执，应补足中断状态展示和完整性验收；Ray、城市环境和整套研究编排不适合直接加入轻量 Skill。

## 建议的下一轮顺序与验收

下表保留最初的升级方案。后续alpha.10已实现同记录字段映射、只读中断清单和Q2事后基线计算，详见[离线改进记录](../skills/authentic-user-v2027/references/offline-20261031-evidence-map.md)。alpha.11进一步实现问题锚点与最近背景检索、并列评分消歧及单记忆臂网格，见[实现与准备状态](../skills/authentic-user-v2027/references/context-20261031.md)。alpha.12已补齐alpha.11冻结算法的[新8人完整结果](../skills/authentic-user-v2027/references/pilot-20261031-context.md)：64次生成、16批审核完成，但态度命中仍低于简单NPS延续。alpha.13进一步实现[态度估计、条件反应和基线分离](../skills/authentic-user-v2027/references/decision-20261031.md)及脚本提取引文，199项工程检查通过；之后alpha.13冻结的新8人完成64生成/16批审核，Q2仍低于简单基线，alpha.14据此做工程修复而未重跑模型，见[本轮结果](../skills/authentic-user-v2027/references/pilot-20261031-decision.md)。独立人工评分与预测优势未成立；原alpha.9缺失不回填，不能将工程实现视为整张清单已验证有效。

| 优先级 | 实际改动 | 验收与限制 | 模型/费用影响 |
|---|---|---|---|
| P0 证据关联与选择 | 在现有记录和哈希上建立可追溯的证据卡：日期、记录关联、字段、原值；概括另存为推断。每条判断显式列出全部前提来源 | 用合成反例和已见失败作回归：单个 0 分不能单独支持某类问题；评分、原话不一致时并列保留；多前提漏选须显式待核验。脚本只保证关联、范围和覆盖，语义充分性仍需审阅 | 本地脚本可先做；不新增外部 API |
| P0 范围与时间 | 缺资料的说明由所选记录范围和结构化状态呈现；模型假设与历史断言保持分型；时间截止、行业与选择范围显式保存 | 未选字段不作来源；局部缺失不推成全部历史不存在；纯未来条件不误判成已发生事实；不得通过类型标签绕过实质前提 | 可先离线核对与回归 |
| P1 评价与基线 | 将来源支持、分类覆盖、命中、原因内容、交付有效性分开；保留最近同业 NPS 延续、固定类别等基线 | 先冻结口径与阈值；未知单列且不算命中；每用户汇总，不能把 128 次回答当 128 个独立样本；事后分析明确标注 | 指标计算无需模型；独立评审需人员安排 |
| P1 中断完整性 | 完成/失败/服务端状态未知/未尝试分别记录，最终报告由清单检查覆盖。任何恢复都先核对本地回执和服务状态 | 不能静默重发未知请求，不能由本地评分填补外部审核；不保证网络层“恰好一次”。本轮保持停止，不在调研中重开 | 离线状态检查可做；恢复前仍须确认套餐路径和额度 |
| P2 新独立验证 | 冻结修复后，再登记未用过的人、目标、时间间隔、排除和预算；原来的新 8 人此后只用于回归 | 在独立样本上同时看支持不足、误撤和预测基线；若未超过基线，限制用途与结论，不据来源分数宣布可替代真人 | 仅用已确认的现有套餐；不够即停，不引入按量付费后备 |

设计上继续让安装者的宿主模型执行模拟和审核，确定性取数与统计交脚本。复用这些方法不要求安装整套框架、购买模型 API 或建立额外付费服务；实际耗用仍取决于安装者所选宿主及其计费方式。未来真人资料外发按明确授权范围处理，公开仓库只留合成示例、代码和汇总结果。

## 版本记录，避免把不同代项目混为一谈

下列是本次读取 main 的提交，后续复核应使用固定链接。Stanford 示例代码和 2023 Smallville 的提交较早，不能因此把较新论文的全部实现和结果归到这些旧快照；TinyTroupe 的 README 新闻也不等于最新提交版本公告。

| 仓库 | 本次固定提交 | 提交日期（UTC） |
|---|---|---|
| StanfordHCI/genagents | [96854071ef4c](https://github.com/StanfordHCI/genagents/tree/96854071ef4c2d79c93144c973c7820722d52bab) | 2024-11-18 |
| microsoft/TinyTroupe | [7ce8be378a37](https://github.com/microsoft/TinyTroupe/tree/7ce8be378a37ee73f9745d6781452712318afa04) | 2026-10-23 |
| sierra-research/tau2-bench | [da0835f6c67b](https://github.com/sierra-research/tau2-bench/tree/da0835f6c67baef58bdda18f2a3b037dfb3a1754) | 2026-10-30 |
| joonspk-research/generative_agents | [fe05a71d3e4e](https://github.com/joonspk-research/generative_agents/tree/fe05a71d3e4ed7d10bf68aa4eda6dd995ec070f4) | 2023-08-11 |
| tsinghua-fib-lab/AgentSociety | [3d359288d3c5](https://github.com/tsinghua-fib-lab/AgentSociety/tree/3d359288d3c513f6c9f77afbaa9c16e205693f83) | 2026-10-30 |

本轮只借鉴方法和架构，不移植代码。若后续采用第三方实现，应固定来源提交并保留相应许可与署名；论文、数据和访问服务分别按其条件处理。这份调研不改写已发布 alpha.9 的源码、安装包或实验结果。


## 同日补充：Concordia与已完成新协议试验

另阅读[Concordia官方组件与引擎说明](https://github.com/google-deepmind/concordia/blob/main/CHEATSHEET.md)：其问卷引擎区分写回记忆的顺序问答和批次中不改记忆的无状态问答。这提示我们应继续把独立重复请求与多轮访谈分开；前次代理回答不能自动变成下一次的真人资料。组件组织可供参考，本轮没有安装该框架、复制代码或增加模型调用。

本项目的新协议试验已经完整结束；发现机械关键词拦截、错栏类别估计、未知代码冲突及来源覆盖索引缺失。alpha.14已作局部修复和213项工程检查；来源支持、交付覆盖和留出命中继续分别报告，未复用变更前审核或宣称新预测增益。下一步需要独立来源校准及可见历史有变化的挑战样本，稀疏短评没有区分力时应补真实材料，而不是扩大模拟人格。原有固定论文版本及其相对复测分数保留，不以旧摘要中的85%替代版本差异。
