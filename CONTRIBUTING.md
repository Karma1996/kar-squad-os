# Contributing

KAR Squad OS 由人类与 Agent 协作维护。原则：**人类做决定，Agent 做实现与证据；每次变更可测试、可回滚。**

## 角色

| 角色 | 负责 | 不做什么 |
| --- | --- | --- |
| Human（Decision Owner） | 目标、优先级、评审、合并批准、发布批准、Access/仓库/分支保护 | 不直接改 Skill/Agent 配置 |
| Agent（Maintainer） | 实现、测试、配置手册、Skill/Agent 更新、release、部署 dry-run/apply、verify | 不代替人类审批、不删除对象、不碰密钥 |

## 变更流程

1. **Issue**：在 Multica 的 **KAR Squad OS** 项目开 issue；写目标、验收、风险、回滚。
2. **分支**：`feat/{ISSUE_KEY}-{SLUG}`；一个 issue 一个 PR。
3. **实现**：同步更新 `config/`、`skills/`、`agents/`、`tests/`；保持 `VERSION` 一致。
4. **本地验证**：
   ```bash
   make test
   make check
   ```
5. **PR**：描述含变更、影响、测试、迁移、回滚；CI 必须绿。
6. **人类评审**：看 diff、配置手册、测试与迁移影响；Approve 后 squash merge。
7. **发布**：打 tag `vX.Y.Z`；`make build`；把 `release/KAR-Squad-Bootstrap-vX.Y.Z.zip` 附到 issue。
8. **部署**：`bootstrap.py --dry-run` → `--apply --update` → `verify.py`；执行前备份。
9. **回滚**：用 `backups/` 或上一版 release；不删除对象。

## 配置变更协议

任何 Skill/Agent/Squad/模板变更，PR 必须回答：

- 改哪个对象？当前值是什么？
- 目标值是什么？影响哪些 Agent/项目？
- 如何验证？如何回滚？
- 是否改变人类动作数、门禁或质量底线？
- 是否需要同步更新 `config/KAR-Squad-Config-vX.Y.md` 与 `CHANGELOG.md`？

## 质量底线

- 独立验证、人类门禁、main 只由人类、issue 内单写者、证据优先、无秘密、失败显式——**不可被项目 override 取消**。
- 不删除/跳过测试来让 CI 变绿。
- 不把 token、密码、workspace ID、runtime ID、真实仓库 URL、人名写进仓库。
- 模板 HTML 只改槽位/样式，不引入 CDN；版本与 sha256 必须同步。

## 版本

- `MAJOR`：破坏性变更（Skill 名、门禁、目录、发布包结构）。
- `MINOR`：新增 Skill/能力、兼容的默认值调整。
- `PATCH`：文案、bug fix、校验增强。
- 每次发布更新 `VERSION`、`bootstrap.json`、`CHANGELOG.md`、配置手册版本。
