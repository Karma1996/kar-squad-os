# 人类 WIP 与 SLA

目标：人类负载可控。Lead 不能因为 Agent 跑得快就一次塞给同一个人 5 张卡。

## 1. 规则

| 规则 | 数值 | 说明 |
| --- | --- | --- |
| 每个 Decision Owner 同时待决策 | ≤2 | 第 3 个起排队，不发出 |
| 24h 提醒 | 1 次 | 只提醒一次；之后继续等待 |
| 代批 | 禁止 | Agent 不 `/approve`、不默认通过、不替人签字 |
| 备份升级 | 由 Decision Owner 指定 | 没有备份且发起人失联时保持等待 |

“待决策”只统计 `gates.<gate>.status: pending` 且已记录 `requested_at` 的门；`approved` / `rejected` 不计。

## 2. 排队

- 按 `requested_at` 从早到晚排；前 2 个是 active，第 3 个起是 queued。
- queued 的门不删、不改结论，只在上一张卡解决后按序发出。
- 同一个 issue 的多道门也占名额：不会同时给同一人发 H1 和 H2。
- Program 有多个 Decision Owner 时按 owner 分别计数；不要把 A 的额度挪给 B。

## 3. 24h 提醒

- `age_hours >= 24` 且 `reminder_sent_at` 为空 → 提醒一次。
- 提醒只发一条，写 `reminder_sent_at` 与 `reminder_count: 1`；不改 `approved_at`、不改状态。
- 已提醒的门继续等待；周报里单列为 “after_reminder_waiting”，不视为通过。
- 第二次提醒不发；如果对方明确说“先放着”，继续等待并在决策台账记录。

## 4. 备份升级

Decision Owner 在 roster 或门卡回复里指定备份人：

- 备份人只在 Decision Owner 失联且明确授权范围内决策；没有授权不算数。
- 授权逐门记录（例如“H2 由 B 决定”），写入 manifest 的 `gates.<gate>.owner` 或决策台账。
- 没有备份或没有授权：保持等待，不代批、不自动通过。

## 5. 脚本

```bash
python3 scripts/human_wip.py check --manifests <docs-home> --json
```

输出：

```json
{
  "owners": {
    "<owner>": {
      "pending": 3,
      "over_limit": 1,
      "active": [{"issue": "KAR-42", "gate": "h1", "...": "..."}],
      "queued": [{"issue": "KAR-43", "gate": "h1", "...": "..."}],
      "reminders_due": []
    }
  },
  "totals": {"pending": 3, "queued": 1, "reminders_due": 0, "after_reminder_waiting": 0},
  "violations": []
}
```

- `--now <ISO>`：按指定时间评估，便于复盘与测试。
- `--limit 2`：默认每个 owner 2 个。
- 退出码 1 只用于**违规**（例如 Agent 批准、pending 有 `approved_at`），不用于排队。
- 脚本只报告；Lead 负责改门卡节奏、写 `reminder_sent_at`。

## 6. 周检查

每周摘要（[`docs/METRICS.md`](METRICS.md)）同时看：

- 是否有 owner 长期超 2 个待决策；
- 提醒后仍等待的时长；
- 人类动作数是否超过工作道上限（Quick 1、Standard 3、Program 4–5）。

超限先查流程（卡太多、拆得太碎、证据不足导致返工），不是让人多签。
