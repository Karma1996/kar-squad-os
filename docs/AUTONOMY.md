# 低风险 24h 默认与假设

目标：R0/R1 的可逆小改动不必因为人类一时没看卡就无限等待；沉默 24 小时后按一份**写清楚、可推翻**的假设继续。**H3 仍是人类决定，假设永远不能代替合并批准。**

## 1. 适用边界

同时满足才可启用：

| 条件 | 要求 |
| --- | --- |
| 风险 | 仅 R0 / R1 |
| 可逆 | `autonomy.reversible: true`，能直接 revert |
| 外部契约 | 无；必须显式 `external_contract: false` |
| 层级 | 不是 Program 子级（子级继承父级门禁） |
| 项目 opt-in | 人类在项目层记录 `by / at / scope`，默认关闭 |
| 等待 | H1 卡发出满 ≥24h，且只提醒一次 |
| 假设 | 一句话写清“按什么条件推进”，归属 Decision Owner |

不满足任一项：走正常 H1，不记 `autonomy`。R2/R3、迁移、认证/支付、公共接口、不可逆数据一律排除。

## 2. 24 小时流程

```text
H1 卡发出（记 wait_started_at）
  → 满 24h 发一次提醒（notification）
  → 人类无回复：记 assumption + assumed_at，gates.h1.status = assumed
  → 继续实现；H2 照常人类批准
  → H3 仍由人类 /approve；假设只影响 H1 的沉默等待
```

- 人类在 24h 内回复：按正常 H1 走，不写 `autonomy`（若已写且提前批准，校验会提示改为普通 H1）。
- 24h 后人类回复“改 X”：按 steer 流程处理；若超出已批准范围，退回 H1。
- 人类回复“不同意/停”：记 `override`，`state: overridden`，H3 失败，必须重做或重新走 H1。

## 3. 项目级 opt-in

项目描述只写差异（`squad-overlay`）：

```json
{
  "autonomy": {
    "enabled": true,
    "opted_in_by": "<decision-owner-user-id>",
    "opted_in_at": "2026-10-30T08:00:00Z",
    "scope": "repo:storefront"
  }
}
```

- 只能由人类 opt-in；Agent 不能代开。
- 项目级 opt-out 随时生效，只影响之后的 H1，不追溯已记录的假设。
- 小队默认值见 `kar-squad-profile/squad.json` 的 `autonomy` 块（默认 `enabled_by_default: false`）。

## 4. manifest 记录

```json
"autonomy": {
  "project_opt_in": {"by": "<decision-owner-user-id>", "at": "2026-10-30T08:00:00Z", "scope": "repo:storefront"},
  "reversible": true,
  "external_contract": false,
  "window_hours": 24,
  "wait_started_at": "2026-11-01T09:00:00Z",
  "notification": {"at": "2026-11-02T09:00:00Z", "actor": "<decision-owner-user-id>", "channel": "issue comment"},
  "assumption": {
    "statement": "沿用现有断言与测试命令，仅把固定 sleep 改为条件等待；若人类否决则回到 H1。",
    "owner": "<decision-owner-user-id>",
    "recorded_at": "2026-11-02T09:05:00Z",
    "expires_at": "2026-11-09T09:00:00Z"
  },
  "state": "assumed",
  "assumed_at": "2026-11-02T09:00:00Z"
}
```

对应的 H1 门：

```json
"gates": {
  "h1": {
    "status": "assumed",
    "requested_at": "2026-11-01T09:00:00Z",
    "assumed_at": "2026-11-02T09:00:00Z",
    "approver_type": "assumption",
    "rationale": "R1 可逆改动，静默 24h 后按假设推进；H3 仍需人类批准。",
    "conditions": [],
    "checks": [
      {"id": "scope", "result": "pass", "evidence": "需求分析文档 v1.0 §2"},
      {"id": "prototype", "result": "n/a", "evidence": "无界面变更", "note": "纯测试修复"},
      {"id": "evidence", "result": "pass", "evidence": "24h 提醒与假设记录"}
    ]
  }
}
```

字段规则：

- `window_hours` ≥24；`assumed_at` 必须 ≥ `wait_started_at + window_hours`。
- `notification.at` 不得早于 24h 窗口结束，也不得晚于 `assumed_at`；只提醒一次。
- `state`：`assumed` / `approved` / `overridden`。
- `assumed` 必须与 `gates.h1.status` 一致，`approver_type: assumption`；H1 不写 `approved_by/approved_at`。
- `approved`：人类在假设生效后批准；`gates.h1.approved_at` 不得早于 `assumed_at`。
- `overridden`：H3 失败，必须重做并恢复人类门；`override` 记录 `by / at / decision / reason`。
- `override.decision: human_gate_restored`：必须回到人类 H1 批准，H3 才可能通过。

## 5. H1 可推翻

允许的推翻方式：

| 人类说 | 记录 | 结果 |
| --- | --- | --- |
| “不同意这个假设，先停” | `state: overridden` + `override.decision: rejected` | H3 FAIL，重做/重走 H1 |
| “恢复 H1，我来批” | `override.decision: human_gate_restored` | H1 必须人类批准，之后才能 H3 |
| “按这个假设继续” | `state: assumed` 保持不变 | 照常 H2/H3 |
| “把 X 改成 Y” | `steers` + 文档升版 | 超出范围则退回 H1 |

推翻是人类的权利，不需要解释成本；Agent 不得争辩或把假设当作已批准。

## 6. H3 与人类动作数

- H3 永远需要人类 `/approve`；`assumed` 只替代 H1 的沉默等待。
- 人类动作数不变：Quick 1、Standard 3、Program 4–5。
- 假设期间不产生额外接触点；24h 提醒属于 gate 接触点，不新开卡。
- 若假设被推翻，恢复 H1 后重新计数人类动作，不静默继续。

## 7. 校验

```bash
python3 scripts/autonomy.py check --manifest <path>/delivery-manifest.json --profile h3
python3 scripts/autonomy.py deadline --manifest <path>/delivery-manifest.json
python3 scripts/policy.py check --manifest <path>/delivery-manifest.json --profile h3
```

`policy.py` 在 H3 强制同一套规则；`manifest.py check --profile h3` 也会经 `validate_policy` 校验。完整示例：[`examples/low-risk-manifest.json`](examples/low-risk-manifest.json)。

## 8. 常见错误

| 现象 | 原因 | 修复 |
| --- | --- | --- |
| `only R0/R1 may use the 24h default` | 风险级别不适用 | 回到正常 H1 |
| `window_hours: must be >= 24 hours` | 想缩短等待 | 不允许；等待满 24h |
| `24h window has not elapsed` | 假设写早了 | 等窗口结束再记，或删掉 autonomy 走正常 H1 |
| `notification.at: may not precede the 24h window` | 提醒发早了 | 满 24h 只提醒一次 |
| `requires gates.h1.status=assumed` | 只写了 autonomy，没改门 | 同步 H1 记录 |
| `human rejected the assumption` | 人类已推翻 | 停止，重做/重走 H1 |
| `normal early H1 approval should not carry an autonomy block` | 人类提前批准却仍记假设 | 删除 autonomy，按普通 H1 记录 |
