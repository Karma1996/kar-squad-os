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
        ├── 威胁模型.html            # R3 必填
        ├── 权限矩阵.html            # R3 必填
        ├── 安全扫描报告.html        # R3 必填；密钥 + 依赖
        ├── 回滚演练记录.html        # R3 必填
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

# 二·五、暂存：只有冻结版才进仓库

| 级别 | 放哪 | 用途 | 进仓 |
| --- | --- | --- | --- |
| L0 草稿 | issue 评论，唯一 canonical 链接 | 讨论、改 | 否 |
| L1 待评审 | issue 附件（1 页摘要 + 1 份 HTML） | 人类评审 | 否 |
| L2 冻结 | `{DOCS_HOME}/<KEY>-<SLUG>/` + manifest | 基线、可引用 | 是，需 `/approve` |

- 每个阶段只保留 1 个 canonical 文件；旧版只在“已废弃”一行列出，不逐版上传。
- 未冻结文档不得提交到代码仓，包括 `/init` 阶段和“先存个档”的理由。
- 只有 L2 版本可以作为 H2/H3 的输入；引用 L0/L1 视为无基线。

# 二·六、人类可读文档标准

- 固定结构：**3 分钟摘要 → 这次请你确认什么（≤3 条）→ 正文 → 证据附录（机读）**。
- 正文不出现 H1/H2/A4/A5、完整 SHA、矩阵计数、文件大小；版本绑定可用短 digest，完整证据放附录或 manifest。
- 每份文档只服务一个决定；写不出“它促成哪个决定”就删。
- 页数上限：意图简版 1 页、需求基线 6 页、方案设计 8 页、技术栈 4 页、决策记录 1 页；原型 8–12 屏。
- 人类是审核方：先给结论和需要决定的事，再给依据；不复述过程。

# 三、五份固定正式文档 + 条件原型 + 按需复盘

1. 需求分析文档.html（Analyst）
2. 交互原型.html（条件；Analyst）
3. 方案设计文档.html（Architect）
4. 测试设计与用例.html（TestDesigner）
5. 开发交付说明.html（Developer）
6. 测试验收文档.html（QA）
7. 复盘分析文档.html（按需；Retro；不做时不创建）
8. delivery-manifest.json（Lead 维护）

产物数量按风险分级封顶，不靠多写文档换安全感：R0/R1 ≤3、R2 三份（需求/设计/测试设计）、R3 全量 + 安全 overlay、Program 子级 1–2。写入 manifest `artifacts`，详见 `docs/ARTIFACTS.md`。

# 四、模板（小队所有）

- 模板来自 `kar-doc-template` Skill；**不要向项目要模板路径**。
- 取 Skill 的 `templates/KAR-Deliverable-Template.html`，只填槽位；不重新设计页面。
- 文档 `data-template-version` 必须等于 4.1；不一致视为旧壳，不得合并。
- `{DOCS_HOME}/multica/templates/` 只是 materialize 缓存；缺失/旧时运行 `materialize_template.py`，不要人工维护第二套壳。
- 项目 override 只允许 `overrides.template=project` + `overrides.template_path` + 人类批准；默认永远 squad 模板。
- 固定槽位：doc-head、summary、doc-toc、body、evidence、provenance、approval、footer。
- 模板升级 = 小队发版；不允许每项目手工改壳。

# 五、候选冻结与 Manifest

`delivery-manifest.json` 升为 `version: 2`；候选身份是 `candidate/<KEY>-<digest>`。v4.4 起 H3 还校验低风险假设（`autonomy`）与 UI 变更的视觉回归（`ui_affected` / `visual_regression`）。

