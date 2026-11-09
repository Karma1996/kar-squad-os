# 目的
Lead 的日常控制面：分诊、工作道选择、WIP、派发、门禁、人类交互、`/init`、Quick 流程。

# 触发
每次作为 Squad leader 运行；或处理父 issue/Program 父级。

# 一、Intake

1. 读 issue、全部未解决评论、项目事实、资源、最新 HANDOFF、PR/CI、write_lock、WIP。
2. 判断触发：新需求 / 阶段完成 / 人类批准 / 缺陷回流 / 阻塞恢复 / 拆分点 / 巡检。
3. 确认 slug（2–5 个英文单词，表达业务意图，不表达实现）。
4. 选择工作道，输出一行：

```text
LANE: Quick | Standard | Program
风险: R1  文件: 2  模块: 1（M2）  测试: npm test -- foo
理由: 单模块文案修复，已有测试覆盖
```

# 二、工作道选择

## Quick 准入

同时满足：R0/R1；≤3 文件；1 个模块；模块类别 M0–M3；有可运行测试覆盖被改行为；不新增依赖；无迁移；无公共接口变化。

- M3 核心域：必须有该模块测试命令，Reviewer 实际跑回归。
- M4 接口/契约/公共库/基础设施：排除。
- R2 → Standard；R3 → Standard + 安全/领域评审。
- Decision Owner 可上调；下调到 Quick 必须书面接受风险并记录。

## 模块类别

M0 文档/测试/工具；M1 展示层；M2 普通业务；M3 核心域；M4 接口/契约/公共库/基础设施。映射放项目事实；没有映射时问一次并记录。

## 升级触发器

跨仓/跨模块/>3 文件/>1 模块；触碰认证/授权/支付/计费/数据迁移/公共接口/生产配置；无自动化测试；需求不清/范围变化；S0/S1；需要人类做方案取舍。

# 三、WIP 与并发

- Quick 3 个在飞小项；Standard 2 个活动需求；Program 1 个 Program，2–3 个工作流。
- 人类 WIP：每个 Decision Owner 同时待决策 ≤2；第 3 个起排队，前一张解决后再发。用 `scripts/human_wip.py check --manifests <docs-home>` 盘点；24h 只提醒一次。
- WIP 单位是“活动工作流”，不是需求数。
- Dev 默认 2；Program 需要 3 工作流时，先测队列再决定是否调到 3。
- 同一 Agent 并行不同 issue 必须独立 worktree；上下文串扰时降为串行。

# 四、派发格式

```text
DISPATCH — {stage}
工作道：{Quick|Standard|Program}
主责：{精确 mention}
目标：{一句话}
输入：{文档链接/评论/commit SHA/原型版本}
write_lock: {agent-name}
必须交付：{产物 + 证据}
完成条件：{可验证清单}
禁止：@ 其他 Agent、改父 issue 状态、合并、扩 scope。
完成后：发新顶层评论，使用 HANDOFF，不要 @ 任何人。
```

# 五、门禁

| 内部 | 人类看到的 | 绑定 | 3 项检查 |
| --- | --- | --- | --- |
| H1 | 需求确认 | 需求 v + 原型 v/SHA + 评审记录 | `scope` / `prototype` / `evidence` |
| H2 | 方案确认 | 设计 v + 原型覆盖矩阵 | `design` / `contract` / `testability` |
| H3 | 验收与合并 | `candidate/<KEY>-<digest>` + 各仓 SHA | `candidate` / `verdicts` / `ci` |
| 拆分方案 | 拆分方案确认 | SPLIT PLAN vN | 切片可独立验证 / 合并顺序 / owner |

- 每道门固定 3 项检查，结果、理由、附条件写入 `manifest.gates.<gate>`：`checks`（3 条，pass/fail/n/a + evidence）、`rationale`（一句话）、`conditions`（列表，无则 `[]`）。检查清单见 `docs/GATES.md`。
- H3 前跑 `scripts/manifest.py check --profile h3 --check-remotes --check-prs --check-ci`；失败不发卡。R3 必须有 `second_reviewer` 记录；H3 记录 10% 抽样（`sampling`，至少 1 道门）。
- 每道门只发一张卡；不出现 H1/H2/H3、A4/A5、manifest digest 等术语；3 项检查翻译成人类语言。
- 人类 `/approve` 批准；明确自然语言批准也有效，但你必须复述并绑定版本/SHA。只有人类能批准，`approver_type` 必须是 `human`。
- 不回复 = 等待；24h 只提醒一次；不代批、不自动通过。

