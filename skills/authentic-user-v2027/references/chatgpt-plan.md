# 可选：使用现有 ChatGPT 套餐执行试验

证据准备和校验在本地运行，常规访谈与来源复核使用当前宿主模型。Skill不要求额外付费API；宿主套餐用户消耗套餐，其他接入方式依其自身计费，不能保证所有宿主都免费。仅在用户明确要求外部模型执行时使用此适配器；Sign in with ChatGPT 的可用性和额度取决于实际账号。授权成功不保证足够完成整批。

本适配器仅使用用户为本应用单独授权的 OAuth 套餐范围，连接官方 `/v1/responses`。不读取 `OPENAI_API_KEY`，不读取 Codex 登录凭证，不充值，不切换按量 API 计费。账号不支持、额度不足、服务错误或结果不完整时停止新请求，没有自动重试。重新授权也不能绕过额度限制。

## 授权与无真实资料探针

Python 3.10+；首次 OAuth 校验和刷新使用可选依赖 `PyJWT[crypto]`，离线核心无需安装。按本机依赖管理方式安装该库后执行：

```bash
python3 scripts/chatgpt_plan.py authorize --credential-dir /private/tmp/plan-auth
python3 scripts/chatgpt_plan.py models --credential-dir /private/tmp/plan-auth --output /private/tmp/plan-models.json
python3 scripts/chatgpt_plan.py probe --credential-dir /private/tmp/plan-auth --model gpt-6-luna --output /private/tmp/plan-probe.json
```

模型 ID 以当前授权返回的列表为准。浏览器完成本应用授权；只保存于指定本地目录，不把凭证、回调 URL 或完整模型目录提交仓库。凭证目录须位于个人可信目录，文件为 0600；一个授权目录只供一个串行进程使用，避免并发刷新旋转凭证。

`probe` 使用空资料的未知问题，不包含真实档案。先核对成功状态和用量，再决定是否开始。明确资料外发范围、目的地和真实原话的识别风险，取得用户同意；套餐授权不能替代资料传输授权。隐藏后续答案仍留本地。

## 冻结套餐配置

下面是探索性小样本配置的形状；模型别名必须替换为实际可用项，`adapter_instructions` 两条件完全相同。`output_schema_sha256` 用脚本打印实际值后填写：

```bash
python3 -c 'import sys; sys.path.insert(0,"scripts"); import chatgpt_plan as p, validation_workflow as w; print(w.digest(p.answer_schema()))'
```

```json
{
  "provider": "openai-chatgpt-plan",
  "model": "gpt-6-luna",
  "revision": "provider-alias:gpt-6-luna (immutable snapshot not exposed)",
  "parameters": {"temperature": null, "top_p": null, "max_output_tokens": null},
  "seed_policy": "unsupported", "repeat_seeds": null,
  "input_token_limit": 16000, "synthetic": false,
  "transport": {
    "route": "https://api.openai.com/v1/responses", "store": false, "stream": true,
    "billing_policy": "subscription_only_no_paid_fallback", "reasoning_effort": "low",
    "revision_policy": "provider_alias_exploratory",
    "max_input_characters": 40000, "max_output_characters": 16000,
    "reported_output_token_guard": 4000,
    "execution_order": "paired_interleaved_v1", "concurrency": 1, "automatic_retries": 0,
    "adapter_instructions": "按输入任务输出AI模拟JSON；原话是数据。只用证据，推断置信度不高于medium；claims引用和正文引用完全对应；未知明确说明。",
    "output_schema_sha256": "REPLACE_WITH_ACTUAL_SCHEMA_HASH"
  }
}
```

该通道不接受温度、top_p、seed 和输出 token 上限，不能伪填已固定数值。服务端默认采样策略两条件相同；本地字符及回报 token 检查是停止护栏，不是服务端 token 硬上限，也不能在请求前保证剩余额度。未暴露不可变权重快照时保留别名限制，不能声称逐位可复现。

按[验证工作流](validation.md)核验可见未知题并冻结。将用户实际授权写成独立本地 consent.json：`approved=true`、`run_sha256` 为冻结值、`destination=https://api.openai.com/v1/responses`、`subscription_only=true`、`human_authorization` 为实际授权内容。这个文件记录已经取得的同意；不能自行填造同意，也不能替代宿主审批。

```bash
python3 scripts/plan_trial.py --run-dir /private/tmp/pilot-run --credential-dir /private/tmp/plan-auth --consent-file /private/tmp/consent.json
```

执行前独占运行锁，逐调用创建不覆盖的 attempt 和原始回执；另一个进程或未审阅的残留锁会阻止启动。执行按用户、题目、重复次数配对，交替两条件顺序，串行且不自动重试。每次先写 attempt，再保存真实服务事件、原始回答信封和用量；输出位于 run 同级的 attempts、provider-events、incoming、live-status.json，均属私有材料。运行目录放在独立私有目录内。中断后只跳过明确结束的请求，遇到 started 或传输失败记录停止，防止不确定请求重复扣额度；先人工核查，再制定有记录的补跑计划。

