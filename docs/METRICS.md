# 指标采集与每周摘要

先采基线，再优化。v4.2 起每个变更集的 `delivery-manifest.json` 必须记录 5 项指标，每周生成一份 6 指标摘要。

## 1. 每个 issue 的 5 项指标

写入 `delivery-manifest.json` 的 `metrics`：

| 字段 | 含义 | 计数规则 |
| --- | --- | --- |
| `human_touches` | 人类决策次数 | 每次有效的 `/approve`、明确自然语言批准、选择/补充信息回复各计 1 次；同一门内的追问不重复计 |
| `wait_human` | 人类等待时长（小时） | 门卡发出到人类回应的累计时长；多道门相加，保留 1 位小数 |
| `rework_rounds` | 返工轮次 | 因 REQUEST_CHANGES / 退回 / 缺陷回流而重新派发的次数；同一轮多处修复计 1 次 |
| `candidate_recuts` | 候选重切次数 | 候选冻结后，因 late push、文档 SHA 变化或修复而重新 `freeze` 的次数 |
| `escaped_defects` | 逃逸缺陷数 | H3 之后发现、且本应由 A4/A5 拦截的缺陷；关闭 issue 时回填 |

示例：

```json
"metrics": {
  "human_touches": 3,
  "wait_human": 6.5,
  "rework_rounds": 1,
  "candidate_recuts": 2,
  "escaped_defects": 0,
  "cycle_time_hours": 42.0,
  "closed_at": "2026-11-06T02:10:00Z"
}
```

- `cycle_time_hours`：H1 卡发出到 H3 批准（或关闭）的时长；不填时报告脚本用 `gates.h1.requested_at → gates.h3.approved_at` 推导。
- `closed_at`：计入周汇总的时间；缺省时用 `gates.h3.approved_at`。
- 没填或填负数，`metrics.py --strict` 直接失败；不允许用 0 掩盖缺失。

## 2. 每周 6 指标摘要

```bash
python3 scripts/metrics.py report --manifests <docs-home> --format markdown
```

输出：

| 指标 | 周汇总方式 |
| --- | --- |
| `human_touches` | 求和 |
| `wait_human` | 平均（小时） |
| `rework_rounds` | 求和 |
| `candidate_recuts` | 求和 |
| `escaped_defects` | 求和 |
| `cycle_time_hours` | 平均（小时） |

按 `closed_at` 的 ISO 周（`YYYY-Www`）分组；未关闭或没有 H3 时间的 issue 单列，不混入周均值。

JSON 输出：

```bash
python3 scripts/metrics.py report --manifests <docs-home> --format json --strict
```

`--strict` 在有 issue 缺指标时退出码 1，适合放进周检查或 CI。

## 3. 两周基线

`--baseline-weeks 2`（默认）要求至少 2 个 ISO 周有完整数据才标记 `baseline.ready: true`：

```json
"baseline": {"weeks_required": 2, "weeks_collected": 2, "ready": true, "unclosed": []}
```

- 不足 2 周：只采集，不用指标做效率承诺或调并发。
- 达到 2 周：把基线数字写进复盘/配置提案，再决定是否优化。
- 基线不因某周特别差而剔除；异常周保留并注明原因。

## 4. 谁在什么时候记录

| 时点 | 动作 |
| --- | --- |
| 发门卡 | 写 `gates.<gate>.requested_at`；人类回应后补 `approved_at` / `human_touches` |
| 冻结/重切候选 | `candidate_recuts` +1（`freeze` 不改 metrics，由 Lead 记） |
| 退回/REQUEST_CHANGES | `rework_rounds` +1 |
| H3 批准 | 写入前 5 项（`escaped_defects` 可为 0，关闭时回填） |
| issue 关闭 | 回填 `escaped_defects` 与 `closed_at`，跑一次周摘要 |

## 5. 禁止

- 不用“感觉快了”代替指标；不挑周、不删异常值。
- 不用指标倒推个人绩效；指标用于发现流程问题。
- 不把 token、人名、真实仓库 URL 写进指标或报告。
