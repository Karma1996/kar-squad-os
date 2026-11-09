# 候选冻结与 `manifest check`

`delivery-manifest.json` 是变更集的可审计快照。v4.2 起，A4/A5 不只绑定 branch/head，而是绑定一个可重建、可验证的候选标签：

```text
candidate/<ISSUE_KEY>-<digest>
```

示例：`candidate/KAR-42-dd31c919574d`。

## 1. 候选 digest 怎么来

digest 只由**候选输入**决定，不由审批、指标或 CI 记录决定：

| 输入 | 字段 |
| --- | --- |
| 变更集 | `change_set_id`、`issue`、`slug` |
| 文档 | `requirements`、`prototype`、`design`、`test_design`、`dev_notes` 的 `version` + `sha` |
| 代码 | 每个 repo 的 `repo_id`、`base`、`branch`、`head` |

算法：按上述字段构造对象 → `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)` → SHA-256 → 取前 12 位十六进制。

`qa_report` 是候选的验证产物，**不进入 digest**；QA 更新报告不会让候选失效。任何输入文档、分支或 head 变化都会改变 digest。

## 2. 命令

```bash
# 计算并可写回 digest/tag（默认 dry-run）
python3 scripts/manifest.py digest --manifest <path>/delivery-manifest.json --write

# 冻结：校验文件 SHA、各仓 head、PR、CI 后写入 candidate
python3 scripts/manifest.py freeze \
  --manifest <path>/delivery-manifest.json \
  --docs-root <docs-home> \
  --repo-root storefront=/path/to/storefront \
  --write

# A4/A5 使用的冻结校验
python3 scripts/manifest.py check \
  --manifest <path>/delivery-manifest.json \
  --docs-root <docs-home> \
  --repo-root storefront=/path/to/storefront \
  --profile freeze

# H3 前的完整校验（含外部 PR/CI）
python3 scripts/manifest.py check \
  --manifest <path>/delivery-manifest.json \
  --docs-root <docs-home> \
  --repo-root storefront=/path/to/storefront \
  --profile h3 --check-remotes --check-prs --check-ci
```

### profile

| profile | 校验内容 |
| --- | --- |
| `draft` | 结构、字段、gate 形状、metrics 类型；不要求文件存在或 head 可读 |
| `freeze` | 上述 + 文档/原型 SHA 与文件一致 + 各仓本地 head 一致 + PR 字段 + CI `passed` + candidate digest/tag/frozen_at |
| `h3` | 上述 + `risk` R0–R3 + 三道门各 3 项检查 + rationale/conditions + 人类批准 + R3 第二人 + H3 10% 抽样 + 5 项指标 |

### 退出码

- `0`：通过。
- `1`：有 ERROR（`--json` 可机读）。
- `2`：参数错误。

## 3. late push 如何使结论失效

`check --profile freeze|h3` 会比较 manifest 的 `repos[].head` 与本地 checkout 的实际 HEAD；加 `--check-remotes` 再比较 `git ls-remote <remote> refs/heads/<branch>`。任一不一致输出：

```text
LATE PUSH — manifest head bbbb…, storefront is at cccc…
```

此时：

1. A4/A5 结论作废，不得合并。
2. 重新运行受影响测试。
3. `freeze --write` 生成新 digest/tag。
4. Reviewer/QA 在新 tag 上重新出结论。

文档或原型 SHA 变化同理，报 `sha mismatch` 与 `STALE`。

## 4. 外部事实校验

| 开关 | 依赖 | 校验 |
| --- | --- | --- |
| `--check-remotes` | `git` | `repos[].head` 与远端分支一致 |
| `--check-prs` | `gh` | `gh pr view <pr> --json headRefOid,state`：head 一致、PR 为 OPEN |
| `--check-ci` | `gh` | `gh pr checks <pr> --json bucket`：全部为 `pass` |

CI 记录本身在 `repos[].ci`：`status`、`head`、`url`、`checked_at`。`head` 必须等于 `repos[].head`，`status` 必须为 `passed` 才能冻结。`--check-ci` 是对 GitHub 的二次核对；没有 `gh`/网络时至少保留 manifest 内的一致性校验。

## 5. 最小结构

```json
{
  "version": 2,
  "change_set_id": "KAR-42",
  "issue": "KAR-42",
  "slug": "checkout-idempotency",
  "risk": "R2",
  "decision_owner": "<user-id>",
  "docs": {
    "requirements": {"path": "...", "version": "1.2", "sha": "<64 hex>"},
    "prototype": {"path": "...", "version": "1.0", "sha": "<64 hex>", "mode": "B", "approved_by": "<user-id>", "approved_at": "<time>"},
    "design": {"path": "...", "version": "2.0", "sha": "<64 hex>"},
    "test_design": {"path": "...", "version": "1.0", "sha": "<64 hex>"},
    "dev_notes": {"path": "...", "version": "1.0", "sha": "<64 hex>"},
    "qa_report": {"path": "...", "version": "1.0", "sha": "<64 hex>"}
  },
  "repos": [{
    "repo_id": "storefront",
    "remote": "git@github.com:org/storefront.git",
    "base": "develop",
    "branch": "feat/KAR-42-checkout-idempotency",
    "head": "<40 hex>",
    "pr": "https://github.com/org/storefront/pull/42",
    "merge_order": 1,
    "ci": {"status": "passed", "head": "<40 hex>", "url": "...", "checked_at": "<time>"}
  }],
  "candidate": {"digest": "<12 hex>", "tag": "candidate/KAR-42-<digest>", "frozen_at": "<time>"},
  "gates": {"h1": {}, "h2": {}, "h3": {}},
  "metrics": {},
  "merge_receipts": []
}
```

完整可运行示例：[`docs/examples/delivery-manifest.json`](examples/delivery-manifest.json)。门的字段与检查项见 [`docs/GATES.md`](GATES.md)，指标见 [`docs/METRICS.md`](METRICS.md)。

## 6. 运行时怎么用

- **Developer（A4 候选）**：push 后写 manifest，跑 `freeze --write` + `check --profile freeze`，把 tag、digest、命令与退出码写进 HANDOFF。
- **Reviewer/QA**：先跑 `check --profile freeze`，结论标题绑定同一个 tag；head 或 tag 变了，旧结论作废。
- **Lead（H3）**：跑 `check --profile h3 --check-remotes --check-prs --check-ci`；只有通过才发 H3 卡，卡上绑定 tag（对人可写短 SHA）。
- **合并后**：回填 `merge_receipts`；归档时保留 manifest，digest 不重算。
