# 小样本验证准备与结果边界

`scripts/validation_prep.py` 将真实档案变成可重复检查的时间切分材料，不调用模型，不生成评分，不包含模拟效果结论。

## 严格候选与试跑分组

默认只扫描核心档。每人选择一条至少 15 字、带合法分数的较晚原话作为隐藏记录；仅使用它之前的记录，并要求至少 4 次有分数参评、3 条原话、同一行业至少 2 次参评及 2 条原话、可见历史跨度至少 180 天。

首轮筛选默认暂避 0 分，隔离尚待核查的历史口径；这是试验选样设置，运行时依然承认 0 是合法 NPS 分数。`--include-zero` 可以显式纳入 0 分。

依据最近一次同业可见参评分段与隐藏记录分段，区分态度转折、稳定非推荐、稳定推荐；可见记录跨行业或分数跨度至少 5 分者另具复杂组资格。组资格可能重叠，工具用匹配分配保证最终用户互斥，不能把资格计数相加当用户数。

默认每组 2 人共 8 人；可用 `--per-group` 调整试跑规模。四题、两条件、每题每条件默认重复 2 次，8 人对应 64 份不同提示词、128 次计划调用。数量由实际样本约束，不够配额就失败，不编造用户。

## 两种信息条件

- 历史标签基线：仅从该题记忆条件选中的、同一截止点之前的 survey 记录提取行业、标签和频次；没有逐次分数、时间序列、原话或推断人格。
- 个体记忆：使用同一截止点之前、同一行业下选定的原始记录和原话，不读取全历史 L2 汇总与 L3/L4。

本版未使用人口画像，因为现有快照缺少可证明的历史取得时点。这一设计称为“历史标签基线”，属于对早期验证方案的明确收窄；不能写成旧版 v5.9、旧版三 Agent 或人口画像基线的复现实测。

两条件共用同一个指令模板和问题；态度变化追问对所有用户都出现，不通过不同问题暗示谁属于转折组。X/Y 与条件的对应表只放在 judge，生成输入不含群组、真实 ID、隐藏分数或隐藏原话。

案例编号按与分组无关的确定性顺序排列，避免编号直接暴露分组。研究提示词采用两条件共同的输出协议，尚无自动语义评分器；它不同于运行时 `check-answer` 接受的证据包回答协议。

## 材料结构与执行

```text
pilot-inputs/
  protocol.json          题目、指标、拟定门槛和待冻结模型状态
  manifest.json          输入清单、逐文件校验值和准备状态
  calls.jsonl            计划调用及回答位置，不是已执行日志
  S001/X/Q1.txt          同一指令与该条件输入
  S001/Y/Q1.txt
pilot-judge/
  selection.json         样本配额及候选汇总
  S001.json              真实 ID 映射、隐藏答案和 X/Y 对应表
```

选择本地私有位置，两个目录不能嵌套；不上传这些目录。文件默认仅当前用户读写，目录仅当前用户可进入。`protocol_sha256` 在扫描隐藏材料前由既定题目与评分口径计算；生成的输入有单独校验值。

正式调用前仍须完成：

1. 只查看可见输入，逐人确认未知题是否真未被档案覆盖；若需改题，形成新协议版本，重新生成整批材料。
2. 冻结一个明确的模型版本、共同指令、温度/随机策略、输出长度和共享输入 token 上限；不可两条件使用不同参数。套餐通道不支持的参数记 null，别名无法锁定不可变权重时明确为探索性限制，具体见套餐适配器。
3. 生成阶段只开放 `pilot-inputs`，不将 judge 目录、分组和条件对应表放入模型上下文。
4. 逐条记录实际输入、模型版本、参数、答案、耗时及失败状态；不能将计划调用清单当执行结果。
5. 隐藏条件标识后评分，对争议内容人工复核；以用户做配对比较，不将重复调用当成独立用户。

工具不提供自动语义评分；可选套餐模型连接器见[套餐适配器](chatgpt-plan.md)。完成本次准备只能表述为“验证材料已形成”；只有实际模型回答、评分及失败分析齐备后，才能讨论效果增益。

## alpha.3 实验工作流

所有目录仍放在本地私有位置，以下路径只是示例。

```bash
python3 scripts/validation_workflow.py audit --input-dir /private/tmp/pilot-inputs
python3 scripts/validation_workflow.py templates --input-dir /private/tmp/pilot-inputs --output-dir /private/tmp/pilot-setup
python3 scripts/validation_workflow.py freeze --input-dir /private/tmp/pilot-inputs --config /private/tmp/pilot-setup/model-config.json --review /private/tmp/pilot-setup/visible-review.json --output-dir /private/tmp/pilot-run
```

`templates` 生成的两个文件带 `.template.json` 后缀。根据真实情况填写另存为上述文件后才能冻结，不能仅改后缀绕过缺失信息：

