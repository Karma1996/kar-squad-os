# 风险分级产物矩阵

产物数量和风险级别绑定：风险越高，要求越全；低风险不靠“多写文档”换安全感。矩阵由 `scripts/policy.py check --profile h3` 在 H3 强制校验。

## 1. 矩阵

| 风险 | 正式产物 | 必含 | 说明 |
| --- | --- | --- | --- |
| **R0 / R1** | 1–3 份 | 无 | issue 记录、PR、测试证据即可；Quick 不强制正式 HTML |
| **R2** | 3 份 | 需求分析、方案设计、测试设计与用例 | 跨模块/契约/迁移/权限/依赖升级 |
| **R3** | ≥6 份 | 上述三份 + 开发交付说明、测试验收文档、安全 overlay；触发原型时再加交互原型 | 认证授权、支付计费、密钥、不可逆数据、合规 |
| **Program 子级** | 1–2 份 | 开发交付说明 | 至多再加一份需求/设计摘要；验收并入父级，不重复父级证据 |

- “全量”指五份固定文档 + 安全 overlay；原型按第 5 节条件触发。原型一旦绑定（`docs.prototype` 存在），R3 必须把它计入产物。
- Program 子级继承父级安全 overlay、门禁、草稿/steer 与接触点记录；子级 manifest 记 `program_child: true` 时只校验产物预算（1–2 份），其余治理块归父级。子级若自身触碰 R3 范围，由父级 H3 统一复核。
- 复盘文档按需，不计入矩阵上限。

## 2. manifest 记录

```json
"lane": "standard",
"program_child": false,
"artifacts": [
  {"kind": "requirements", "ref": "multica/requirements/KAR-42-checkout-idempotency/需求分析文档.html", "version": "1.2"},
  {"kind": "design", "ref": ".../方案设计文档.html", "version": "2.0"},
  {"kind": "test_design", "ref": ".../测试设计与用例.html", "version": "1.0"}
]
```

字段：

- `kind`：固定枚举，见下；同一变更集每种最多一条。
- `ref`：文档路径、PR URL 或 issue 评论引用，必须能定位到证据。
- `version`：可选；正式文档填文档控制区的版本。

`kind` 枚举：`requirements` / `prototype` / `design` / `test_design` / `dev_notes` / `qa_report` / `security_overlay` / `issue_record` / `pr` / `test_evidence` / `retro`。

## 3. 各风险的最小示例

**R1（Quick）**

```json
"artifacts": [
  {"kind": "issue_record", "ref": "KAR-77 评论 01a1..."},
  {"kind": "pr", "ref": "https://github.com/example/app/pull/77"},
  {"kind": "test_evidence", "ref": "evidence/logs/unit-77.log"}
]
```

**R2（Standard）**

```json
"artifacts": [
  {"kind": "requirements", "ref": ".../需求分析文档.html", "version": "1.1"},
  {"kind": "design", "ref": ".../方案设计文档.html", "version": "1.0"},
  {"kind": "test_design", "ref": ".../测试设计与用例.html", "version": "1.0"}
]
```

开发交付说明与验收记录并入 PR 描述、manifest 证据与 `qa_report` 文档，不再单独占额度。

**Program 子级**

```json
"program_child": true,
"artifacts": [
  {"kind": "dev_notes", "ref": "workstreams/payment/开发交付说明.html", "version": "1.0"},
  {"kind": "design", "ref": "workstreams/payment/设计说明.html", "version": "1.0"}
]
```

## 4. 校验

```bash
python3 scripts/policy.py check --manifest <path>/delivery-manifest.json --profile h3
python3 scripts/policy.py matrix      # 打印矩阵
```

规则：

- 数量超出上限或低于下限 → FAIL。
- R2 缺任一必含产物、R3 缺任一固定产物或安全 overlay → FAIL。
- 同一 `kind` 重复、`ref` 为空、未知 `kind` → FAIL。
- 不足额时不要补“凑数文档”；先判断风险级别是否判错，再补真实产物。

## 5. 与其它文档的关系

- 文档目录与命名：[`kar-docs-manifest`](../skills/kar-docs-manifest/SKILL.md)。
- R3 安全 overlay：[`SECURITY-OVERLAY.md`](SECURITY-OVERLAY.md)。
- manifest 字段总览：[`MANIFEST.md`](MANIFEST.md)。
- 门禁检查：[`GATES.md`](GATES.md)。
