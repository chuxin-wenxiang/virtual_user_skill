# 全真用户 v2027 预览版

版本：`2027.0.0-alpha.6` · 验证状态：**归因门禁与新8人留出检查完成，审核仍有漏放和误撤，保留研究预览**

把本地个体历史整理为有时间边界的证据包，由宿主模型生成附引用的AI模拟。新增具体字段前提、推断范围、方向依赖，以及只撤回歧义项的来源审核。常规使用无需单独API Key或付费服务；模型费用依宿主接入方式，套餐宿主消耗套餐。真实档案不随代码发布。

[新8人报告](references/pilot-20261029-fresh.md)：128次生成、114份合约通过、14份失败；29批来源复核仍留下8条部分支持推断，并误撤部分有界假设。严格态度命中由10/16降为4/16，简单NPS延续基准为8/8；主题有一位目标无原因，7人结果只能探索。不能宣称推断问题已全部解决或预测效果已验证。

[alpha.5同人回归](references/pilot-20261029.md)与[alpha.4执行偏离](references/pilot-20261026.md)保留。工程可用不代表更接近真人；PMF、人格诊断、因果、总体业务概率未验证。

## 安装

需要 Python 3.10+。将本目录完整复制到宿主的技能目录，目录名保持 `authentic-user-v2027`，可与旧版 `authentic-user` 并存。例如在下载并解压后、位于本目录的终端执行：

```bash
mkdir -p "$HOME/.codex/skills"
cp -R . "$HOME/.codex/skills/authentic-user-v2027"
```

首次安装前确认目标目录不存在，避免把旧文件混入新版本。安装后在新会话明确调用 `$authentic-user-v2027`。其他宿主使用其对应 Skill 安装位置；脚本本身也能直接运行，不依赖 Codex 专用库。

## 两分钟离线演示

以下命令均在本目录执行，仅读取仓库自带的**合成数据**。示例回答为手工编写的协议示例，不是模型实验结果。

```bash
python3 scripts/authentic_user.py --version
python3 scripts/authentic_user.py doctor --profiles-dir examples/profiles
python3 scripts/authentic_user.py inspect --profiles-dir examples/profiles --buyer-id demo-rich --cutoff 2026-01-01
python3 scripts/authentic_user.py prepare --profiles-dir examples/profiles --buyer-id demo-rich --question '酒店退改和价格透明，你更在意什么？' --cutoff 2026-01-01 --industry domestic_hotel --output outputs/demo-memory.json
python3 scripts/authentic_user.py prompt --bundle outputs/demo-memory.json --output outputs/demo-prompt.txt
python3 scripts/authentic_user.py check-answer --bundle outputs/demo-memory.json --answer examples/answer-field-demo.json
python3 scripts/authentic_user.py render-answer --bundle outputs/demo-memory.json --answer examples/answer-field-demo.json --output outputs/demo-answer.rendered.json
```

将 `outputs/demo-prompt.txt` 交给当前宿主 AI，按其中协议生成回答，再用 `render-answer` 读取来源字段统一生成引用，并用 `check-answer` 检查绑定结果。脚本的 `prompt` 命令只生成文本，不会替你调用模型。

输出文件默认以本地用户读写权限创建；同名文件已存在会报错，请换文件名。运行示例第二次时可以换一个输出目录。`outputs/` 被 Git 忽略，不应提交真实证据。

## 一条命令开始访谈

```bash
python3 scripts/authentic_user.py interview --profiles-dir examples/profiles --buyer-id demo-rich --question '酒店退改和价格透明，你更在意什么？' --cutoff 2026-01-01 --output-dir outputs/interview-demo
```

命令创建证据包、提示词、绑定证据包的回答模板和运行记录，不自动调用模型或生成假回答。宿主 AI 读取 `outputs/interview-demo/prompt.txt` 后生成 `answer.json`，先检查候选：

```bash
python3 scripts/authentic_user.py render-answer --bundle outputs/interview-demo/evidence.json --answer outputs/interview-demo/answer.json --output outputs/interview-demo/answer.rendered.json
python3 scripts/authentic_user.py check-answer --bundle outputs/interview-demo/evidence.json --answer outputs/interview-demo/answer.rendered.json
```

随后按 [SKILL交付流程](SKILL.md) 用宿主完成来源审核并确定性撤下歧义项；审核也消耗模型额度，不要求另外购买API。

新回答必须携带当前证据包的 `bundle_sha256`，wire_answer 的事实只能选原字段，推断有可见前提、竞争解释及外部更新条件；渲染器统一生成正文与 claims，避免两份清单失配。仍兼容读取 alpha.1 证据包；旧回答未绑定时会返回明确警告，建议重新生成。

