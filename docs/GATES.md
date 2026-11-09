# 审批清单（H1 / H2 / H3）

每道门固定 **3 项检查**，检查结果、理由与附条件都写入 `delivery-manifest.json` 的 `gates.<gate>`。人类只做决定；检查与证据由 Agent 准备并可复核。

## 1. 三道门的 3 项检查

### H1 需求确认

| id | 检查 | 通过证据 |
| --- | --- | --- |
| `scope` | 范围与验收标准同需求版本一致 | 需求文档 `version` + AC 编号；issue 范围声明 |
| `prototype` | 原型版本/SHA 与 manifest 一致（无原型记 `n/a` 并写原因） | 原型 `version`/`sha`/`mode`；H1 一并批准 |
| `evidence` | 证据可复现，无未关闭 S0–S2 | 评审记录、命令、退出码；缺陷清单 |

### H2 方案确认

| id | 检查 | 通过证据 |
| --- | --- | --- |
| `design` | 设计覆盖全部 P0/P1 FR/AC | 设计文档覆盖矩阵 |
| `contract` | 契约、迁移与回滚已定义 | 契约/迁移/回滚章节；无变化也要写明 |
| `testability` | A3 可执行，测试命令明确 | 测试设计 + 命令；A3 预审结论 |

### H3 验收与合并

| id | 检查 | 通过证据 |
| --- | --- | --- |
| `candidate` | candidate tag/digest 与各仓 head 一致 | `manifest.py check --profile h3` 输出 |
| `verdicts` | A4/A5 通过，无未关闭 S0–S2 | Reviewer/QA 结论 + 绑定的 tag |
| `ci` | CI 全绿且 head 一致 | `gh pr checks` / CI 记录 `head` |

检查项的 `result` 只能是 `pass` / `fail` / `n/a`；`fail` 不得批准，`n/a` 必须写 `note` 说明为什么不存在（例如无大型 UI）。

## 2. manifest 记录格式

```json
{
  "status": "approved",
  "requested_at": "2026-11-03T08:00:00Z",
  "approved_by": "<human-user-id>",
  "approver_type": "human",
  "approved_at": "2026-11-03T09:10:00Z",
  "rationale": "需求与原型覆盖全部 P0，范围未漂移。",
  "conditions": ["导出范围仅限本月"],
  "checks": [
    {"id": "scope", "result": "pass", "evidence": "需求 v1.2 §3 AC1–AC6"},
    {"id": "prototype", "result": "pass", "evidence": "原型 v1.0 sha cccc…"},
    {"id": "evidence", "result": "pass", "evidence": "evidence/reports/h1-review.md"}
  ]
}
```

- `rationale`：一句话，为什么可以过这道门；`manifest.py` 限制 280 字符。
- `conditions`：批准附条件；没有就写 `[]`，不要省略。
- `approved_by` + `approver_type: "human"`：**只有人类能批准**。`approver_type` 不是 `human` 时 `manifest.py check --profile h3` 直接失败。
- `requested_at`：卡片发出时间，用于 24h SLA 与 WIP 排队。

## 3. 人类看到的卡（8 行）

内部术语（H1/H2/H3、A4/A5、digest）不出现在卡上，但 3 项检查必须翻译成人类语言：

```text
🟡 需要你：确认方案（v2.0 / 9f8e7d）
谁决定：你（Decision Owner）
先看：1 页摘要 → <链接>；设计文档 → <链接>
我检查了：① 设计覆盖全部 P0 ② 契约/迁移/回滚已定义 ③ 测试可执行
理由：设计覆盖六个验收点，幂等键与回滚方案明确
附条件：无（有则写清，批准时一并记录）
回复：/approve　要改：直接说“把 X 改成 Y”
不做：停在这里，不会自动通过；24h 后只提醒一次
```

规则：

- 第一行是动作，不是背景；最多 3 个链接。
- “我检查了”一行对应 3 项检查；失败或 `n/a` 要在理由里说明。
- “理由”与“附条件”与 manifest 的 `rationale` / `conditions` 逐字一致，便于审计。
- 人类 `/approve` 或明确自然语言批准才有效；表情、沉默不算。

## 4. R3 第二人复核

`risk: "R3"` 时，H3 必须记录第二人复核：

```json
"second_reviewer": {
  "reviewer": "<user-id 或独立评审人>",
  "role": "security",
  "verdict": "pass",
  "at": "2026-11-05T16:00:00Z"
}
```

要求：

- 第二人不能是本变更集的主责 Developer/Reviewer，也不能是同一个 Agent 身份。
- 复核范围：安全/权限/密钥/数据不可逆/合规，以及 H3 的 3 项检查。
- `verdict` 只有 `pass` 才能进入 H3；`fail` 退回或 blocked，并在 manifest 记录原因。
- 第二人复核**不代替**人类批准：H3 仍由 Decision Owner `/approve`。

## 5. H3 10% 抽样

H3 前由 Lead 对本次变更集的门禁记录抽样复核，比例 **10%**，至少 1 道门：

- 标准变更集 `population = 3`（H1/H2/H3）→ 抽 1 道；Program 含拆分确认 `population = 4` → 抽 1 道。
- 抽样检查：3 项检查是否有证据、批准人是否为人类、rationale/conditions 是否与卡一致、绑定版本/SHA 是否正确。
- 记录写入 `gates.h3.sampling`：

```json
"sampling": {
  "rate": 0.1,
  "population": 3,
  "sampled": ["h1"],
  "reviewed_by": "<user-id>",
  "at": "2026-11-06T01:30:00Z",
  "note": "复核 H1 的 3 项检查与批准记录一致，无发现。"
}
```

`manifest.py check --profile h3` 会校验：rate=0.1、抽样数量 ≥ `ceil(0.1 × population)`、记录人与时间、note 非空。抽样发现橡皮图章或证据缺失时，H3 不得通过，退回对应门。

## 6. 与人类 WIP/SLA 的关系

- 每个 Decision Owner 同时待决策 ≤2；超过的由 Lead 排队，不一次发 3 张卡。见 [`docs/HUMAN-WIP.md`](HUMAN-WIP.md)。
- 24h 未回应只提醒一次；之后继续等待，**不代批、不自动通过**。
- 卡片、manifest、决策台账三处必须能对上：谁、何时、批准了哪个版本/标签、附了什么条件。
