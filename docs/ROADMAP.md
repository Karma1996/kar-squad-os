# Roadmap

按“先可观测、再提效、后扩能力”的顺序推进。每项完成需更新配置手册、测试与 CHANGELOG。

## v4.2（P0）

| 项 | 验收 |
| --- | --- |
| 候选冻结 tag + `manifest check` | A4/A5 绑定 `candidate/<KEY>-<digest>`；任何 late push 使结论失效；脚本校验 docs/repos/PR/原型 SHA |
| 审批清单 + rationale/conditions | 每道门 3 项检查；manifest 记录一句话理由与附条件；R3 第二人复核；H3 抽样 10% |
| 指标采集 | 每个 issue 记录 human_touches / wait_human / rework / recuts / escaped defects；每周摘要 |
| 人类 WIP/SLA | 每个 Decision Owner 同时待决策 ≤2；24h 提醒 + 备份升级 |
| 校验与恢复 | `verify.py` 覆盖 Squad 指令/模板/文件（已做）；补 `restore.py`、fake-CLI 单测、CI（本仓库已起步） |

## v4.3（P1）

| 项 | 验收 |
| --- | --- |
| R3 安全 overlay | 威胁模型/权限矩阵/密钥与依赖扫描/回滚演练；独立安全评审人 |
| 风险分级产物矩阵 | R0/R1 三份以内；R2 三份；R3 全量；Program 子级 1–2 份 |
| 草稿 checkpoint + 中途 steer | H1/H2 前 10 分钟异步 review；纠偏走 steer，记录决策台账 |
| Lead touchpoint budget | 只允许 intake/契约/H1-H3/集成/合并/异常六个接触点 |
| 1 页 Quickstart + `/tour` | 新人不读 1000 行手册也能完成一个门（本仓库已有 Quickstart） |

## v4.4（P2）

| 项 | 验收 |
| --- | --- |
| 低风险 24h 默认 + 假设 | 仅 R0/R1、可逆、无外部契约；项目级 opt-in；H1 可推翻 |
| 队列抢占 | S0/S1 抢占；Quick FIFO；Program 合并窗口优先 |
| 单一源生成 | 从 YAML/JSON 生成 config/skills/agents，消除三套源漂移 |
| 视觉回归工具化 | 项目事实配置工具/断点/阈值；关键界面自动对比 |
| 发布自动化 | tag → GitHub Release → Multica issue 附件；部署 dry-run/apply/verify 一键 |

## 暂不做

- 多套并行版本/多分支长期维护（先保持单基线）。
- 自动删除/归档旧 Skill（人类确认后执行）。
- 绕过人类门禁的“全自动交付”。
