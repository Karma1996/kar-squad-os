# 目的
让大项目用父 Program + 子 Workstream 并行交付，同时保持一个变更集、一个 manifest、一次 H3。

# 触发
工作道 = Program；或 Standard 拆出 >3 个工作流/跨团队。

# 一、结构

- 父 Program issue：assignee = Squad（Lead）；负责契约、拆分、集成、汇总验收、合并列车。
- 子 Workstream issue：一个可独立验证的用户行为切片，或一个独立仓库的改动；有自己的分支、PR、A4/A5、manifest 条目。
- 父级不重复子级证据，只做“契约 + 集成 + 汇总”。

# 二、拆分原则

1. 按用户可见行为做纵向切片，或按独立仓库/模块切；**不要按前后端/层切**。
2. 每个子 issue 必须能独立合并与验证；共享文件的并行 PR 会冲突，冲突就串行或换切法。
3. 子 issue 描述必须自包含：scope、AC、依赖、仓库、分支、验收信号、原型链接（如有）。
4. 先冻结跨工作流契约（接口/数据/错误码/版本），再并行。

# 三、拆分切点

| 切点 | 时机 | 拆什么 | 父级保留 | 门 |
| --- | --- | --- | --- | --- |
| P0 | H1 前，多领域独立调研 | 领域需求/问题子 issue（可选） | 统一需求基线 | H1 父级 |
| P1 | H2 前，设计可并行 | 每个工作流一份设计子 issue | 总体架构+契约+索引 | H2 父级评审整套 |
| P2 | H2/A3 后，一份设计定稿 | 每个工作流一个开发子 issue | 设计基线+A3+契约 SHA | 子级 A4/A5 + 父级集成 |

- 开发中途临时拆 = 重新规划、重新基线；默认不允许，确需则重新 `/approve`。
- 不需要并行时保持单 issue；不要 H1 就建整棵树。

# 四、SPLIT PLAN

```text
SPLIT PLAN v1 — {PARENT_KEY}
切点：P1 设计 / P2 开发
合并模型：B 集成分支
工作流：
| slug | 范围 | 仓库 | owner | 依赖 | wave | 验收信号 |
分支：
- 父：feat/{PARENT_KEY}-{SLUG}
- 子：feat/{PARENT_KEY}-{SLUG}/{slug}
人类调整：直接改表或评论；/approve 后启动 wave 1。
```

流程：

1. 父 issue 发 SPLIT PLAN；子 issue 全部以 `backlog` 创建（backlog 不启动 run）。
2. 人类直接改表/评论增删合并、改 owner/wave；也可直接编辑子 issue。
3. 人类 `/approve` 后，Lead 只把 wave 1 提到 `todo`；后续 wave 由 stage 屏障唤醒后再提升。
4. 未批准的拆分永远不启动。
5. 策略在 intake 批准一次；到切点时若与策略一致，直接建子 issue 并通知；改了 scope/owner/合并顺序才再次 `/approve`。

# 五、Stage

- `--stage <N>` 表达 wave；stage 是累计屏障：到该 stage 为止所有子 issue 都 terminal，父级才被唤醒。
- 可并行的放同一 stage，必须等待的放后一 stage。
- 子 issue 直接 assignee = 专家；**子 issue 的 assignee 可以关闭自己的子 issue**；父 issue 状态只由 Lead 改。
- 父级在 stage 屏障被唤醒后：读取 `issue children`，核对产物与门禁，提升下一 wave 或退回。

# 六、变更集与分支

- `change_set_id = 父 key`；子 key 不进分支前缀。
- 父：`feat/{PARENT_KEY}-{SLUG}`；子：`feat/{PARENT_KEY}-{SLUG}/{FEATURE_SLUG}`。
- 同一 workstream 跨仓同名；文档放 `{DOCS_HOME}/multica/requirements/{PARENT_KEY}-{SLUG}/workstreams/{slug}/`。
- 一个父级 `delivery-manifest.json`；子级是条目。
- 父级 candidate digest 覆盖全部仓 head 与父级文档；子级结论绑定各自 head。父级重切只改受影响条目，再重新 `freeze --write`。
- commit trailer：`Change-Set`、`Workstream`、`Sub-Issue`。

# 七、合入模型

- **B 集成分支（默认）**：子 PR → 父分支；父级在集成分支跑组合验证；父 PR → develop。适合跨仓契约、共享文件、整体回滚。
- **A 顺序直合 develop**：≤2 工作流、共享文件少；每个子 PR 各自过门禁后按序 squash。
- 模型必须写进 SPLIT PLAN 与 manifest；不能中途混用。

# 八、父级集成与 H3

- 子级 A4/A5 通过不等于父级完成；父级必须做集成验证：跨工作流契约、组合 staging、端到端关键路径、manifest 一致性。
- H3 看父级 candidate tag/digest + 各仓 SHA + 集成证据；不重复子级全部证据。
- H3 前跑 `scripts/manifest.py check --profile h3 --check-remotes --check-prs --check-ci`；任一仓 late push 则父级结论作废。
- 原型：跨工作流 UI 用父级 `交互原型.html`；各工作流独立页面放子目录；H1 一次批准整套，模式 B。
- 复盘按需；不作为合并前置。

# 九、合并列车

- 按 manifest 的 merge_order 逐仓合并；共享仓走 merge queue；一次一个 PR。
- Docs PR 最后合入。
- 合并失败：冻结合并列车；保留已合入仓；人类在回滚/前向修复/拆分之间决定；不自动继续。
- 回填 merge receipts；删除 feature 分支；main 只由人类发布。

# 十、代价与限制

- 子级独立 A4/A5，验证成本上升；2–3 个工作流起步，不超过 4 个。
- 子级 run 不继承父级讨论，只拿到 `[Parent issue]` 指针；描述不完整会返工。
- 子 issue 完成 ≠ 父级完成；父级必须有自己的集成验证与 H3。
- 过度拆分退回重规划；不要把一个大 PR 按层拆成多个不可独立验证的 issue。
