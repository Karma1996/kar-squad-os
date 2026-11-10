# 发布自动化（release.py / deploy.py）

`scripts/release.py` 把版本检查、打 tag、GitHub Release、Multica issue 附件串成一条可审计的流水线；`scripts/deploy.py` 把工作区部署串成 `dry-run → apply --update → verify`。两者都只做**机械步骤**，不代替人类批准，也不绕过门禁。

- 所有不可逆动作默认 dry-run；只有显式 `--apply` 才执行。
- `tag` / `publish` / `deploy --apply` 必须带 `--approved-by <human>`；它记录“谁批准了这次发布”，不是身份认证。
- 外部命令（`git` / `gh` / `multica` / bootstrap / verify）都可注入路径，CI 用 fake 命令验证参数与顺序，不触网。

## 1. 目标与边界

| 脚本 | 做什么 | 不做什么 |
| --- | --- | --- |
| `scripts/release.py check` | 校验 `VERSION` / `bootstrap.json` / profile / CHANGELOG / 配置手册 / 干净工作树 / 本地 tag | 不构建、不打 tag、不写入 |
| `scripts/release.py plan` | 打印 build → tag → push → GitHub Release → Multica 附件的顺序与命令 | 无任何副作用 |
| `scripts/release.py tag` | 创建 annotated tag，可选 push | 不移动/覆盖已有 tag，不推 main |
| `scripts/release.py github-release` | 用 `gh` 创建 Release，notes 默认取 CHANGELOG 对应段落 | 不登录 `gh`，不改 tag |
| `scripts/release.py attach` | 把发布包作为附件评论到 Multica issue，正文含 tag 与 sha256 | 不创建 issue，不内联 `--content` |
| `scripts/release.py publish` | 串起 check → build → tag → release → attach，失败即停 | 不代替人类批准，不自动 push（除非 `--push`） |
| `scripts/deploy.py` | 版本检查 → bootstrap dry-run → bootstrap apply → verify | 不创建项目/仓库/Access，不碰密钥 |

不可协商的边界：

- `main` 只由人类合并；发布自动化不 push 代码分支，只 push 显式批准的 tag。
- tag 不可重复、不可移动；发布错了用新的 patch 版本前向修复，不删除或重写旧 tag。
- 不把 token、密码、workspace ID、runtime ID、真实仓库 URL 或人名写进仓库或命令行示例。
- 失败必须显式：任一步返回非 0 就停止，不静默降级为 PASS。

## 2. 发布前检查（check / plan）

```bash
# 人类可读
python3 scripts/release.py check

# CI / 自动化读取
python3 scripts/release.py check --json

# 仅用于本地排错：脏工作树降级为 warning
python3 scripts/release.py check --allow-dirty
```

`check` 校验：

| 检查 | 失败语义 |
| --- | --- |
| `VERSION` 是 `MAJOR.MINOR.PATCH` | error |
| `bootstrap.json.version == VERSION` | error |
| `bootstrap.json.config` 指向的配置手册存在 | error |
| `skills/kar-squad-profile/squad.json` 的 `version == VERSION` | error |
| `CHANGELOG.md` 有 `## {VERSION}` 标题 | error |
| `git -C <root> status --porcelain` 为空 | error；`--allow-dirty` 时降为 warning |
| 本地已存在 `v{VERSION}` tag | 只 warning（tag 不可变，真正发布时会失败） |

输出：

```text
RELEASE CHECK: OK
  version: 4.4.0
  tag: v4.4.0
  artifact: release/KAR-Squad-Bootstrap-v4.4.0.zip
```

失败时输出 `RELEASE CHECK: FAIL`，逐条列出 `ERROR:` / `WARN:`，退出码为 1。若 `--root` 不是 git 仓库，工作树检查无法判断，降级为 warning；真正的 `tag` / `publish --apply` 仍会因 git 命令失败而停止。

`--json` 输出对象：

```json
{
  "ok": true,
  "version": "4.4.0",
  "tag": "v4.4.0",
  "artifact": "release/KAR-Squad-Bootstrap-v4.4.0.zip",
  "errors": [],
  "warnings": []
}
```

`plan` 只校验 tag 是否等于 `v{VERSION}`，然后打印固定顺序：

```bash
python3 scripts/release.py plan --tag v4.4.0
```