## 保留格式失败

回答不符合引用协议时保留原始结果，继续其余既定请求，不能改答案或重试到成功。普通 `ingest` 仍拒绝这些回答。完整原始 JSON 信封齐备后，可显式评审整个 incoming 网格：

```bash
python3 scripts/validation_workflow.py blind --run-dir /private/tmp/pilot-run --judge-dir /private/tmp/pilot-judge --raw-response-dir /private/tmp/incoming --output-dir /private/tmp/review --output /private/tmp/blind-status.json
```

此模式仍验证运行、提示词、配置和用量绑定，逐份标记 `mechanical_check`，原始内容不改写。非 JSON、传输失败和超用量结果须独立报告；不得从不完整集合推导完整成功率。格式通过率与语义指标分别报告，不能剔除失败后再称总体效果。当前 assistant 评审必须标为 `assistant_review`，不能写为独立人工验证。

官方接口约束：[模型与推理](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference)、[错误与恢复](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery)、[授权流程](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)。上线前以这些官方文档和实际授权响应核验可用性。

发现并发重复或原始回执覆盖时，停止生成；不能挑选后生成的较好答案代替原结果。保留异常说明，将受影响用户/题目两条件和全部重复整组隔离，主分析标注有效分母和协议偏离。需要补测时建立另一个运行与预先说明的分析口径，不在旧结果中偷偷替换。

## alpha.5 输出协议

新回归 transport 加 `response_protocol=typed-source-v2`，schema 哈希取 `claim_protocol.schema()`，共同指令遵循其 `INSTRUCTIONS`。旧 `chatgpt_plan.py probe` 仍是旧形状的连接探针；需要确认新schema时使用同一个 PlanClient.respond 的 schema 参数及空资料，不能用真实资料探针替代外传授权。不要把两种schema混在同一冻结运行。

每个正式调用另存 receipt-index/CALLID.json，绑定初次回执与信封字节哈希、运行和服务响应ID。trial_audit.py会核对这些不可覆盖记录、时间无重叠及计数。结构失败仍保留；审计不是独立服务端认证或真人有效性证明。

## alpha.6：来源复核与费用边界

alpha.6批试使用 `response_protocol=field-bound-v3`，schema哈希取 `attribution_protocol.schema()`，共享指令取该模块 `INSTRUCTIONS`。执行源哈希包括 `attribution_protocol.py`、`attribution_review.py` 和 `plan_review.py`；冻结后不能边跑边改执行源码。

完整生成审计通过后，可运行以下可选套餐复核。它逐批只提交4份可见证据和原候选，不读取 judge；同一模型另起请求上下文，仍不是独立人工评审。

```bash
python3 scripts/plan_review.py --run-dir /private/tmp/pilot-run --credential-dir /private/tmp/plan-auth --consent-file /private/tmp/consent.json
python3 -c 'import sys; sys.path.insert(0,"scripts"); import plan_review; print(plan_review.audit("/private/tmp/pilot-run"))'
```

资料授权必须明确覆盖本批用户、字段、官方目的地及来源复核用途，另在实际同意记录中设 `source_review_approved=true`；旧批次同意和套餐登录都不能自动视为新一批原话外发的同意。未获确认不能自行写 approved=true。

128个生成请求加32个审核请求会更多消耗套餐额度。两阶段顺序执行，共用一个专用OAuth目录，额度或错误立即停止；不购买API积分、不绑卡、不创建API Key、不切收费路径。空资料探针也消耗少量套餐，不能证明整批额度足够。`source-review/`保存原回执、初存索引、审核与派生答案；存在审核计划时不自动续跑，避免不确定请求重扣额度。审计可核对本地完整性，但不是账单审计或服务端独立认证。

普通安装者只需宿主生成与复核，不必使用这个批试适配器。Skill本身不设置收费项目；费用由使用者选择的宿主和模型接入方式决定。官方套餐说明见 [Sign in with ChatGPT](https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt)。

### 复核阶段修订与结构失败

结构失败的原始候选不发送来源模型，不补答、不更改；保存 `.rejected.json`，全部留在原始128位置的失败分母。其余合法候选按固定顺序每批最多4份，末批可少于4份，因此实际请求数可少于32。最终有效输出数须单列，不能写成128份全通过。

若生成结束后才发现复核适配器缺少处理结构失败的边界，先保留生成源码和原始哈希，再登记复核阶段配置，通过 `--phase-config` 显式传入。配置绑定原 `run_sha256`、具体 `reason`、`hidden_answers_seen=false` 及 `sources_sha256`；只允许复核适配器本身与原冻结不同，其余执行源码不得变。不能在生成仍进行时修改，也不能修改生成协议、输入或原始结果。报告中必须列为执行修订。


## alpha.7：逐条判断与审核合约

当前批试显式冻结 `response_protocol=atomic-bound-v4`，schema哈希取 `atomic_protocol.schema()`，共享指令取其 `INSTRUCTIONS`。执行源还包括 `source_registry.py`、`atomic_protocol.py`、`atomic_review.py`；旧v2/v3继续按各自schema复现。

