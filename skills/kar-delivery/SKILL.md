# 目的
在已批准的需求、设计、测试契约和原型内实现，产出可独立复核的证据。

# 触发
A3 就绪；工作道 Standard/Program 的开发阶段；Quick 的修复阶段。

# 一、开工前

确认：branch/head、write_lock、PR、设计覆盖矩阵、A3 用例与命令、已批准原型版本/SHA、项目测试命令、CI。

缺任何一项：不写代码，发 BLOCKED 或交回 Lead。

# 二、变更集与分支

- `change_set_id = 根父 issue key`；子 issue key 不进分支前缀。
- Quick：`fix/{KEY}-{SLUG}`；Standard：`feat/{KEY}-{SLUG}`；Program 父级：`feat/{PARENT_KEY}-{SLUG}`；Program 子级：`feat/{PARENT_KEY}-{SLUG}/{FEATURE_SLUG}`。
- 同一 workstream 跨仓同名；不建 per-agent/per-stage 分支；不直推 develop/main；不 force push。
- 使用 detached HEAD 在 canonical 分支最新 SHA 上工作；提交后 push。
- commit trailer：`Change-Set: {PARENT_KEY}`、`Workstream: {slug}`、`Sub-Issue: {CHILD_KEY}`。
- 提交信息：`{ISSUE_KEY}: {type}({scope}): {summary}`；一个提交做一件事。

# 三、TDD 与测试

1. 先让对应测试红（若已存在且红，记录基线）。
2. 实现到绿。
3. 重构，保持绿。
4. 对 FR/AC 逐项运行：unit/integration/E2E；覆盖异常、权限、边界、幂等、错误路径。
5. P0/P1 全量运行；P2/P3 至少受影响范围，并解释。
6. 新缺陷必须加回归测试；修复后跑目标测试 + 相关回归。
7. 不得删除/跳过测试、降低断言、绕过 CI、改验收期望。

# 四、测试矩阵

在开发交付说明中维护：

| TC | FR/AC | 命令 | 结果 | 证据 |
| --- | --- | --- | --- | --- |

另记录 lint/typecheck/unit/integration/build/acceptance 的命令、退出码、摘要、时间。

# 五、原型一致性

- 严格按 H1 批准的 `交互原型.html` 实现；颜色、字号、间距、圆角、阴影、图标、布局、状态、权限、响应式断点按模式 B。
- 可见偏差 → 停止，提交 `DECISION-REQUEST`：前后对比、影响、建议、是否改变 AC；由 Decision Owner 决定。
- 实现细节差异（DOM 结构、内部组件）只要可见结果一致，不需要批准。
- 不静默重设计；不以“实现更方便”改变已批准交互。

# 六、PR 与开发说明

- PR 标题含子 issue key（如 `KAR-12 KAR-9 payment: ...`）；父 key 在分支名和父级集成 PR。
- PR 描述：变更、测试、风险、回滚、原型链接、父 issue 链接、截图。
- 开发交付说明：范围对照、变更文件、测试矩阵、覆盖率与缺口、迁移/配置、部署/回滚、已知问题、Reviewer 指南、证据索引、变更记录。
- PR 与文档指向同一 head SHA；CI 通过。

# 七、候选与交接

- A4 候选：范围内 FR 已实现；P0/P1 通过；lint/typecheck/unit/integration/build/acceptance 全绿；CI 通过；无 secrets/无越权/无禁用测试；未解决问题显式记录。
- HANDOFF：stage=build、branch/head、pr、artifacts、tests、coverage、prototype、risks、open_questions、recommended_next。
- 建议下一步 Reviewer（A4）与 QA（A5）并行；不自行批准、不合并、不部署生产。

# 八、禁止

不评审自己的代码；不合并；不改需求/设计；不扩 scope；不提交生成物/大报告/密钥；不把“本地通过”当 CI 通过。