```text
RELEASE PLAN: v4.4.0
  1. build          python3 scripts/build_release.py
  2. tag            git tag -a v4.4.0 -m 'KAR Squad OS v4.4.0'
  3. push           git push origin v4.4.0
  4. github-release gh release create v4.4.0 ... --title 'KAR Squad OS v4.4.0' --notes-file ...
  5. attach         multica issue comment add KAR-ISSUE --content-file ... --attachment ...
  artifact: release/KAR-Squad-Bootstrap-v4.4.0.zip
```

tag 不匹配时退出 1，不产生任何副作用。`--json` 输出 `{ok, version, tag, artifact, steps}`。

## 3. 发布流水线（tag → GitHub Release → Multica 附件）

推荐顺序：先 dry-run 看计划，再由人类批准后 `--apply`。

```bash
# 1. 本地检查与计划（无副作用）
python3 scripts/release.py check
python3 scripts/release.py plan --tag v4.4.0

# 2. 一键 dry-run：打印 build/tag/release/attach 全部命令，不构建、不打 tag
python3 scripts/release.py publish \
  --tag v4.4.0 \
  --issue KAR-13 \
  --approved-by <human>

# 3. 人类确认后执行；--push 默认关闭，需要显式打开
python3 scripts/release.py publish \
  --tag v4.4.0 \
  --issue KAR-13 \
  --approved-by <human> \
  --apply --push
```

`publish --apply` 的顺序：

1. `check`：`--apply` 下脏工作树直接失败；dry-run 只 warning。
2. `build`：`python3 scripts/build_release.py`，产物必须是 `release/KAR-Squad-Bootstrap-v{VERSION}.zip`。
3. `tag --apply`：先确认 tag 不存在，再 `git tag -a`；`--push` 时才 `git push <remote> <tag>`。
4. `github-release --apply`：默认 title 为 `KAR Squad OS v{VERSION}`，notes 从 CHANGELOG 的 `## {VERSION}` 段落生成到 `release/RELEASE-NOTES-v{VERSION}.md`，再执行 `gh release create`。
5. `attach --apply`：在 `release/` 写评论正文（tag、文件名、sha256、批准人），再执行 `multica issue comment add ... --content-file ... --attachment ...`。

也可以分步执行（便于人工核对每一步）：

```bash
python3 scripts/release.py tag \
  --tag v4.4.0 --approved-by <human> --apply --push

python3 scripts/release.py github-release \
  --tag v4.4.0 \
  --artifact release/KAR-Squad-Bootstrap-v4.4.0.zip \
  --apply

python3 scripts/release.py attach \
  --issue KAR-13 \
  --artifact release/KAR-Squad-Bootstrap-v4.4.0.zip \
  --tag v4.4.0 \
  --approved-by <human> \
  --apply
```

关键默认值：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--apply` | 关闭 | 不带就是 dry-run，只打印命令 |
| `--push` | 关闭 | 人类必须显式打开；只 push tag，不 push 分支 |
| `--attach` | 开启 | `publish` 默认在 Release 后评论到 issue；可用 `--no-attach` 关闭 |
| `--remote` | `origin` | push tag 的远端 |
| `--notes-file` | 自动生成 | 可注入现成 notes；生成文件只在 `--apply` 时写 |
| `--title` | `KAR Squad OS v{VERSION}` | GitHub Release 标题 |

`attach` 的评论正文固定使用 `--content-file`，不使用内联 `--content`；正文至少包含发布 tag、附件文件名与 sha256。`publish` 会把 `--approved-by` 传给 `attach`，因此正文含“发布由 `<human>` 批准”。

## 4. 人类批准

- `--approved-by <human>` 是批准记录，不是身份校验；只有人类实际批准后才应传入。
- `tag`、`publish`、`deploy --apply` 没有批准参数就失败；dry-run 只打印计划。
- 谁可以打 tag / push tag 由仓库权限决定；脚本不提升权限，也不绕过分支保护。
- `main` 只由人类合并；`publish` 只操作 tag，不合并、不推 main。
- tag 一经发布不可重复：

  ```bash
  # check 只警告，方便人类提前看到
  python3 scripts/release.py check

  # tag / publish 会失败，绝不覆盖
  python3 scripts/release.py tag --tag v4.4.0 --approved-by <human> --apply
  # RELEASE TAG: FAIL / tag v4.4.0 already exists; tags are immutable
  ```

- 发布内容错了：前向修复（新的 patch 版本）或用 `gh release edit` 修正说明；不要删除/移动已发布的 tag。
- `--push` 默认关闭，意味着“打 tag”和“公开 tag”是两次人类决定；确认要公开时才加 `--push`。

## 5. 一键部署（dry-run → apply → verify）

`scripts/deploy.py` 默认 dry-run；只有 `--apply` 才写工作区，并且必须带 `--approved-by`。

```bash
# 1. dry-run：只调用 bootstrap.py --dry-run，不写工作区
python3 scripts/deploy.py \
  --multica "$MULTICA_CLI_PATH" \
  --workspace-id "$MULTICA_WORKSPACE_ID" \
  --core-runtime "$KAR_CORE_RUNTIME_ID" \
  --qa-runtime "$KAR_QA_RUNTIME_ID" \
  --profile "$MULTICA_PROFILE"