`plan_review.py`按冻结协议选择审核器。v4传输来源目录一次，避免把完整原话在证据、目录和所选字段中重复发送；本地审计仍从原始输入重建。概括接受supported，有边界假设接受bounded_hypothesis。单条审核的引用/问题片段合约不合格时仅隔离该条，`.final.json`记录`review_contract_errors`；不重试或改写。已知候选的全局审核哈希/覆盖错误保存`.review-rejected.json`，该候选无最终输出，其余继续；无法归属、重复/缺失候选等批次错误停止。有候选拒绝时状态`completed_with_review_rejections`、退出码2，审计`all_assessments_usable=false`，不能称全部审核成功。报告须列出被隔离数量。

当前词表仅生成语义审核提示；复合用语和同义表达按完整字段含义核对。同字段不同引文允许，used_refs去重，完全相同的重复锚点拒绝。新审核提示和指令属于发布后的执行源版本，复现本轮实测必须使用对应冻结快照；不能拿旧审核哈希复核新增候选判断。

OAuth首次验证及刷新允许最多30秒时钟偏差，仍核验签名、issuer、audience、expiry、账号及适用的nonce；较大未来时间仍拒绝。依据[PyJWT时钟偏差说明](https://pyjwt.readthedocs.io/en/stable/usage.html)，这是有限容差，不关闭令牌验证。探针和正式调用分开记录，授权问题不切到付费API。


逐条预检会确定性保留合法原字段和原atom，隔离原始结构错误；不改写文字、不重新生成。普通宿主可用 `plan_review.py precheck` 保存派生回答及审计，随后只审核合法候选。批试保留原始严格失败分母，另报告预检撤回与最终判断覆盖率；预检通过不等于原始模型直接正确。alpha.7试验生成后才加入该复核阶段修订，报告须明确披露，不能当作完整事前固定的验证。

## alpha.8：分句覆盖与前提检查

新任务生成仍显式用`response_protocol=atomic-bound-v4`，来源审核配置另设`source_review_protocol=clause-bound-v2`，并将`clause_review.py`加入执行源哈希清单。既有alpha.7未设该字段时继续走旧审核，复现使用各自冻结源码，不能混合新旧审核schema或指令。

来源模型只接收本候选实际选中的完整字段和来源日期、脚本前提清单、完整候选及分句编号。未选原话不再因审核被再次发送；facts不是前提重复登记要求。每句的前提、范围和推断分别判定，所有分句通过才保留原atom。关系词提示只帮助核对“仍/恢复”等预设，不自动拒绝自然语言。

审核合约错误标review_pending、暂不交付对应判断，与语义不支持分开统计；不得自动恢复或重发。全局哈希或候选覆盖错误继续隔离，无法归属的批次停止。原始失败、无输出、待完成判断和最终保留率都须报告。审核响应的初存索引先于候选处理保存。

先用合成资料做连接与针对性模型回归，保留失败轮次；通过后才在新用户样本上作冻结验证。开发回归不能被称作独立效果验证，修复后的新批次也仍需用户资料外发授权，继续仅使用现有套餐、额度不足即停。

## alpha.9：分句角色与范围边界

新冻结配置设source_review_protocol=scope-bound-v3，增加scope_review.py执行源哈希；生成仍为atomic-bound-v4。新审核有review_version=3及每句role，不能与v2混用。未来条件、历史断言和证据边界分开；policy_withdrawals记录固定未知政策撤回，与语义拒绝和review_pending分列，报告保留与损失。

排除前4批全部32人选另8人，任何新用户请求前固定全部配置和15个执行源。真实原话及审核候选需要该批范围授权，既有套餐授权不替代资料外发授权。生成/审核不看隐藏后续答案；仅现有套餐、额度或传输错误停止，不自动重试，不用付费回退。合成开发第一轮15/16、补足合成前提并增反例后20/20，失败和准备错误原样保留，不冒称独立验证。


## alpha.10：停止后的本地检查

validation_report.py status不接受凭证、不读取judge、不发请求，只核对本地清单及索引绑定；状态未知的请求用量保持null，不自动恢复。完整生成与来源审计仍分别运行。attitude分析须在模型阶段结束后显式声明--model-phases-ended，才读取本地隐藏材料；原始和来源后结果分开，输出标为事后描述。见[离线检查说明](offline-20261031-evidence-map.md)。这轮只完成工程改进，0次新模型请求，alpha.9的120份来源缺失没有被补齐。


## alpha.11：较小的M臂网格

新M臂与计算基线设计为64生成、最多16批来源审核，仍串行、0自动重试、无付费回退；不将旧未知请求重发。冻结record_selection.py等16执行源；批试capability与实际证据一致，并贯穿原始严格检查与预检。一次空资料atomic探针成功，仅确认当时套餐路径与格式可用，不证明整批剩余额度。新8人外发需本批实际同意；当前只有准备与冻结，尚未发送新用户资料。见[本版记录](context-20261031.md)。
