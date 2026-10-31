# 全真用户 v2027 预览版

版本：`2027.0.0-alpha.14` · 验证状态：**研究预览；新8人试验完成，尚无预测优势**

把授权本地历史整理为有时间边界的证据包，由宿主模型生成附来源的AI模拟。普通使用不要求单独API Key，消耗宿主额度；真实档案不随代码发布。

alpha.13冻结算法的新8人已完成64次生成、16批来源审核和80个唯一正式响应。原始严格导入41/64；64份派生结果齐全，含5个隔离待审组件。Q2原始10/16命中、审核后5/16，低于最近同业NPS延续及固定推荐的16/16；8人目标均为推荐类，不能证明识别变化的能力。来源初评最终仍3条部分支持，严格敏感性口径下为8条。详见[本轮完整结果与评分限制](references/pilot-20261031-decision.md)。

alpha.14据实测问题补齐错栏估计、历史类别延续、冲突未知代码及日期引用检查；次数/比较词按上下文核源，不机械认证或删除。来源审核增加不含未选值的完整目录类型/日期索引，明确NPS分段，区分未来估计的不确定性与历史资料缺失。213项离线检查通过；修复后只做已见数据回归，未再调用模型，不能称新的独立验证通过。

AI态度估计、条件反应与脚本历史基线继续分开，估计保留自己的来源；失败仍未知，基线不替AI补分。原始候选、正式结果和alpha.13版本保持原样，旧alpha.9缺失不回填。独立人工校准和预测有效性仍未完成。

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
python3 scripts/authentic_user.py check-answer --bundle outputs/demo-memory.json --answer examples/answer-decision-demo.json
python3 scripts/authentic_user.py render-answer --bundle outputs/demo-memory.json --answer examples/answer-decision-demo.json --output outputs/demo-answer.rendered.json
```

将 `outputs/demo-prompt.txt` 交给当前宿主 AI，按其中协议生成回答，再用 `render-answer` 读取来源字段统一生成引用，并用 `check-answer` 检查绑定结果。脚本的 `prompt` 命令只生成文本，不会替你调用模型。

输出文件默认以本地用户读写权限创建；同名文件已存在会报错，请换文件名。运行示例第二次时可以换一个输出目录。`outputs/` 被 Git 忽略，不应提交真实证据。

## 一条命令开始访谈

```bash
python3 scripts/authentic_user.py interview --profiles-dir examples/profiles --buyer-id demo-rich --question '酒店退改和价格透明，你更在意什么？' --cutoff 2026-01-01 --output-dir outputs/interview-demo
```

命令创建证据包、同记录字段关联表source-map.json、独立baseline.json、提示词、绑定证据包的回答模板和运行记录，不自动调用模型或生成假回答。宿主 AI 读取 `outputs/interview-demo/prompt.txt` 后生成 `answer.json`，先按条目预检候选并保存原始失败记录：

```bash
python3 scripts/plan_review.py precheck --bundle outputs/interview-demo/evidence.json --answer outputs/interview-demo/answer.json --output outputs/interview-demo/answer.checked.json --audit-output outputs/interview-demo/precheck.json
python3 scripts/authentic_user.py check-answer --bundle outputs/interview-demo/evidence.json --answer outputs/interview-demo/answer.checked.json
```

随后按 [SKILL交付流程](SKILL.md) 用宿主完成来源审核并确定性撤下歧义项；审核也消耗模型额度，不要求另外购买API。

新回答必须携带当前证据包的 `bundle_sha256`，wire_answer 的事实和判断选择来源目录编号，完整原文由脚本提取，态度估计、条件反应和假设分别审核；渲染器统一生成正文与 claims，避免两份清单失配。仍兼容读取 alpha.1 证据包；旧回答未绑定时会返回明确警告，建议重新生成。

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
python3 scripts/validation_prep.py build --profiles-dir /absolute/path/my-profiles --input-dir /private/tmp/pilot-inputs --judge-dir /private/tmp/pilot-judge --comparison memory_vs_computed_baselines --response-protocol decision-bound-v5 --include-zero --max-records 24
```

以上命令准备M记忆臂：默认四组各2人、四题、每题重复2次，8人32份提示词、64次生成和最多16批审核；Q2最近NPS及固定类别基线本地计算。新用户验证还须显式排除所有旧人、启用fresh_holdout并事前固定抽样规则，不能把默认分组材料称为独立新样本。具体见[新协议与验证计划](references/decision-20261031.md)。

原标签—记忆双臂继续保留兼容入口，使用显式旧协议；不能将新M臂伪称标签对照或修改旧运行分母。准备不调用模型，实际取数/输入可用不代表模型效果已验证。输入与隐藏材料相互分离并保留在本地。

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

本版借鉴2026方法中的证据分层、候选机制/竞争解释和用户配对统计，但不复制内部服务或私有口径。原话仍是历史自述，来源字段忠实提取不证明真实行为；候选机制不是诊断，推断即使格式正确仍需语义复核。没有机制时可明确未知。旧自由文本及v2/v3/v4回答兼容读取，新宿主任务使用decision-bound-v5，按各组件的实际来源分别审核；旧冻结运行不改协议。

## 检查

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_release.py
```

`check_release.py` 检查发布文件是否符合白名单、是否混入私有数据/密钥形态、版本一致性和 Markdown 本地链接；它不能代替人工审查原话或授权。仓库只包含公开代码和标为 `synthetic` 的示例，不含原始 CSV、真实档案、内部交接和服务凭证。

## 发布状态

本版新增能力、已跑检查和待验证项见 [发布说明](RELEASE_NOTES.md)。回答中的第一人称始终代表 AI 模拟，不能冒充用户本人。附证据不自动意味着判断正确，关键结论还需语义复核。
