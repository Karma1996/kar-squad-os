# 目的
这是 KAR Delivery Squad 的**小队级默认配置**。项目描述不再承载共性配置，只作为薄覆盖层。所有 Agent 在运行时按“默认优先”的顺序解析配置。

# 触发
每次运行；`/init`、intake、文档写作、分支/门禁判断前都要先解析配置。

# 一、解析顺序（从低到高）

1. **Squad 默认**：本 Skill 的 `squad.json`。
2. **仓库探测**：README、package manifest、CI 配置、Makefile、Dockerfile、目录结构、现有 docs、UI tokens。
3. **项目 overlay**：项目描述中的 `<!-- squad-overlay --> … <!-- /squad-overlay -->` JSON 块。
4. **Issue 运行时覆盖**：Decision Owner/roster、临时 priority、显式 waiver。

**项目描述不是第二套小队配置。** 它只写差异、未知项和项目特有事实；缺失字段用 Squad 默认值，未知字段 warning，不阻断。

# 二、Squad 默认包含什么

| 类别 | 内容 |
| --- | --- |
| 工作道 | Quick/Standard/Program；风险 R0–R3；文件 ≤3；模块 M0–M4；升级触发器 |
| 门禁 | H1 需求确认 / H2 方案确认 / H3 验收与合并；Quick 一道门 |
| 文档 | 五份固定 HTML + 条件原型 + 按需复盘；目录 `{DOCS_HOME}/multica/requirements/{ISSUE_KEY}-{SLUG}/` |
| 模板 | `kar-doc-template` 的 squad 模板；版本 4.1；哈希校验 |
| 分支 | Quick/Standard/Program 父/子的命名；commit trailer |
| WIP/并发 | Quick 3；Standard 2；Program 1（2–3 工作流）；人类待决策 ≤2 |
| 原型 | 大/复杂 UI 触发；模式 B；风格从项目代码提取；H1 绑定 |
| 复盘 | 按需；不阻塞合并 |
| 人类 | `/approve` + `/init`；Decision Owner = 根父 issue 创建人；24h SLA |

完整机器可读默认值见本 Skill 的 `squad.json`。

# 三、项目 overlay

项目描述里只保留一个 JSON 块：

````markdown
<!-- squad-overlay -->
```json
{
  "version": 1,
  "repos": [{"id": "api", "url": "…", "branch": "develop", "test": "…"}],
  "docs_home": "…",
  "ci": {"name": "…", "required": ["…"]},
  "staging": "…",
  "human_defaults": {"backup": "…"},
  "constraints": ["…"],
  "overrides": {"merge_model": "integration"}
}
```
<!-- /squad-overlay -->
````

允许的顶层字段：`version / repos / docs_home / ci / staging / human_defaults / constraints / overrides / goal / success_metrics / notes`。

允许的 `overrides`：`merge_model / template / module_map / ui_profile / lane_defaults / wip / slas`。

**不可覆盖的 Squad 不变式**：独立验证、人类门禁、main 只由人类、issue 内单写者、证据优先、无秘密、失败显式。项目 override 只能调参数，不能取消底线。

# 四、必填与降级

- 必填：`repos`（至少一个仓库事实）。缺失时 `resolve_config.py` 报错；`/init` 必须先补齐。
- 推荐：`docs_home`、`ci`、`staging`、`human_defaults`、`constraints`。
- 缺失时的降级：单仓 → N=1；无 Docs Home → 仓库内 `docs/` 或根 `multica/`；无 CI → 本地命令 + 证据；无 staging → 本地/容器验证；无 UI 设计系统 → 从代码提取。
- 降级必须写进证据栏，不能静默。

# 五、`/init` 流程

1. 读项目描述、`.multica/project/resources.json`、README、package manifest、CI 配置、目录结构、现有 docs、UI tokens。
2. 能探测的不问；只问缺失/冲突项（目标 3–5 问）。
3. 生成 `squad-overlay` JSON 草案 + 少量说明；不写入。
4. 人类 `/approve` 后，写入项目描述；用 `resolve_config.py` 读回校验，贴 effective config。
5. 项目描述为空也能启动：用默认值 + assumption，在 H1 卡标注；只有 `repos` 缺失才 blocked。
6. 已有项目描述含旧字段：忽略未知字段并 warning，不覆盖、不阻断。

# 六、解析脚本

```bash
python3 scripts/resolve_config.py \
  --resources-json .multica/project/resources.json \
  --output effective_config.json
```

- 合并 Squad 默认 + 项目 overlay；输出 warnings/errors。
- `--description-file` 可直接读一份草案。
- `--allow-empty-repos` 仅用于 `/init` 草案阶段。
- 退出码 0 = 可用；1 = 有必填项缺失/JSON 解析失败。

# 七、完成定义

- 项目 issue 上贴出 effective config 摘要：lane、docs home、repos、合并模型、overrides。
- 所有缺失项都有 assumption 或 blocked 理由。
- 没有把 Squad 默认值复制进项目描述；项目描述只保留差异和外部事实。
