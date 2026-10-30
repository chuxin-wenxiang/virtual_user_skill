# alpha.10：同记录字段关联、执行清单与简单基线

2026-10-31。本轮仅做离线工程改进，未调用模型、未选新用户、未恢复alpha.9未知请求、未增加付费路径。全套156项工程检查通过，其中17项为新增针对性检查；这些结果不认证自然语言判断或真人预测有效。

## 已实现

1. `source_map`为所选E记录列出实际可用F字段、日期和来源哈希。它让模型更容易同时找到涉及的score、text、tags，不把同日不同记录合并，也不掩盖评分与文本不一致。新证据包与现代atomic批试都重算核对；旧目录和审核渲染保持兼容，记录检索排序未改变。
2. 宿主与新批试共同增加字段选择指导：全部前提显式选取，单个0分不能支持具体问题主题。关联表不补引用，不按关键词自动拒绝，不直接判定语义支持。
3. `validation_report.py status`只读核对本地文件清单与已有索引绑定，区分未尝试、请求状态未知、响应已存但索引不全、已有索引响应、结构失败及最终缺失。候选、批次、待完成atom使用独立分母；不因为存在final文件就宣称来源或效果验证通过。
4. `attitude`从本地已结束试验计算Q2交付命中、覆盖和给类别后的命中，比较同一可见输入的最近同业调查分数延续、固定推荐/观望/不推荐。0分保留，同一最新时点存在冲突评分时基线弃答；不从原话重复计一次调查。结果标posthoc_descriptive，不作确认性效果结论。

## 使用

普通访谈沿用SKILL入口；新建目录增加`source-map.json`查看副本，权威映射在绑定的`evidence.json`中。无需新增服务或依赖。只有模型阶段结束后，分析步骤才能读取judge；生成和来源审核仍不能访问它。

```bash
python3 scripts/validation_report.py status --run-dir /private/tmp/pilot-run --output /private/tmp/run-inventory.json
python3 scripts/validation_report.py attitude --run-dir /private/tmp/pilot-run --judge-dir /private/tmp/pilot-judge --model-phases-ended --phase original --output /private/tmp/q2-original.json
python3 scripts/validation_report.py attitude --run-dir /private/tmp/pilot-run --judge-dir /private/tmp/pilot-judge --model-phases-ended --phase source-final --output /private/tmp/q2-source-final.json
```

全部为本地只读处理，输出排他创建且为0600。`status`不读取judge、不接收凭证，也不发模型请求；`attitude`要求结束声明且拒绝未处理的执行锁，声明不能代替真实结束模型阶段。未知请求用量保留null，已知用量只累计有索引的完整响应；未认证全部账单。

清单只检查已存回执、信封和候选绑定，不重新验证全部传输body、时间间隔或派生重现，`full_integrity_audit_performed=false`始终保留。完整生成仍用trial_audit.py，完整来源仍用plan_review.audit；后者不会因清单有输出而被视为通过。`final_file_grid_complete`只指文件覆盖，不是审核或效果通过。

现代批试显式使用`validation_prep.build(..., response_protocol="atomic-bound-v4")`，协议登记`source_map_protocol=record-fields-v1`，两条件共用映射指令。新增映射也增加少量上下文；实际护栏仍须在冻结时检查，不保证套餐整批额度足够。旧`reframe`仅用于未带映射的历史材料，遇到现代映射输入会在创建目录前拒绝，避免静默丢弃契约。复现旧运行继续使用其原始冻结源码。

## 已结束alpha.9材料的事后核对

| 清单项目 | 新脚本核对结果 |
|---|---:|
| 原始生成已有索引响应 | 128 |
| 原始严格通过 / 结构失败 | 108 / 20 |
| 最终来源输出 / 缺失 | 8 / 120 |
| 来源未知请求涉及候选 / 未尝试候选 | 4 / 116 |
| 完成 / 未知 / 未尝试来源批次 | 2 / 1 / 29 |
| 已知完整正式响应输入 / 输出tokens | 439,249 / 36,114 |
| 原始记忆Q2给类别 / 全部位置 | 7 / 16 |
| 原始记忆Q2命中 / 全部位置 | 6 / 16 |
| 原始记忆Q2命中 / 给类别 | 6 / 7 |
| 最近同业NPS延续命中 | 14 / 16，8人各重复2次 |

以上与[alpha.9报告](pilot-20261030-scope.md)一致，没有更改原回答、评分或状态。标签条件Q2仍0/16命中，细分为12次弃答与4次结构无效；“全都未给有效类别”不能简化成全都成功克制。最终Q2几乎全缺失，0交付命中是缺失计零的交付指标，不能据此宣布审核使预测变差。

本轮未用新指令重生成这些答案，因而不构成alpha.10效果试验，也没有把已使用的人再次称为未见样本。新增工具让证据和分母更易核对，尚未证明推断支持不足或误撤的真实发生率下降。

## 仍待完成

现有来源审核120份缺失保持原样；不自动重试未知请求。记录排序、跨记录事件识别和独立人工评分尚未升级；不通过同日匹配补造事件。更完整的证据选取、语义误撤校准和新独立用户验证仍需后续工作，冻结规则与分析方案后才能发起，仅使用已确认现有套餐及对应数据授权，额度或传输错误停止。
