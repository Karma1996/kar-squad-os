# Changelog

## 4.3.0

- 新增 R3 安全 overlay：威胁模型、权限矩阵、密钥与依赖扫描、回滚演练、独立安全评审人；H3 第二人与 overlay 评审人强制为同一人（`security_overlay.reviewer`）。
- 新增风险分级产物矩阵：R0/R1 ≤3、R2 三份、R3 全量、Program 子级 1–2；manifest 用 `artifacts` 记录，`policy.py` 校验。
- 新增草稿 checkpoint + 中途 steer：H1/H2 草稿提前 ≥10 分钟发布，纠偏写入 `steers` 决策台账并绑定文档版本（`checkpoints` / `steers`）。
- 新增 Lead 接触点预算：只允许 intake/契约/门禁/集成/合并/异常六类，预算与 gate 记录写入 `touchpoints`。
- 新增 `scripts/policy.py`：可独立或随 `manifest.py check --profile h3` 运行，覆盖以上四类治理规则。
- Quickstart 压缩为 1 页并增加 `/tour` 五步只读导览；配置手册升为 v4.3，Skills/Agents/Squad 同步。
- 测试：新增 `tests/test_policy.py`（产物矩阵/安全 overlay/checkpoint/steer/接触点），manifest H3 用例补治理块；`make check` 校验示例 manifest 的 v4.3 策略。

## 4.2.0

- 新增候选冻结：`scripts/manifest.py freeze/digest/check`；A4/A5 绑定 `candidate/<KEY>-<digest>`，late push 或文档 SHA 变化使结论失效。
- manifest 升为 `version: 2`：每道门 3 项检查 + `rationale` + `conditions`；R3 记录第二人复核；H3 记录 10% 抽样（`gates.h3.sampling`）。
- 新增指标采集：`scripts/metrics.py` 输出每个 issue 的 5 项指标与每周 6 指标摘要，先采 2 周基线。
- 新增人类 WIP/SLA：`scripts/human_wip.py` 检查每个 Decision Owner 待决策 ≤2、排队、24h 只提醒一次、拒绝 Agent 代批。
- 新增恢复：`scripts/restore.py` 从 `backups/backup-*.json` 恢复 Skill（含文件）/Agent/Squad；bootstrap 备份补充 Skill 文件内容。
- 新增 `docs/GATES.md`、`docs/MANIFEST.md`、`docs/METRICS.md`、`docs/HUMAN-WIP.md`、`docs/BACKUP-RESTORE.md` 与完整 manifest 示例。
- 门禁卡升级为 8 行：增加“我检查了 / 理由 / 附条件”；配置手册升为 v4.2，Skills/Agents/Squad 同步。
- 测试：fake Multica CLI 支持状态与详情；新增 manifest/metrics/human_wip/restore 单测；`make check` 校验示例 manifest。


## 4.1.0

- 新增 `kar-squad-profile`：小队默认值、解析顺序、薄项目模板、`resolve_config.py`。
- 新增 `kar-doc-template`：唯一文档模板、`template.json`（4.1 + sha256）、`materialize_template.py`。
- 文档模板从项目配置改为小队资产；项目只提供 Docs Home。
- 项目描述改为 `squad-overlay` 薄覆盖层；共性配置移入小队默认值。
- `bootstrap.py` 支持 `skill files upsert`；`verify.py` 校验 Skill 文件、模板 hash、Squad 指令。
- 配置手册升为 v4.1；新增人类快速上手、路线图、ADR。

## 4.0.0

- 三条工作道 Quick/Standard/Program。
- 运行时人类 roster；Decision Owner = 根父 issue 创建人。
- 父 key 变更集与 Program 子分支。
- 灵活拆分 P0/P1/P2；像素级原型模式 B。
- 按需复盘；迁移包与 `verify.py`。

## 3.0.0

- 8 席 / 17 Skill / 1 Squad；H1–H3；问题优先；并行 A4/A5。
- 旧基线，保留作历史参考。