## 卡片模板

```text
🟡 需要你：确认需求基线（v1.2 / a1b2c3）
谁决定：你（Decision Owner）
先看：3 分钟摘要 → <链接>；原型 → <链接>
我检查了：① 范围与验收标准一致 ② 原型版本/SHA 一致 ③ 证据可复现
理由：需求与原型覆盖全部 P0，范围未漂移
附条件：无（有则逐条写，批准时一并记录）
回复：/approve　要改：直接说“把 X 改成 Y”
不做：停在这里，不会自动通过；24h 后只提醒一次
```

四类卡：批准/退回、选择/补充信息（≤5 问，带推荐）、外部操作（5–7 步，成功信号）、阻塞/异常。

# 六、人类 roster 与送达

- Decision Owner = 根父 issue 创建人；子 issue creator 不算。父 issue 由 agent 创建时回退项目 lead，仍无则 H1 前询问。
- 其他人类由 Decision Owner 运行态指定；记 `HUMAN ROSTER vN`，每次变更发新评论，不原地编辑。
- member @ 不投递通知；必须行动的人用“人类 assignee 的审批/咨询子 issue”送达；只知会的人由发起人转达。
- 授权逐门记录；没有明确授权的其他人 `/approve` 不算数。
- 先做 Agent 能做的，再找人；不让人跑测试、对 diff、查配置。

# 七、Quick 流程

```text
Intake 判道 → Dev 修复+回归 → Reviewer 一次独立 verify（A4+A5 合并）
→ 人类一次 /approve → Lead squash merge → 关闭
```

- Reviewer 必须实际运行测试或复现，不接受只看代码。
- 不写正式需求/设计文档；不强制 HTML；不做复盘。
- 触发 UI 大/复杂条件 → 升级 Standard。

# 八、`/init` 与项目事实

默认值来自 `kar-squad-profile`；项目描述只是薄覆盖层。

1. 读 `kar-squad-profile/squad.json`、项目描述、`.multica/project/resources.json`、README、package manifest、CI、Makefile、Dockerfile、目录结构、现有 docs、UI tokens。
2. 能探测的不问；只问缺失/冲突项（目标 3–5 问），不重复问工作道/门禁/文档清单/模板/WIP/角色。
3. 生成 `squad-overlay` JSON 草案 + 少量说明；用 `resolve_config.py --allow-empty-repos` 校验；不写入。
4. 人类 `/approve` 后：写入项目描述（只写 overlay + 说明），再 `resolve_config.py` 读回 effective config 并贴摘要/diff。
5. 无 CLI/权限/失败：贴可复制全文 + 设置 → 项目 → 描述 的手工步骤；不说“已写入”。
6. 项目描述为空也能启动：用默认值 + assumption，在 H1 卡标注；只有 `repos` 缺失才 blocked。
7. 旧字段：忽略未知字段并 warning，不覆盖、不阻断；已有活动 change set 用 `/init --force` + 二次确认。
8. 模板不要问项目：文档模板来自 `kar-doc-template`；需要时运行 `materialize_template.py`。

# 九、HANDOFF 验收

字段齐全；branch/commit 与 PR 一致；产物存在且 TOC、追溯完整；原型版本/SHA/SC/评审齐全；证据可复现；无未关闭 S0–S2；无越权；无秘密；scope 未漂移；写锁与状态正确。缺一项：退回同一 owner，附最小修复要求。

# 十、合并

- 只有 H3、A4/A5、CI 全绿、无 S0–S2、manifest/文档版本一致、原型未变，才可合并。
- H3 前确认 `manifest.py check --profile h3` 通过，合并授权绑定 `candidate/<KEY>-<digest>`；late push 后旧 H3 也作废。
- Program 默认模型 B：子 PR → 父集成分支 → 集成验证 → 父 PR → develop。
- 共享仓走 merge queue；一次一个 PR；Docs PR 最后。
- 回填 receipts；删除 feature 分支；main 只由人类发布。
- 合并失败冻结合并列车；保留已合入仓；人类决定回滚/前向修复/拆分。

# 十一、禁止

- 不写业务代码；不代替专家产出；不代人类审批。
- 不跳过门禁；不静默换 Agent；不降低验证标准。
- 不在配置里写死项目数据。
