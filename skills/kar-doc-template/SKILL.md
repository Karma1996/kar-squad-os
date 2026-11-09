# 目的
这是 KAR Delivery Squad 的**唯一文档模板来源**。文档风格、槽位、CSS、版本和哈希由小队拥有，与项目无关；项目只决定文档写到哪里（Docs Home）。

# 触发
任何正式 HTML 文档的写作、评审或合并前检查。

# 一、模板文件

本 Skill 携带：

```text
templates/KAR-Deliverable-Template.html
templates/template.json          # version / squad_version / sha256 / slots
scripts/materialize_template.py
```

- `template.json.version` 当前为 **4.1**；`squad_version` 为 **4.1.0**。
- 文档的 `data-template-version` 必须等于 `template.json.version`；不一致视为旧壳，不得合并。
- 模板是自包含 HTML；样式、CSS token、TOC、打印、无障碍都在壳里，不在项目配置里。

# 二、使用规则

1. **不要向项目要模板路径。** 模板来自本 Skill，不来自 `{DOCS_HOME}/multica/templates/` 的项目配置。
2. 写文档时：取本 Skill 的模板 → 只填槽位（`DOC_*`、`SUMMARY`、`BODY`、`EVIDENCE`、`PROVENANCE`、`APPROVAL`、`CHANGELOG`）→ 写入目标目录。
3. 不重新设计页面、不引入第二套 CSS、不加载 CDN/外部字体；断网与 `file://` 可读。
4. 模板升级 = 小队发版；不要在每个项目里手工改壳。
5. 项目级覆盖是例外：只有 `overrides.template = "project"` + `overrides.template_path`，并且人类明确批准，才使用项目模板；默认永远用 squad 模板。

# 三、materialize（缓存到项目 docs 树）

`{DOCS_HOME}/multica/templates/` 里的副本是**产物缓存**，不是配置源。缺失或版本旧时：

```bash
python3 scripts/materialize_template.py \
  --docs-home "{DOCS_HOME}" \
  --workspace-id "{WORKSPACE_ID}"
```

- 脚本通过 `skill list` 找到本 Skill，用 `skill files list <id> --with-content` 取 HTML 与 `template.json`；跨 runtime 不依赖固定挂载路径。
- 写入后校验 `template.json.sha256` 与 HTML 一致；打印版本/hash。
- 如果脚本不可用：用 `multica skill files list` 手工取文件，写入同样的路径；不要问项目要模板。

# 四、与 UI 原型的关系

- 本 Skill 只管**文档壳/风格**。
- UI 原型的视觉风格仍从项目代码提取（tokens、组件、现有页面），由 `kar-requirements-prototype` 负责；不要把项目设计系统塞进小队模板。
- 文档模板和 UI 视觉语言是两条线，避免互相污染。

# 五、检查清单

- [ ] 文档 `data-template-version` = 4.1。
- [ ] 使用本 Skill 的模板，不是项目旧副本。
- [ ] 槽位齐全，TOC/证据/审批/变更记录存在。
- [ ] 无 CDN、无外部字体、无 secrets。
- [ ] manifest/doc control 记录模板版本与 hash。
- [ ] 项目 override 有人类批准记录（如适用）。

# 六、完成定义

文档可离线打开；模板版本/hash 一致；槽位完整；风格与小队模板一致；项目无需配置模板路径。
