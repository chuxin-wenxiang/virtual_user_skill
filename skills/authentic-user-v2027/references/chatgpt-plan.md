# 可选：使用现有 ChatGPT 套餐执行试验

常规证据准备和宿主访谈仍离线运行。仅在用户明确要求外部模型执行时使用此适配器；Sign in with ChatGPT 的可用性和额度取决于实际账号。授权成功不保证足够完成整批。

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