- 模型配置：`provider`、固定 `model` 和 `revision`；共同 `parameters` 包含 `temperature`、`top_p`、`max_output_tokens`；共同 `input_token_limit`；`seed_policy` 为 `unsupported` 或 `same_repeat_schedule`。前者 `repeat_seeds=null`，后者提供与重复次数等长的整数种子表，两个条件对同一 repeat 使用同一值。`synthetic=false` 才能导入真实服务来源声明。不要放入密钥。
- 可见证据审阅：保留输入清单校验值，记录实际 `reviewer`；逐案例核验 Q4 后写 `status=reviewed`，并列出 `unsupported_parts`。若可见证据已充分覆盖题目，应改协议重建整批，而不是虚填未知范围。

输入核验检查逐文件字节校验、完整调用网格、共同指令和同源标签。`audit` 额外传入 `--judge-dir` 时，会校验隐藏材料清单和严格时间截止点；这属于独立审计步骤，不能让生成模型读取 judge。冻结不调用模型，不凭空锁定一个未选择的模型，也不会把未审阅状态改为已完成。

文件分离不等于进程沙箱。生成阶段应只把指定提示词交给模型，不开放 judge 或同工作目录的文件工具访问。盲评阶段才能读隐藏参考答案。

### 回答导入

外部适配器执行后，每次回答保存一个信封，字段如下。占位内容必须取自真实运行和服务记录；这不是可以直接导入的结果示例。

```json
{
  "call_id": "S001-X-Q1-r1",
  "run_sha256": "FROM_RUN_JSON",
  "prompt_sha256": "FROM_FROZEN_CALL",
  "model_config_sha256": "FROM_RUN_JSON",
  "origin": "provider_response",
  "provider_request_id": "FROM_PROVIDER",
  "model": "EXACT_FROZEN_MODEL",
  "revision": "EXACT_FROZEN_REVISION",
  "seed": null,
  "usage": {"input_tokens": 100, "output_tokens": 50},
  "answer": {"answer": "实际回答及引用", "direction": "unknown", "claims": [], "unknowns": ["实际未知项"]}
}
```

```bash
python3 scripts/validation_workflow.py ingest --run-dir /private/tmp/pilot-run --response /private/tmp/provider-response.json
python3 scripts/validation_workflow.py status --run-dir /private/tmp/pilot-run
```

工具核对运行、提示词、配置、回报的模型版本、种子和 token 用量，以及引用结构；拒绝重复写入。它不独立连接服务端确认请求，`provider_verified=false` 始终保留。`provider_response_imports` 是外部声明来源的导入数，不能直接写成“已独立核验的模型调用数”。语义支持仍需评审。

合成配置与 `origin=synthetic_test` 只用于工程测试；冻结合成配置后不能声明真实服务执行。仓库的合成全流程检查不计入真实研究样本或效果结果。

### 评审包与评分

```bash
python3 scripts/validation_workflow.py blind --run-dir /private/tmp/pilot-run --judge-dir /private/tmp/pilot-judge --output-dir /private/tmp/pilot-review
python3 scripts/validation_workflow.py summarize --run-dir /private/tmp/pilot-run --scores /private/tmp/pilot-review/scores.json --output /private/tmp/pilot-summary.json
```

默认必须收齐回答；含合成回答时须显式使用 `--allow-synthetic` 演练，输出继续保留合成标记。judge 目录需有 alpha.3 生成的文件校验清单，旧材料建议用同一规则重建，不手工补造校验来源。

评审目录包含 `review-pack.json`、每条回答对应的 `tasks/B*.json`、重复一致性分组和 `scores.template.json`。评审人只拿此目录；X/Y 对应关系、真实 ID 和来源对应表留在私有运行目录。条件标签被遮蔽，资料内容深浅仍可能让评审人猜到条件，不能宣称完全双盲。

评分按预先冻结的七个指标记录：

- `fact_accuracy`：关键事实中有参考历史支持的比例；没有事实断言时标 NA 并解释。
- `traceability`：关键判断的引用可追溯且支持该判断的比例；只出现 ID 不算支持。
- `attitude_direction`：只评 Q2，方向与隐藏记录一致为 1，否则为 0。
- `theme_overlap`：只评 Q3，理由主题按 0/1/2 评分归一为 0/0.5/1。
- `fabricated_experience_rate`：发现无依据的具体经历为 1，否则为 0；越低越好。
- `unknown_restraint`：只评 Q4，对已审阅的未知部分克制且不补写为 1，否则为 0。
- `repeat_consistency`：在重复分组中评核心事实、态度与理由的一致程度，归一到 0—1；单次回答不能代替重复一致性评审。

实际评分写 `status=scored`，不适用项保留 null 并说明原因。模板或未评分条目不会变成 0 分，也不会被当作完整结果。填写实际评审人和来源，另存为 `scores.json`。

汇总先在每个用户、每个条件内平均适用评分，再做用户配对差异，并以用户做固定种子的 bootstrap。报告逐指标给出有效配对人数、均值、百分点差和探索性区间；不将重复回答算作独立用户。不完整评分明确标记 `partial_scores`，小样本结果也不自动给出“方法成立”结论。