```bash
# 计算/写回 digest 与 tag
python3 scripts/manifest.py digest --manifest <path>/delivery-manifest.json --write
# 冻结：校验 docs SHA、原型 SHA、各仓 head、PR、CI
python3 scripts/manifest.py freeze --manifest <path> --docs-root <docs-home> --repo-root <id>=<path> --write
# A4/A5 校验
python3 scripts/manifest.py check --profile freeze --manifest <path> --docs-root <docs-home> --repo-root <id>=<path>
# H3 校验（含门禁、R3 第二人、10% 抽样、指标、v4.3 治理块）
python3 scripts/manifest.py check --profile h3 --manifest <path> --docs-root <docs-home> --repo-root <id>=<path> --check-remotes --check-prs --check-ci
# 只跑治理策略（产物矩阵/安全 overlay/草稿/steer/接触点/低风险假设/视觉回归）
python3 scripts/policy.py check --manifest <path> --profile h3
# 低风险 24h 假设与视觉回归单独审阅
python3 scripts/autonomy.py check --manifest <path> --profile h3
python3 scripts/visual.py check --config <visual.json> --results <results.json>
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
  "lane": "standard",
  "artifacts": [{"kind": "requirements", "ref": "...", "version": "1.2"}],
  "security_overlay": {"threat_model": {}, "permission_matrix": {}, "secret_scan": {}, "dependency_scan": {}, "rollback_drill": {}, "reviewer": {}},
  "checkpoints": {"h1_draft": {"intent_confirmed_at": "...", "published_at": "...", "review_window_minutes": 10, "reviewers": ["..."], "outcome": "unchanged", "steer_ids": []}},
  "steers": [],
  "touchpoints": [{"kind": "intake", "at": "...", "actor": "..."}],
  "merge_receipts": []
}
```

规则：

- 一个父级 manifest；子级是条目。Program 父级 digest 覆盖全部仓 head。
- 每道门固定 3 项检查 + `rationale` + `conditions`；只有人类能批准，`approver_type` 必须是 `human`。清单见 `docs/GATES.md`。
- R3 记录 `gates.h3.second_reviewer`；H3 记录 10% 抽样 `gates.h3.sampling`（至少 1 道门）。
- 每个 issue 在 `metrics` 记录 5 项：`human_touches / wait_human / rework_rounds / candidate_recuts / escaped_defects`；周摘要用 `scripts/metrics.py`。定义见 `docs/METRICS.md`。
- `artifacts` 按风险分级记录正式产物（见 `docs/ARTIFACTS.md`）；R2 三份、R3 全量 + 安全 overlay，超出或不足都会被 H3 拒绝。
- R3 写 `security_overlay`：威胁模型/权限矩阵/扫描/回滚演练/独立评审人；评审人必须同时是 `gates.h3.second_reviewer`。见 `docs/SECURITY-OVERLAY.md`。
- H1 先发 1 页意图简版，人类确认后才写需求基线；H1/H2 发卡前再发草稿 ≥10 分钟，写 `checkpoints`；纠偏写 `steers` 决策台账。见 `docs/CHECKPOINT-STEER.md`。
- `touchpoints` 只允许 intake/契约/门禁/集成/合并/异常六类，超出预算 H3 FAIL。见 `docs/LEAD-TOUCHPOINTS.md`。
- 文档 SHA、原型 SHA 或任一仓 head 变化 → digest 变化，A4/A5/H3 旧结论失效；late push 必须重切，不能改旧结论。
- 完整示例：`docs/examples/delivery-manifest.json`；字段与命令：`docs/MANIFEST.md`。

# 五·五、产物校验（P1）

- 产物方在 HANDOFF 前跑：
  ```bash
  python3 scripts/verify_artifact.py --manifest <docs>/delivery-manifest.json --require-sha --json
  python3 scripts/doc_lint.py --dir <docs-issue-dir> --json
  ```
- `verify_artifact.py` 校验 path / 存在性 / 大小 / SHA-256；`--require-sha` 时缺 SHA 直接失败。
- `doc_lint.py` 校验模板版本、摘要、证据/批准区、占位符、外链、锚点；ERROR 不得发门禁。
- Reviewers 复核两份输出；Lead 只看 PASS/FAIL，不自己重算 SHA。

# 六、证据

- 截图放 `evidence/screenshots/`，按 `SC-xxx-{breakpoint}-{theme}.png`。
- 日志/报告放 `evidence/{logs,reports}/`；索引写 `evidence-index.json`。
- 文档中的结论必须指回证据路径/命令/退出码。
- 不嵌入敏感数据；截图前脱敏。

# 七、禁止

不把正式文档放仓库根；不建 `KAR-xxx/` 根目录；不把文档散落到代码仓绕过 Docs Home；不把未冻结文档提交到代码仓；不逐版上传附件；不写真实数据/密钥；不用聊天摘要代替 HTML。
