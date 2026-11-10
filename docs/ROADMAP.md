# Roadmap

按“先可观测、再提效、后扩能力”的顺序推进。每项完成需更新配置手册、测试与 CHANGELOG。

## v4.2（P0，4.2.0 已交付）

实现与验证命令见 `docs/MANIFEST.md`、`docs/GATES.md`、`docs/METRICS.md`、`docs/HUMAN-WIP.md`、`docs/BACKUP-RESTORE.md`。

| 项 | 验收 |
| --- | --- |
| 候选冻结 tag + `manifest check` | ✅ A4/A5 绑定 `candidate/<KEY>-<digest>`；late push/文档 SHA 变化使结论失效；`scripts/manifest.py` 校验 docs/repos/PR/CI/原型 SHA |
| 审批清单 + rationale/conditions | ✅ 每道门 3 项检查；manifest 记录一句话理由与附条件；R3 第二人复核；H3 抽样 10% |
| 指标采集 | ✅ 每个 issue 记录 human_touches / wait_human / rework_rounds / candidate_recuts / escaped_defects；每周 6 指标摘要 + 2 周基线 |
| 人类 WIP/SLA | ✅ 每个 Decision Owner 同时待决策 ≤2；排队；24h 只提醒一次；备份升级 |
| 校验与恢复 | ✅ `verify.py`；新增 `restore.py`、fake-CLI 单测、CI（manifest 示例 + 全套单测） |

## v4.3（P1，4.3.0 已交付）

实现与验证命令见 `docs/SECURITY-OVERLAY.md`、`docs/ARTIFACTS.md`、`docs/CHECKPOINT-STEER.md`、`docs/LEAD-TOUCHPOINTS.md`；统一校验 `python3 scripts/policy.py check --profile h3`。

| 项 | 验收 |
| --- | --- |
| R3 安全 overlay | ✅ 威胁模型/权限矩阵/密钥与依赖扫描/回滚演练；独立安全评审人（与 H3 第二人同一人，id 强制一致） |
| 风险分级产物矩阵 | ✅ R0/R1 ≤3；R2 三份；R3 全量 + 安全 overlay；Program 子级 1–2；`artifacts` 在 H3 校验 |
| 草稿 checkpoint + 中途 steer | ✅ H1/H2 提前 ≥10 分钟发布草稿；纠偏走 `steers`，与 `checkpoints`、文档版本三方对账 |
| Lead touchpoint budget | ✅ 只允许 intake/契约/门禁/集成/合并/异常六类；预算与 gate 记录在 `touchpoints` 校验 |
| 1 页 Quickstart + `/tour` | ✅ Quickstart 压缩为 1 页并给出 5 分钟走完一道门；`/tour` 五步只读导览写入配置手册附录 D |

## v4.4（P2，4.4.0 已交付）

实现与验证命令见 `docs/AUTONOMY.md`、`docs/QUEUE.md`、`docs/SINGLE-SOURCE.md`、`docs/VISUAL-REGRESSION.md`、`docs/RELEASE-AUTOMATION.md`；统一校验 `python3 scripts/policy.py check --profile h3` 与 `make check`。

| 项 | 验收 |
| --- | --- |
| 低风险 24h 默认 + 假设 | ✅ 仅 R0/R1、可逆、无外部契约、项目级人类 opt-in；H1 静默 24h 后记 `assumed`；人类可推翻（`overridden` 时 H3 失败）；H3 仍人类；`autonomy.py check|deadline` + `policy.py` 校验 |
| 队列抢占 | ✅ S0/S1 抢占；同 severity 内 Program 合并窗口优先、其余 FIFO、Quick 严格 FIFO；`queue.py check|plan` 确定性输出与抢占记录 |
| 单一源生成 | ✅ `sources/squad.json` 生成 skills/agents/squad/bootstrap/profile；`generate.py --check` 在 `make check` 拦截漂移；ADR 0002 记录 JSON 选型 |
| 视觉回归工具化 | ✅ 项目事实 `visual.json` 配置工具/断点/阈值/关键界面；`visual.py init|capture|check`；关键界面默认 0 差异，缺组合/工具不可用判 FAIL/BLOCKED；`visual_regression` 在 H3 校验 |
| 发布自动化 | ✅ `release.py check|plan|tag|github-release|attach|publish`；tag → GitHub Release → Multica issue 附件；`deploy.py` dry-run → apply → verify 一键，人类 `--approved-by` 前置 |

## 暂不做

- 多套并行版本/多分支长期维护（先保持单基线）。
- 自动删除/归档旧 Skill（人类确认后执行）。
- 绕过人类门禁的“全自动交付”。
