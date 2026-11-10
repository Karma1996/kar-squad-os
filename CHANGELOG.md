# Changelog

## 4.4.0

- 新增低风险 24h 默认与假设：仅 R0/R1、可逆、无外部契约、项目级人类 opt-in；H1 静默 24h 且只提醒一次后记 `assumed`，人类可推翻，H3 仍由人类批准（`autonomy.py check|deadline`、`policy.py` 的 `autonomy` 校验）。
- 新增队列抢占：`queue.py check|plan` 按 S0/S1 抢占、Program 合并窗口优先、Quick FIFO 的确定性顺序派发；抢占不改门禁与人类动作。
- 新增单一源生成：`sources/squad.json` 生成 `skills.json`、`agents.json`、`squad/`、`bootstrap.json`、`kar-squad-profile/squad.json`；`generate.py --check` 在 `make check` 拦截漂移；ADR 0002 记录选型。
- 新增视觉回归工具化：项目事实配置工具/断点/阈值/关键界面；`visual.py init|capture|check` 校验覆盖与阈值，关键界面默认 0 差异；manifest `ui_affected` / `visual_regression` 在 H3 校验。
- 新增发布/部署自动化：`release.py check|plan|tag|github-release|attach|publish`（tag → GitHub Release → issue 附件）与 `deploy.py`（dry-run → apply --update → verify 一键）；不可逆步骤默认 dry-run 且必须人类 `--approved-by`。
- 配置手册升为 v4.4，新增 `docs/AUTONOMY.md`、`docs/QUEUE.md`、`docs/SINGLE-SOURCE.md`、`docs/VISUAL-REGRESSION.md`、`docs/RELEASE-AUTOMATION.md`、ADR 0002 与三份示例；Skills/Agents/Squad 同步。
- 测试：新增 autonomy/queue/generate/visual/release/deploy 单测与示例 manifest 的 v4.4 策略校验；`make check` 增加生成漂移、低风险假设与队列示例校验。

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
