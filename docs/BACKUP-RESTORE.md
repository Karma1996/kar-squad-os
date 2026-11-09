# 备份与恢复（restore.py）

`bootstrap.py --apply` 在写入前自动备份 Skills、Agents、Squad 与 Squad 成员到 `backups/backup-<UTC>.json`。`restore.py` 用同一个快照恢复，不改动项目、仓库、Access、分支保护或密钥。

## 1. 备份什么时候产生

```bash
python3 scripts/bootstrap.py --apply --update
# -> backup written: backups/backup-20261109T120000Z.json
```

- 备份包含：每个 Skill 的 `description` / `content` / 支持文件内容，每个 Agent 的 `description` / `instructions` / `max_concurrent_tasks` / `runtime_id` / 已绑定 Skill，Squad 的 `description` / `instructions` / `leader_id`，以及 Squad 成员与角色。
- `--no-backup` 会跳过备份，不推荐；恢复只能依赖上一份快照。
- 备份目录被 `.gitignore` 忽略，不提交 token/workspace id。

## 2. 恢复

```bash
# 默认 dry-run：只打印将执行的命令
python3 scripts/restore.py \
  --backup backups/backup-20261109T120000Z.json \
  --workspace-id "$MULTICA_WORKSPACE_ID"

# 确认后写入
python3 scripts/restore.py \
  --backup backups/backup-20261109T120000Z.json \
  --workspace-id "$MULTICA_WORKSPACE_ID" \
  --apply

# 读回验证
python3 scripts/verify.py --workspace-id "$MULTICA_WORKSPACE_ID"
```

- `--only skills|agents|squad`：只恢复其中一类，可重复。恢复 agents 时仍会按名字解析已有 Skill 绑定。
- `--core-runtime` / `--qa-runtime` / `--runtime-map name=runtime-id`：备份里没有 `runtime_id` 或需要换运行时（例如灾备到新工作区）时使用。
- 默认 dry-run；dry-run 不写任何对象。

## 3. 恢复语义

| 对象 | 已存在（按名字） | 不存在 |
| --- | --- | --- |
| Skill | `skill update` 覆盖 description/content + `skill files upsert` | `skill create` 后上传文件 |
| Agent | `agent update` 覆盖 instructions/description/并发 | `agent create`（需要 runtime）后 `agent skills set` |
| Squad | `squad update` 覆盖 description/instructions/leader | `squad create`（需要 leader） |
| Squad 成员 | 已存在则 `member set-role` | `member add` |

- 按**名字**匹配，不按旧 ID；旧 ID 只用于备份内的关联（leader、成员、Skill 绑定）。
- 不删除备份里没有的 Skill/Agent/Squad；多余对象需人类确认后手动归档。
- 人类成员不自动恢复（需要 workspace 权限与人名解析）；脚本会打印 warning，由人类重新添加。
- 备份格式不兼容或缺字段时显式报错，不猜。

## 4. 什么时候用

- `bootstrap.py --apply` 中途失败，部署态与包不一致。
- 误更新 Skill/Agent 后需要回到上一版。
- 灾备：在新工作区按同一备份重建小队（需重新指定 runtime）。

## 5. 回滚边界

- 可回滚：Skill 内容/文件、Agent 指令/并发/绑定、Squad 指令/leader/成员角色。
- 不可回滚（本脚本不碰）：Access、成员角色、项目/仓库、分支保护、密钥、已删除对象。
- 恢复后必须跑 `verify.py`；不一致就不算恢复完成。
- 恢复是覆盖写：执行前再确认一次备份文件路径与 `created_at`，必要时先复制备份文件。