# 2. 人类批准后 apply：bootstrap 自动备份，再 verify
python3 scripts/deploy.py \
  --multica "$MULTICA_CLI_PATH" \
  --workspace-id "$MULTICA_WORKSPACE_ID" \
  --core-runtime "$KAR_CORE_RUNTIME_ID" \
  --qa-runtime "$KAR_QA_RUNTIME_ID" \
  --profile "$MULTICA_PROFILE" \
  --apply --approved-by <human>

# 3. 只做检查、不更新已有对象
python3 scripts/deploy.py ... --apply --approved-by <human> --no-update
```

固定四步：

1. **version/spec check**：`VERSION` 与 `bootstrap.json.version` 一致；不导入/调用 Multica。
2. **bootstrap dry-run**：`bootstrap.py --dry-run`，带 Multica/workspace/runtime/backup 参数。
3. **bootstrap apply**：`bootstrap.py --apply --update`（除非 `--no-update`）；`--backup-dir` 默认 `backups/`，写入前自动备份。
4. **verify**：`verify.py` 按 `--multica` / `--workspace-id` / `--profile` 校验部署态。

行为：

- dry-run **只调用第 2 步**；第 3、4 步标记 `skipped`，并打印 `dry-run only; re-run with --apply --approved-by <human> to write`。
- apply 任一步失败立即停止，后续步骤标记 `skipped`，退出码 1；成功时打印步骤表、版本与 `deployed` 摘要。
- `--bootstrap-script` / `--verify-script` 可注入；以 `.py` 结尾时用当前 Python 解释器执行，其他路径直接执行。
- `--timeout` 默认 600 秒；超时按失败处理。
- `--json` 输出机器可读的步骤、退出码、错误和 `deployed` 状态。

步骤表示例：

```text
STEP                      EXIT    RESULT
------------------------------------------------
1 version/spec check      0       ok
2 bootstrap dry-run       0       ok
3 bootstrap apply         0       ok
4 verify                  0       ok
version: 4.4.0
deployed: yes (update=yes)
```

回滚方式：

```bash
# 用 bootstrap 写入前自动生成的快照恢复
python3 scripts/restore.py --backup backups/backup-<stamp>.json --workspace-id "$MULTICA_WORKSPACE_ID" --apply

