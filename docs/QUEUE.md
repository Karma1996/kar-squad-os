# 队列抢占与派发

`scripts/queue.py` 是 Lead 的**确定性调度器**：输入当前运行中与排队中的工作项，输出抢占决策与统一派发顺序。它只解决“谁先跑”，不改变门禁、验收标准和人类动作。

## 1. 为什么需要队列

S0/S1 事故、Program 合并窗口和 Quick 小修会同时到达。如果只靠 Lead 临场判断，会出现三个问题：

- 同 severity 的工作没有稳定顺序，不同人排出的队列不一致；
- S0/S1 抢占没有记录，事后无法解释谁挤掉了谁；
- Program 合并窗口被随意插队，Quick 的 FIFO 承诺失效。

`queue.py` 把规则写成可测试的排序键和抢占矩阵，让 Lead 每次得到同一份结果。抢占只表示“先执行谁”，被抢占项不丢失进度，也不跳过任何门。

## 2. 排序规则表

排队项按以下**总序**排序，键依次比较，前一个相同才看后一个：

| 顺序 | 键 | 取值 | 说明 |
| ---: | --- | --- | --- |
| 1 | `severity_rank` | S0=0，S1=1，S2=2，S3=3，S4=4 | 严重度高的先派发 |
| 2 | `window_priority` | 合并窗口开放=0，其他=1 | 只对 Program 且窗口开放生效 |
| 3 | `enqueued_at` | RFC3339 时间升序 | 同 severity、同窗口优先级时先入队先派发 |
| 4 | `id` | 字符串升序 | 同刻入队的确定性兜底，避免输入顺序影响结果 |

实现上就是：

```text
(severity_rank, window_priority, enqueued_at, id)
```

规则说明：

- **Program 合并窗口优先**：`lane=program` 且带 `program_merge_window`，并且 `open_at <= now <= close_at`（两端都包含）时，`window_priority=0`。同 severity 下它会排在窗口未开放或没有窗口的项之前。
- **窗口已关闭**：`now > close_at` 不算错误，只给 WARN“窗口已关闭，按普通 Program 处理”，`window_priority` 按 1 处理。
- **窗口未开放**：`now < open_at` 同样按 1 处理，不提前派发。
- **Quick FIFO**：Quick 项之间不插入任何 lane 优先级；同 severity 的 Quick 严格按 `enqueued_at`（再按 `id`）执行。Program 开放窗口是唯一允许越过同 severity Quick 的例外。
- **同 severity 按入队时间**：Standard/Program（窗口未开放或已关闭）与 Quick 在同一 severity 下都走 `enqueued_at`，不额外抬高 lane。

## 3. 抢占矩阵

只有**排队中**的 S0/S1 会抢占**运行中**的工作项；排队项之间只比派发顺序，不互相“抢占”。

| 运行项 \ 排队项 | 排队 S0 | 排队 S1 |
| --- | :---: | :---: |
| 运行 S0 | 否 | 否 |
| 运行 S1 | **是** | 否 |
| 运行 S2 | **是** | **是** |
| 运行 S3 | **是** | **是** |
| 运行 S4 | **是** | **是** |

补充规则：

- 排队 S0 抢占所有非 S0 运行项；排队 S1 抢占 S2–S4 运行项，**不限 lane**。
- S0 永不被抢占；S1 不会被另一个 S1 抢占（但会被排队 S0 抢占）。
- 每个被抢占的运行项只输出**一条**记录。若有多个排队项都能抢占它，选派发顺序最靠前的那个（最高优先级），写入 `by_queued_id`。
- `preemptions` 按 `running_id` 排序，保证同一输入输出稳定。
- 原因字符串会写明命中的规则，例如 `S0 抢占`、`S1 抢占`、`Program 合并窗口开放（12:00 关闭）`、`Quick FIFO`、`同 severity 按入队时间`。

## 4. 输入/输出示例

输入 `queue.json`：

```json
{
  "now": "2026-11-10T09:00:00Z",
  "running": [
    {"id": "run-1", "issue": "KAR-2", "lane": "standard", "severity": "S3", "started_at": "2026-11-10T08:00:00Z"}
  ],
  "queued": [
    {"id": "q-1", "issue": "KAR-3", "lane": "quick", "severity": "S1", "enqueued_at": "2026-11-10T08:30:00Z"},
    {"id": "q-2", "issue": "KAR-4", "lane": "program", "severity": "S2", "enqueued_at": "2026-11-09T10:00:00Z",
     "program_merge_window": {"open_at": "2026-11-10T08:30:00Z", "close_at": "2026-11-10T12:00:00Z"}}
  ]
}
```

`python3 scripts/queue.py plan --queue queue.json` 输出：

