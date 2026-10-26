# 全真用户 v2027 预览版

版本：`2027.0.0-alpha.2` · 效果验证：**待补**

把本地真实用户的历史记录整理为有时间边界的证据包，由 Codex 等支持 Skill 的宿主 AI 生成附引用的模拟回答。本版包含可安装 Skill、零依赖 Python CLI、证据准备、提示词、回答结构检查与合成演示。没有独立模型调用，不需要 API Key。真实用户档案不随代码发布。

这是可运行的研究预览版，尚未证明优于标签基线。安装、命令执行和回归检查通过只代表工程功能可用。群体选人、PMF 量化、指标预测、实时更新、人格建模与因果验证均未包含在首版。

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
python3 scripts/authentic_user.py check-answer --bundle outputs/demo-memory.json --answer examples/answer-demo.json
```

将 `outputs/demo-prompt.txt` 交给当前宿主 AI，按其中协议生成回答，再用 `check-answer` 检查生成的 JSON。脚本的 `prompt` 命令只生成文本，不会替你调用模型。

输出文件默认以本地用户读写权限创建；同名文件已存在会报错，请换文件名。运行示例第二次时可以换一个输出目录。`outputs/` 被 Git 忽略，不应提交真实证据。

## 一条命令开始访谈

```bash
python3 scripts/authentic_user.py interview --profiles-dir examples/profiles --buyer-id demo-rich --question '酒店退改和价格透明，你更在意什么？' --cutoff 2026-01-01 --output-dir outputs/interview-demo
```

命令创建证据包、提示词、绑定证据包的回答模板和运行记录，不自动调用模型或生成假回答。宿主 AI 读取 `outputs/interview-demo/prompt.txt` 后生成 `answer.json`，再检查：

```bash
python3 scripts/authentic_user.py check-answer --bundle outputs/interview-demo/evidence.json --answer outputs/interview-demo/answer.json
```

新回答必须携带当前证据包的 `bundle_sha256`，正文引用与 `claims` 引用需要一致，避免串用另一用户或问题的回答。仍兼容读取 alpha.1 证据包；旧回答未绑定时会返回明确警告，建议重新生成。

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

## 检查

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_release.py
```

`check_release.py` 检查发布文件是否符合白名单、是否混入私有数据/密钥形态、版本一致性和 Markdown 本地链接；它不能代替人工审查原话或授权。仓库只包含公开代码和标为 `synthetic` 的示例，不含原始 CSV、真实档案、内部交接和服务凭证。

## 发布状态

本版新增能力、已跑检查和待验证项见 [发布说明](RELEASE_NOTES.md)。回答中的第一人称始终代表 AI 模拟，不能冒充用户本人。附证据不自动意味着判断正确，关键结论还需语义复核。
