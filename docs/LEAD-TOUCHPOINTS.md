# Lead 接触点预算

Lead 只在 **6 类接触点** 找人类。其他时间自己查、自己做、自己验证，然后在评论里报告结果。

## 1. 六个接触点

| 接触点 | 用途 | 预算/变更集 | 典型形式 |
| --- | --- | --- | --- |
| `intake` | 判道、风险级别、Decision Owner/roster、范围澄清 | 1 | intake 评论 / 首张卡 |
| `contract` | 跨工作流契约、拆分方案、接口/数据边界 | 1（Program 必填） | SPLIT PLAN / 契约确认 |
| `gates` | H1 / H2 / H3 门禁卡（Quick 只有 1 张） | 3（Quick 1） | 8 行卡 + `/approve` |
| `integration` | 集成分支、跨仓联调、需要人类取舍的集成结果 | 1 | 集成报告 + 一个问题 |
| `merge` | 合并列车阻塞、回滚/前向修复选择 | 1 | 阻塞卡 |
| `exception` | 阻塞、事故、S0/S1、需要人类访问/授权 | 按需，必须写原因 | 异常卡 |

六类以外的人类交互都算越界：例如“顺便确认一下文案”“帮忙看下这个 diff”“你觉得这个命名好吗”。这些先自己判断或交回对应 Agent，不找人。

## 2. manifest 记录

```json
"lane": "standard",
"touchpoints": [
  {"kind": "intake", "at": "2026-11-03T07:20:00Z", "actor": "<decision-owner-user-id>", "summary": "intake 确认 Standard、R3 与 Decision Owner。"},
  {"kind": "contract", "at": "2026-11-03T12:00:00Z", "actor": "<decision-owner-user-id>", "summary": "确认幂等键契约。"},
  {"kind": "gates", "gate": "h1", "at": "2026-11-03T08:00:00Z", "actor": "<decision-owner-user-id>"},
  {"kind": "gates", "gate": "h2", "at": "2026-11-04T02:00:00Z", "actor": "<decision-owner-user-id>"},
  {"kind": "gates", "gate": "h3", "at": "2026-11-05T11:00:00Z", "actor": "<decision-owner-user-id>"},
  {"kind": "exception", "at": "2026-11-05T12:00:00Z", "actor": "<decision-owner-user-id>", "reason": "CI 环境密钥缺失，需要人类在 Web 设置页补配。"}
]
```

规则：

- `kind` 只能是六类之一；`actor` 是实际被联系的人；`gate` 只用于 `gates`。
- `intake` ≤1、`contract` ≤1、`gates` ≤3（Quick 1）、`integration` ≤1、`merge` ≤1。
- `exception` 必须写 `reason`，说明为什么不能在六类常规接触点内解决。
- H3 校验 `intake` 与三道门（Quick 一道）都有记录；Program 还要求 `contract`。

## 3. 什么算 / 不算接触点

| 算 | 不算（自己做完再报告） |
| --- | --- |
| 让人类选方案/范围/优先级 | 自己读代码、查文档、跑测试 |
| 让人类批准门/合并 | 在评论里汇报“已完成、证据如下” |
| 让人类提供访问/密钥/权限 | 自己修复可复现的 CI 失败 |
| 让人类接受残余风险/延期 | 自己按项目事实做技术取舍 |
| S0/S1/阻塞需要人类决定 | 礼貌性 @、同步进度、征求意见 |

## 4. 超出预算时

1. 先问自己：这件事 Agent 能不能做？能 → 直接做，不找人。
2. 不能做 → 归到最接近的常规接触点（多数是 `exception`），写清原因和需要的动作。
3. 同一变更集同类接触点已用完 → 合并到下一次门禁卡，不新开一张卡。
4. 人类 WIP ≤2：超出的卡排队，等前一张解决；不并发轰炸。

## 5. 校验

```bash
python3 scripts/policy.py check --manifest <path>/delivery-manifest.json --profile h3
```

- 未知 `kind`、超预算、重复 gate、缺 gate 记录、`exception` 无原因 → FAIL。
- Quick 车道只允许 1 张门禁卡（`gate: "quick"`）；Standard/Program 允许 H1–H3。

## 6. 与人类动作数的关系

接触点预算约束的是 **Lead 找人的次数**；人类动作数约束的是 **人类要做的决定数**。二者一致时最健康：

| 工作道 | 人类动作 | 接触点上限（常规） |
| --- | --- | --- |
| Quick | 1 | intake + 1 gate + merge = 3 |
| Standard | 3 | intake + contract + 3 gates + integration + merge = 7 |
| Program | 4–5 | 上述 + contract 拆分确认 |

`exception` 不设硬上限，但每一次都要能解释为什么常规流程解决不了。