## 接入自己的本地档案

```text
my-profiles/
  archives_v2027/USER_ID.json
  archives_extended/USER_ID.json
```

通过参数 `--profiles-dir /absolute/path/my-profiles`，或环境变量指定目录：

```bash
export AUTHENTIC_USER_PROFILES_DIR='/absolute/path/my-profiles'
python3 scripts/authentic_user.py doctor
python3 scripts/authentic_user.py prepare --buyer-id USER_ID --question '你最在意哪些体验？' --output /tmp/user-memory.json
```

没有参数或环境变量时，默认检查本机 `~/.agents/v2027_profiles`。指定自己的真实 ID，不要使用示例 ID 代替本人。历史回测必须加 `--cutoff`；日期是排他边界，默认时区为上海时间。档案字段、行业代码和限制见 [数据契约](references/data-contract.md)。

## 准备小样本验证

```bash
python3 scripts/validation_prep.py scan --profiles-dir /absolute/path/my-profiles
python3 scripts/validation_prep.py build --profiles-dir /absolute/path/my-profiles --input-dir /private/tmp/pilot-inputs --judge-dir /private/tmp/pilot-judge
```

默认按四组各 2 人选取互斥的 8 人，生成四类题、两种条件的 64 份提示词和计划重复 2 次的 128 条调用清单。实际是否能满足配额取决于本地数据；不够时会报错，不补造样本。材料保持本地，输入目录和评分隐藏材料目录相互分离。

本工具比较“同一批历史标签”与“同一可见历史的个体记忆”，不冒称复现旧生产 Agent。模型版本与参数仍需在生成前冻结，未知题需先核实可见证据；`model_calls_completed=0` 表示只准备了材料。详见 [验证流程与口径](references/validation.md)。

## 冻结、回答导入与盲评

本地工作流工具，先核验完整输入，再生成待填写配置：

```bash
python3 scripts/validation_workflow.py audit --input-dir /private/tmp/pilot-inputs
python3 scripts/validation_workflow.py templates --input-dir /private/tmp/pilot-inputs --output-dir /private/tmp/pilot-setup
```

按实际情况填写固定模型版本、共同参数和可见证据审阅记录，再用 `freeze` 建立运行记录。外部模型实际生成后，通过 `ingest` 导入与运行、提示词、模型配置绑定的回答；全部导入后，`blind` 生成条件标签遮蔽的评审包，`summarize` 对已评分结果按用户做配对汇总。完整命令和回答信封格式见 [验证流程](references/validation.md)。

这些命令不调用模型，也不提供自动语义评分；配置模板未完成时不能冻结。导入的服务响应元数据由外部适配器提供，工具未独立核验服务端执行。合成配置仅用于测试，不能标为真实服务结果。

另可运行 `python3 scripts/validation_prep.py audit-selection` 比较选样口径敏感性；它不改变当前正式筛选规则，也不能替代缺失的历史筛选实现。

## 费用与可选套餐试验

Skill本身不收费。默认由当前宿主模型生成及审核：套餐宿主消耗其套餐，按量API宿主依其自身计费。本版没有必须另购API的步骤，也不能承诺所有安装环境都只扣套餐。下面的外部批试是可选入口，来源复核会增加模型用量；额度不够就停，不能自动转付费。

## 批试入口

使用现有 ChatGPT 套餐执行冻结网格的授权、探针、配置及停止规则见[套餐适配器说明](references/chatgpt-plan.md)。仅在明确资料外发授权后执行；不使用按量 API 付费回退。核心 CLI 保持零依赖，OAuth 校验使用可选 `PyJWT[crypto]`。原始证据、响应和凭证均不公开。

## 引用可靠性与事实/推断边界

本版借鉴2026方法中的证据分层、候选机制/竞争解释和用户配对统计，但不复制内部服务或私有口径。原话仍是历史自述，来源字段忠实提取不证明真实行为；候选机制不是诊断，推断即使格式正确仍需语义复核。没有机制时可明确未知。旧自由文本回答兼容读取并提示复核，新任务使用 field-bound-v3，按具体字段归因，交付前做来源语义审核。

## 检查

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_release.py
```

`check_release.py` 检查发布文件是否符合白名单、是否混入私有数据/密钥形态、版本一致性和 Markdown 本地链接；它不能代替人工审查原话或授权。仓库只包含公开代码和标为 `synthetic` 的示例，不含原始 CSV、真实档案、内部交接和服务凭证。

## 发布状态

本版新增能力、已跑检查和待验证项见 [发布说明](RELEASE_NOTES.md)。回答中的第一人称始终代表 AI 模拟，不能冒充用户本人。附证据不自动意味着判断正确，关键结论还需语义复核。
