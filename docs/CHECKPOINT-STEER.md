# 草稿 checkpoint 与中途 steer

目标：人类在门禁卡发出前就能异步看到草稿并纠偏，不用等正式评审；纠偏有台账，不靠聊天记忆。

## 1. 草稿 checkpoint

H1（需求）与 H2（方案）发卡前：

1. 把草稿发布到 issue（评论里给文档链接 + 版本 + 一句话“这次想请你确认什么”）。
2. 至少提前 **10 分钟**发布，给人类异步 review；不要求人类到点守着。
3. 10 分钟内人类可以提改动；Lead 收敛后发正式 8 行门禁卡。
4. 草稿记录写入 manifest `checkpoints.<gate>_draft`。

```json
"checkpoints": {
  "h1_draft": {
    "published_at": "2026-11-03T07:30:00Z",
    "review_window_minutes": 10,
    "reviewers": ["<decision-owner-user-id>"],
    "outcome": "unchanged",
    "steer_ids": [],
    "note": "需求草案提前 30 分钟发布，无纠偏。"
  },
  "h2_draft": {
    "published_at": "2026-11-04T01:30:00Z",
    "review_window_minutes": 15,
    "reviewers": ["<decision-owner-user-id>"],
    "outcome": "steered",
    "steer_ids": ["ST-1"],
    "note": "设计草案 review 期间接受一次纠偏。"
  }
}
```

规则：

- `review_window_minutes` ≥ 10；`published_at` 至少比 `gates.<gate>.requested_at` 早 10 分钟。
- `outcome`：`unchanged`（无纠偏）或 `steered`（有纠偏）。
- `steered` 必须有 `steer_ids`，且每个 id 在 `steers` 里存在、gate 一致；`unchanged` 不得挂 steer。
- 草稿只提前发布，不提前批准；正式卡仍走 `/approve`。

## 2. 中途 steer

草稿期人类说“把 X 改成 Y”：

1. Lead 复述要改什么、影响哪些文档/AC/契约。
2. 判断是否影响已批准范围：影响 → 退回对应门；不影响 → 直接改并记 steer。
3. 写入 `steers` 决策台账，绑定改后的文档版本。
4. 重跑受影响检查；草稿 checkpoint 标记 `steered`。

```json
"steers": [
  {
    "id": "ST-1",
    "at": "2026-11-04T01:45:00Z",
    "gate": "h2",
    "from": "<decision-owner-user-id>",
    "summary": "重试改为 3 次，保持幂等键不变，不新增队列。",
    "applied": true,
    "version_after": "2.0",
    "recorded_by": "KAR-01-Lead"
  }
]
```

规则：

- 只能 steer `h1` / `h2`；批准后不再接受 steer，改动走退回或新 change set。
- `from` 必须是人类 Decision Owner（或其书面授权人）；`recorded_by` 是 Lead。
- `summary` 一句话（≤280 字符），写“改什么 + 约束”，不写过程。
- `applied: true` 时必须给 `version_after`，且等于对应文档版本（h1 → `docs.requirements.version`，h2 → `docs.design.version`）。
- 未落地：`applied: false` + `deferred_reason` + `deferred_approved_by`（人类书面同意延期），否则 H3 失败。
- steer 时间必须早于该门 `approved_at`。

## 3. 决策台账

`steers` + `gates` + `checkpoints` 三者构成决策台账：

| 记录 | 回答 |
| --- | --- |
| `gates.<gate>` | 谁在何时批准了哪个版本/SHA，理由与附条件 |
| `checkpoints.<gate>_draft` | 草稿何时发出、给了谁、多久、有没有纠偏 |
| `steers[]` | 草稿期改了什么、谁提的、何时落地、改到哪个版本 |

三者必须能对上：谁、何时、改了/批准了哪个版本、附了什么条件。对不上就是审计缺口。

## 4. 校验

```bash
python3 scripts/policy.py check --manifest <path>/delivery-manifest.json --profile h3
```

会检查：

- H1/H2 草稿是否存在、窗口 ≥10 分钟、发布早于门禁请求。
- `outcome` 与 `steer_ids` 一致；steer 必须被某道草稿引用，不能有孤儿。
- steer 的 gate、时间、`version_after` 与文档版本一致；延期必须有理由和人类批准人。
- 三道门（Quick 一道）都有 contact 记录，见 [`LEAD-TOUCHPOINTS.md`](LEAD-TOUCHPOINTS.md)。

## 5. 常见错误

| 现象 | 原因 | 修复 |
| --- | --- | --- |
| `draft must be published at least 10 minutes before` | 发卡太急 | 提前发布草稿，或等窗口满足 |
| `steer_ids: required when outcome is steered` | 口头改了但没记账 | 补 `steers` 并挂到 checkpoint |
| `steer ... not linked` | 有 steer 但 checkpoint 还是 `unchanged` | 改 outcome 并挂 id |
| `version_after must equal docs...` | 改完没升版本或版本写错 | 升文档版本并同步 manifest |
| `steer must be recorded before gates... approval` | 批后补账 | 批后改动走退回/新 change set |

## 6. 与人类交互的关系

- 草稿 review 不占一张门禁卡；正式卡仍是唯一需要 `/approve` 的动作。
- 人类动作数不变：Quick 1、Standard 3、Program 4–5；草稿是异步阅读，不是新门。
- 人类没看草稿不是阻塞：仍按 24h 提醒、只提醒一次、不代批。