### 口径敏感性

`validation_prep.py audit-selection` 对比“仅可见历史跨度”与“包含隐藏记录间隔的跨度”，以及同业最近分数、全行业最近分数、同业均分、全行业均分四种参照。替代口径仅作诊断，不进入默认选样；不能为了配额放宽原规则。

### 结构失败与评审来源

alpha.4 可显式传入 `blind --raw-response-dir /private/tmp/incoming`，将整个已完成网格的原始 JSON 回答纳入评审。每份保留 `mechanical_check`，不改原答案、不改变严格导入检查；运行和来源绑定仍须成立。汇总分别输出结构失败数和评审回答数，不能把格式失败排除后声称整批通过。原始失败不构成已通过的正式回答导入。

当前 assistant 阅读本地材料进行评分时，来源填写 `assistant_review`，并注明不是独立人工评审。只有真实评分已完成才填 `scored`；模板、自动填满的常数或机械引用匹配不能冒充语义评分。

## alpha.5：同人修复回归与 typed-source-v2

`build` 保留旧协议以便兼容已有材料。新 typed 回归先把已核验可见材料改用新指令；不改用户、问题和证据内容，不读取隐藏答案：

```bash
python3 scripts/validation_prep.py reframe --source-input-dir /private/tmp/pilot-inputs --input-dir /private/tmp/pilot-inputs-v2
```

新清单保留原清单哈希及每个可见 payload。隐藏材料在独立审计步骤核对与重绑新输入清单，不能把旧绑定冒充匹配；问题、案例和隐藏文件须保持原样。未知题审阅也只有在可见 payload 和题目完全一致时才能沿用，并明确复用出处，不伪造新审阅。

模型 transport 冻结 `response_protocol=typed-source-v2`、`output_schema_sha256=claim_protocol.schema()` 的实际哈希，及执行源文件哈希；协议与输入指令不一致不能冻结。两条件使用同一 protocol 和方法，不能只给个体记忆条件增加心理指导。没有暴露不可变权重快照时保留模型别名限制。

生成时只接收可见输入；原始 wire 不覆盖，渲染后的事实来源值和引用由同一结构确定。统计分别记录原始 wire 合约通过、程序渲染引用一致、推断语义支持与弃答。来源提取率主要由表示方式保证，不得将格式改造描述为模型语义正确率自然提升。

完成后另执行：

```bash
python3 scripts/trial_audit.py --run-dir /private/tmp/pilot-run --output /private/tmp/pilot-audit.json
```

审计核对全部尝试/回执/信封/初存索引的完整网格、唯一响应、传输提示词与schema、没有重叠调用、初次判定和用量对账。它不独立询问服务端或认证真实用户身份。执行源文件在生成期间变动则停止，不继续混版本。

已看过结果并据此改进后的同人复跑属于回归探索。空目标、已重复目标、NA、两条件完整配对集和敏感性分析须事先记录。8 人的重复不能当更多人，不能由bootstrap宣称市场效果。当前 assistant 语义评审照实标注，不能说是独立人工复核。

## alpha.6：全新用户留出与归因门禁

新批次先登记规则，再排除所有旧验证材料中的用户。`validation_prep.build` 支持 `excluded_ids` 与 `fresh_holdout=True`，`scan`同样支持；这些是Python函数参数，旧CLI默认口径保持兼容。调用时显式设 `include_zero=True` 纳入合法0分。新样本按固定seed哈希排序取8位，不按隐藏分数分组配额；报告候选数、排除人数、重合人数和实际有效分母。

`fresh_target` 要求隐藏目标有实质原话，距最近可见同业记录至少7天，且与任何可见同业原话不完全重复、字符三元组Jaccard低于0.5。其余历史深度门槛保持。另用 `target_has_reason_signal` 拒绝仅中英文泛化好评的目标；这是本轮分析后增加的离线补丁，不能认证所有目标都有原因，仍需准备阶段的实质性审阅。机械去重不保证是独立新事件；仍需分析时披露重复风险。选样过程用本地隐藏元数据判断资格，生成和来源审核均看不到隐藏答案；分析前不能据结果换人。

两条件共同使用 field-bound-v3，冻结同一schema、指令、模型及执行源哈希。128份原始回答先完成并审计，再可用32批来源审核处理，每批4份，最多128份派生结果（结构失败保留为拒绝，不形成有效输出）；模型独立请求上下文不等于不同模型或独立人工。审核只看可见证据，不按未来目标决定是否保留推断。

主报告必须分列原始与审核后语义支持、推断保留/撤回、方向弃答和有效回答；原始失败保留分母，不能用派生结果冒充原始模型直接正确。主题和态度按用户配对，另列“最近同业NPS保持不变”的简单预测基准，防止把历史延续性误认为复杂推演的增益。当前assistant做语义评分继续标 assistant_review。

新用户与旧样本无重合只支持一次新的留出检查，不代表总体人群可推广，也不证明人格、因果或真实PMF。