```text
NOW 2026-11-10T09:00:00Z

派发顺序
  #  ID   ISSUE  LANE     SEVERITY  REASON
  1  q-1  KAR-3  quick    S1        S1 抢占
  2  q-2  KAR-4  program  S2        Program 合并窗口开放（12:00 关闭）

抢占
  RUNNING  ISSUE  BY_QUEUED  REASON
  run-1    KAR-2  q-1        S1 抢占 S2–S4 运行项

结论：2 个排队项；1 个运行项被抢占；1 个 Program 合并窗口开放。
```

`--json` 输出同一结论，便于其他脚本消费：

```json
{
  "ok": true,
  "now": "2026-11-10T09:00:00Z",
  "dispatch": [
    {"rank": 1, "id": "q-1", "issue": "KAR-3", "lane": "quick", "severity": "S1", "reason": "S1 抢占"},
    {"rank": 2, "id": "q-2", "issue": "KAR-4", "lane": "program", "severity": "S2", "reason": "Program 合并窗口开放（12:00 关闭）"}
  ],
  "preemptions": [
    {"running_id": "run-1", "running_issue": "KAR-2", "by_queued_id": "q-1", "reason": "S1 抢占 S2–S4 运行项"}
  ],
  "errors": [],
  "warnings": []
}
```

字段约定：

- 文件里的 `now` 可省略，省略时用当前 UTC；`plan --now <iso>` 覆盖文件值。
- `running` / `queued` 缺失时按空列表处理并给 WARN；类型不是列表则 FAIL。
- 未知字段忽略，不报错。
- `program_merge_window` 只允许出现在 `lane=program` 的排队项上。

## 5. 与门禁/人类动作/WIP 的关系

抢占是**执行顺序**，不是流程豁免：

- **不改门禁**：被抢占项恢复后仍要过原来的 H1/H2/H3，Quick 仍只有一张门禁卡；S0/S1 也仍需人类批准，不因抢占获得自动合并权。
- **不改人类动作数**：Quick 1 次、Standard 3 次、Program 4–5 次不变；抢占不新增门，也不消耗额外人类审批。
- **不改 WIP**：人类待决策仍受 ≤2 限制；被抢占不代表增加一位 Decision Owner 的并发卡。
- **保留现场**：被抢占项保留 branch / head / write_lock，不重置工作区，不丢弃未提交或未推送的成果。
- **恢复时重跑测试**：恢复执行前先重跑受影响的测试；如果 head 变化，重新核对 candidate tag/digest 与测试证据。
- **一个 issue 一个写者**：同一 issue 同时只允许一个写者；抢占只是暂停，不是复制出第二个执行者。

## 6. 校验命令

```bash
# 只校验 schema，不计算派发
python3 scripts/queue.py check --queue queue.json

# 校验并计算派发顺序 + 抢占
python3 scripts/queue.py plan --queue queue.json --now 2026-11-10T09:00:00Z

# 机器可读
python3 scripts/queue.py plan --queue queue.json --json
```

退出码：`0` 表示通过/成功，`1` 表示校验失败或用法错误。`check` 只做 schema 校验；`plan` 先跑同一套校验，通过后才计算。

## 7. 常见错误表

| 错误/现象 | 原因 | 处理 |
| --- | --- | --- |
| `queued[1].severity: expected one of S0, S1, S2, S3, S4` | severity 非法或缺失 | 改为 S0–S4 |
| `queued[0].lane: expected one of quick, standard, program` | lane 非法或缺失 | 改为 quick / standard / program |
| `queued[0].id: required non-empty string` | 排队项没有 id | 补唯一 id |
| `queued[0].id: duplicate id q-1 (already used by running[0])` | running + queued 内 id 重复 | 改成全局唯一 id |
| `queued[0].issue: required non-empty string` | 缺 issue | 补 issue 键 |
| `queued[0].program_merge_window: only allowed on lane=program` | Quick/Standard 带了合并窗口 | 删掉窗口，或把 lane 改成 program |
| `queued[0].program_merge_window: close_at must be after open_at` | 窗口关闭时间 ≤ 开放时间 | 修正两个时间 |
| `queued[0].enqueued_at: invalid RFC3339 timestamp` | 时间格式错误 | 用 RFC3339，例如 `2026-11-10T08:30:00Z` |
| `running[0].started_at: required RFC3339 timestamp` | 缺开始时间 | 补 `started_at` |
| `queued: expected a list` | `queued` 不是数组 | 改成 `[]` 或数组 |
| `WARN: ... 窗口已关闭，按普通 Program 处理` | 窗口已过 `close_at` | 不是错误；按普通 Program 排序，必要时更新窗口 |
| `WARN: running: missing; treated as []` | 省略了 `running` | 明确写 `[]` 可消除警告 |
