# 目的
统一文档目录、模板、命名、manifest 与证据，保证可审计、可迁移、可回滚。

# 触发
任何会写文档、截图、manifest 的运行。

# 一、目录

```text
{DOCS_HOME}/multica/
├── project/
│   ├── repo-registry.html
│   ├── repo-registry.json
│   └── ui-profile.json
├── templates/                # 由 kar-doc-template materialize 的缓存
│   ├── KAR-Deliverable-Template.html
│   └── template.json
└── requirements/
    └── {ISSUE_KEY}-{SLUG}/
        ├── 需求分析文档.html
        ├── 交互原型.html
        ├── 方案设计文档.html
        ├── 测试设计与用例.html
        ├── 开发交付说明.html
        ├── 测试验收文档.html
        ├── 复盘分析文档.html
        ├── delivery-manifest.json
        ├── assets/{diagrams,screenshots,samples,prototype}/
        ├── evidence/{logs,reports,screenshots}/
        └── workstreams/{FEATURE_SLUG}/...
```

# 二、规则

- `DOCS_HOME`：单仓 = 仓库根；多仓 = 专用文档仓根。
- 目录名 = issue key + slug；issue key 平台原样，不补零；slug 2–5 个英文单词，小写连字符；首次提交后不改名。
- 文档平铺；不加 `-v2/-final`，不按阶段套文件夹；版本写文档控制区与 Git。
- 一个需求目录只服务一个根 issue；Program 子级放 `workstreams/`。
- 目录在需求分支上创建，随分支评审合并；不先放 main。
- 复盘按需；不做时不创建文件，在 issue 记录理由。

# 三、五份固定正式文档 + 条件原型 + 按需复盘

1. 需求分析文档.html（Analyst）
2. 交互原型.html（条件；Analyst）
3. 方案设计文档.html（Architect）
4. 测试设计与用例.html（TestDesigner）
5. 开发交付说明.html（Developer）
6. 测试验收文档.html（QA）
7. 复盘分析文档.html（按需；Retro；不做时不创建）
8. delivery-manifest.json（Lead 维护）

# 四、模板（小队所有）

- 模板来自 `kar-doc-template` Skill；**不要向项目要模板路径**。
- 取 Skill 的 `templates/KAR-Deliverable-Template.html`，只填槽位；不重新设计页面。
- 文档 `data-template-version` 必须等于 4.1；不一致视为旧壳，不得合并。
- `{DOCS_HOME}/multica/templates/` 只是 materialize 缓存；缺失/旧时运行 `materialize_template.py`，不要人工维护第二套壳。
- 项目 override 只允许 `overrides.template=project` + `overrides.template_path` + 人类批准；默认永远 squad 模板。
- 固定槽位：doc-head、summary、doc-toc、body、evidence、provenance、approval、footer。
- 模板升级 = 小队发版；不允许每项目手工改壳。

# 五、候选冻结与 Manifest

`delivery-manifest.json` 升为 `version: 2`；候选身份是 `candidate/<KEY>-<digest>`。

```bash
# 计算/写回 digest 与 tag
python3 scripts/manifest.py digest --manifest <path>/delivery-manifest.json --write
# 冻结：校验 docs SHA、原型 SHA、各仓 head、PR、CI
python3 scripts/manifest.py freeze --manifest <path> --docs-root <docs-home> --repo-root <id>=<path> --write
# A4/A5 校验
python3 scripts/manifest.py check --profile freeze --manifest <path> --docs-root <docs-home> --repo-root <id>=<path>
# H3 校验（含门禁、R3 第二人、10% 抽样、指标）
python3 scripts/manifest.py check --profile h3 --manifest <path> --docs-root <docs-home> --repo-root <id>=<path> --check-remotes --check-prs --check-ci
```

digest 只由候选输入决定：`change_set_id/issue/slug` + `requirements/prototype/design/test_design/dev_notes` 的 version+sha + 各仓 `repo_id/base/branch/head`；SHA-256 取前 12 位。`qa_report` 变化不重切候选。

最小结构：

```json
{
  "version": 2,
  "change_set_id": "KAR-9",
  "issue": "KAR-9",
  "slug": "checkout-idempotency",
  "risk": "R2",
  "decision_owner": "<user-id>",
  "docs": {
    "requirements": {"path": "...", "version": "1.2", "sha": "<64 hex>"},
    "prototype": {"path": "...", "version": "1.0", "sha": "<64 hex>", "mode": "B", "approved_by": "...", "approved_at": "..."},
    "design": {}, "test_design": {}, "dev_notes": {}, "qa_report": {}
  },
  "repos": [{"repo_id": "...", "remote": "...", "base": "develop", "branch": "...", "head": "<40 hex>", "pr": "...", "merge_order": 1,
             "ci": {"status": "passed", "head": "<same 40 hex>", "url": "...", "checked_at": "..."}}],
  "candidate": {"digest": "<12 hex>", "tag": "candidate/KAR-9-<digest>", "frozen_at": "..."},
  "gates": {
    "h1": {"status": "approved", "approved_by": "...", "approver_type": "human", "approved_at": "...",
           "rationale": "一句话理由", "conditions": [],
           "checks": [{"id": "scope", "result": "pass", "evidence": "..."},
                      {"id": "prototype", "result": "pass", "evidence": "..."},
                      {"id": "evidence", "result": "pass", "evidence": "..."}]},
    "h2": {"checks": [{"id": "design"}, {"id": "contract"}, {"id": "testability"}]},
    "h3": {"candidate_digest": "<digest>",
           "checks": [{"id": "candidate"}, {"id": "verdicts"}, {"id": "ci"}],
           "second_reviewer": {"reviewer": "...", "role": "security", "verdict": "pass", "at": "..."},
           "sampling": {"rate": 0.1, "population": 3, "sampled": ["h1"], "reviewed_by": "...", "at": "...", "note": "无发现"}}
  },
  "metrics": {"human_touches": 3, "wait_human": 6.5, "rework_rounds": 1, "candidate_recuts": 0, "escaped_defects": 0},
  "merge_receipts": []
}
```

规则：

- 一个父级 manifest；子级是条目。Program 父级 digest 覆盖全部仓 head。
- 每道门固定 3 项检查 + `rationale` + `conditions`；只有人类能批准，`approver_type` 必须是 `human`。清单见 `docs/GATES.md`。
- R3 记录 `gates.h3.second_reviewer`；H3 记录 10% 抽样 `gates.h3.sampling`（至少 1 道门）。
- 每个 issue 在 `metrics` 记录 5 项：`human_touches / wait_human / rework_rounds / candidate_recuts / escaped_defects`；周摘要用 `scripts/metrics.py`。定义见 `docs/METRICS.md`。
- 文档 SHA、原型 SHA 或任一仓 head 变化 → digest 变化，A4/A5/H3 旧结论失效；late push 必须重切，不能改旧结论。
- 完整示例：`docs/examples/delivery-manifest.json`；字段与命令：`docs/MANIFEST.md`。

# 六、证据

- 截图放 `evidence/screenshots/`，按 `SC-xxx-{breakpoint}-{theme}.png`。
- 日志/报告放 `evidence/{logs,reports}/`；索引写 `evidence-index.json`。
- 文档中的结论必须指回证据路径/命令/退出码。
- 不嵌入敏感数据；截图前脱敏。

# 七、禁止

不把正式文档放仓库根；不建 `KAR-xxx/` 根目录；不把文档散落到代码仓绕过 Docs Home；不写真实数据/密钥；不用聊天摘要代替 HTML。
