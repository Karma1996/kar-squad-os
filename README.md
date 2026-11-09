# KAR Squad OS

KAR Delivery Squad 的**配置与运维仓库**：Skills、Agent 指令、Squad leader briefing、文档模板、配置手册、迁移/部署/校验脚本，以及后续优化的测试与 CI。

它不存放具体业务项目的代码或交付物。业务项目通过 `bootstrap.py` 把这套配置部署到 Multica 工作区，再用 `/init` 写入项目薄覆盖层。

- 配置手册：[`config/KAR-Squad-Config-v4.2.md`](config/KAR-Squad-Config-v4.2.md)
- 当前版本：`4.2.0`（见 `VERSION`）
- 部署脚本：`scripts/bootstrap.py`
- 校验脚本：`scripts/verify.py`
- 恢复脚本：`scripts/restore.py`
- 候选/门禁：`scripts/manifest.py`
- 指标：`scripts/metrics.py`
- 人类 WIP/SLA：`scripts/human_wip.py`
- 发布构建：`scripts/build_release.py`

## 这个仓库管什么

| 目录 | 内容 |
| --- | --- |
| `skills/` | 14 个小队 Skill，含 `kar-squad-profile`（默认值/解析规则）与 `kar-doc-template`（唯一文档模板） |
| `agents/` | 8 份 Agent 指令 |
| `squad/` | Squad 名册与 leader briefing |
| `config/` | 完整配置手册（人类可读的基线） |
| `scripts/` | 部署、校验、恢复、候选 manifest、指标、人类 WIP、发布构建 |
| `tests/` | 配置/spec/模板/解析器/恢复/manifest/指标的单元测试（fake CLI） |
| `docs/` | 快速上手、路线图、ADR、门禁清单、manifest、指标、WIP、备份恢复 |

## 协作方式（人类 + Agent）

1. **人类发起/确认**：在 Multica 的 **KAR Squad OS** 项目开 issue，写清目标、验收标准、风险。
2. **Agent 实现**：在 `feat/{ISSUE_KEY}-{SLUG}` 分支修改；同步更新配置手册、Skill、Agent、测试。
3. **CI 必须绿**：`make test` + `make check`（GitHub Actions 同样跑）。
4. **人类评审**：看 diff、配置手册、测试与迁移影响；Approve 后 squash merge 到 `main`。
5. **发布**：打 tag `vX.Y.Z`；`make build` 生成 `release/KAR-Squad-Bootstrap-vX.Y.Z.zip`。
6. **部署到工作区**：`bootstrap.py --dry-run` → `--apply --update` → `verify.py`；执行前自动备份。
7. **回滚**：`restore.py --backup backups/backup-<stamp>.json --apply` → `verify.py`；或使用上一版 release；不删除对象。

详细规则见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

## 本地开发

```bash
make test      # 单元测试（含 manifest/metrics/human_wip/restore）
make check     # 校验 specs、模板 hash、版本一致性、manifest 示例
make build     # 生成 release/KAR-Squad-Bootstrap-v<version>.zip
```

只依赖 Python 3.9+ 标准库。`make test` / `make check` 仅在本仓库可用；迁移包只含部署资产，不含测试与 CI。

## 部署到 Multica 工作区

```bash
export MULTICA_CLI_PATH="/path/to/multica"
export MULTICA_WORKSPACE_ID="<workspace-uuid>"
export KAR_CORE_RUNTIME_ID="<core-runtime-id>"
export KAR_QA_RUNTIME_ID="<qa-runtime-id>"   # 可同 core

python3 scripts/bootstrap.py --dry-run
python3 scripts/bootstrap.py --apply --update
python3 scripts/verify.py
```

- 只创建/更新 Skill、Agent、Squad 与 Skill 支持文件；不创建项目、仓库、分支保护、密钥、Access。
- 写入前自动备份到 `backups/`（含 Skill 文件内容）；`restore.py` 可从这个快照恢复。
- 模板不再由项目配置路径：`kar-doc-template` 是唯一源；项目 docs 树里的模板是 materialize 缓存。

## 版本与兼容

- 语义版本：`MAJOR.MINOR.PATCH`；配置手册、`VERSION`、`bootstrap.json`、release 包保持一致。
- `4.2.0` 起，A4/A5 绑定 `candidate/<KEY>-<digest>`；`manifest.py check` 校验 docs/repos/PR/CI。
- `4.1.0` 起，小队默认值在 `kar-squad-profile`，项目描述只写 `squad-overlay`。
- 旧 `S01–S17` 不在本仓库维护；迁移后由人类归档。
- 不提交 token、密码、workspace ID、runtime ID、真实仓库 URL 或人名。

## 相关

- 人类快速上手：[`docs/HUMAN-QUICKSTART.md`](docs/HUMAN-QUICKSTART.md)
- 审批清单：[`docs/GATES.md`](docs/GATES.md)
- 候选冻结与 manifest：[`docs/MANIFEST.md`](docs/MANIFEST.md)
- 指标与周摘要：[`docs/METRICS.md`](docs/METRICS.md)
- 人类 WIP/SLA：[`docs/HUMAN-WIP.md`](docs/HUMAN-WIP.md)
- 备份与恢复：[`docs/BACKUP-RESTORE.md`](docs/BACKUP-RESTORE.md)
- 后续优化路线：[`docs/ROADMAP.md`](docs/ROADMAP.md)
- 为什么用 Skill 承载配置：[`docs/decisions/0001-config-as-skills.md`](docs/decisions/0001-config-as-skills.md)