# 再读回验证
python3 scripts/verify.py --workspace-id "$MULTICA_WORKSPACE_ID"
```

也可以回到上一版 release 的资产重新执行 `deploy.py`。恢复脚本不删除对象；`backups/` 不提交仓库。

## 6. 失败处理与回滚

发布流水线（`publish`）失败时，按“停在哪一步”处理：

| 失败步骤 | 已产生的副作用 | 处理 |
| --- | --- | --- |
| check | 无 | 修版本/CHANGELOG/配置路径/脏树后重跑；不会打 tag |
| build | `release/` 可能有不完整产物 | 修构建错误后重跑；没有 tag，可直接重来 |
| tag | 可能已创建本地 tag；push 失败时 tag 可能只在本地 | 不要重复创建；`git tag --list` 核对，修复远端权限后只重跑 `--push` 或进入下一步 |
| github-release | tag 已存在，Release 可能未创建 | 修复 `gh` 登录/参数后用同一 tag 与 artifact 重跑 `github-release` |
| attach | tag 与 Release 已存在，评论可能未发 | 修复 Multica 登录/权限后重跑 `attach`；避免重复评论 |

部署（`deploy.py`）失败时：

| 失败步骤 | 已产生的副作用 | 处理 |
| --- | --- | --- |
| version/spec check | 无 | 对齐 `VERSION` 与 `bootstrap.json` 后重跑 |
| bootstrap dry-run | 无 | 修参数/CLI 登录后重跑；不会写工作区 |
| bootstrap apply | 可能已部分写入；备份已生成 | **不要**直接重跑覆盖；先用 `restore.py` 恢复到备份，再修原因重跑 |
| verify | 工作区已写入 | 按 verify 报错修复；无法修复则 `restore.py` + 再 verify |

必须保留的证据：

- `backups/backup-<UTC>.json`：bootstrap 写入前快照，恢复的唯一依据。
- `release/KAR-Squad-Bootstrap-v{VERSION}.zip`：发布资产；`release/` 被 `.gitignore` 忽略，不提交。
- `release/RELEASE-NOTES-v{VERSION}.md` 与评论正文：发布说明与附件记录。
- 命令输出与退出码：`--json` 可直接进 CI 日志。

失败后不要做的事：

- 不删除或移动已发布的 tag；不 force push。
- 不删除工作区对象来“清理”；用备份恢复或前向修复。
- 不把失败的 `check` / `verify` 手动改成 PASS 再继续。

## 7. 安全

- 仓库里不写 token、密码、workspace ID、runtime ID、真实仓库 URL、人名；运行时通过参数或环境变量传入。
- `gh` 与 `multica` 依赖本机已有登录态；脚本不执行 `gh auth login` / `multica login`，也不读取或转述 token。
- 所有外部命令用参数数组执行，不使用 `shell=True`；命令打印用 `shlex.join`，避免空格/引号改变语义。
- `git` / `gh` / `multica` 路径可注入；CI 与单测使用 fake 可执行文件记录 argv，不访问网络、不创建真实 Release/评论。
- `release/`、`backups/` 已在 `.gitignore` 中；发布包与备份不进入提交。
- 最小权限：能 `check` / `plan` 的人不需要发布权限；打 tag、push tag、创建 Release、评论 issue 仍由具备对应权限的人类或经批准的执行者完成。
- 不可逆动作默认关闭：`--apply` 是显式开关，`--push` 是第二次显式开关，`--approved-by` 记录批准来源。

## 8. 常见错误表

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `bootstrap.json version X != VERSION Y` | 版本文件未同步 | 同步 `VERSION`、`bootstrap.json`、profile、配置手册与 CHANGELOG 后重跑 |
| `config handbook does not exist` | `bootstrap.json.config` 路径错误或文件缺失 | 修正路径/补文件；路径按仓库根解析 |
| `CHANGELOG.md has no '## X.Y.Z' heading` | 缺少对应版本段落 | 在 CHANGELOG 增加 `## X.Y.Z` 与变更条目 |
| `git working tree is dirty` | 有未提交/未跟踪文件 | 提交或清理；仅本地排错时用 `check --allow-dirty`，`publish --apply` 仍会失败 |
| `local tag vX.Y.Z already exists`（WARN） | tag 已存在 | 不要重复发布；需要新内容时升 patch 版本 |
| `tag vX.Y.Z already exists; tags are immutable` | 对已有 tag 执行 `tag --apply` / `publish --apply` | 不要覆盖；改用新版本，或对已存在的 tag 只补 Release/附件 |
| `tag vX.Y.Z != v{VERSION}` | 传入 tag 与 `VERSION` 不一致 | 修正 tag 或版本；`plan`/`tag`/`publish` 都会拒绝 |
| `artifact does not exist` | 发布包未构建或路径写错 | 先 `python3 scripts/build_release.py`，确认 `release/KAR-Squad-Bootstrap-vX.Y.Z.zip` |
| `gh release create exited N` | `gh` 未登录、无仓库权限、tag 未 push 或参数错误 | 看 stderr；补登录/权限或先 `tag --push`，再用同一 tag 重跑 |
| `multica issue comment add exited N` | `multica` 未登录、profile/workspace 不对、issue 无权限 | 用 `multica ... --help` 与当前工作区核对后重跑 `attach` |
| `--apply requires --approved-by <human>` | deploy apply 缺少批准参数 | 先取得人类批准，再带 `--approved-by <human>` |
| `DEPLOY: FAIL at step version/spec check` | `VERSION` 与 `bootstrap.json` 不一致或文件缺失 | 对齐版本后重跑；该步骤不会调用任何外部命令 |
| `DEPLOY: FAIL at step verify` | 部署态与包不一致 | 按 verify 报错修复；无法修复时用最近备份 `restore.py` 并重跑 verify |
| `timed out after Ns` | Multica/CLI 慢或网络/登录态异常 | 修环境后重跑；必要时增大 `--timeout`，不要盲目重复 apply |

相关文档：[`README.md`](../README.md)、[`CONTRIBUTING.md`](../CONTRIBUTING.md)、[`docs/BACKUP-RESTORE.md`](BACKUP-RESTORE.md)、[`docs/GATES.md`](GATES.md)、[`docs/ROADMAP.md`](ROADMAP.md)。
