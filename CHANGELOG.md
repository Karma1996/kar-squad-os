# Changelog

## 4.1.0

- 新增 `kar-squad-profile`：小队默认值、解析顺序、薄项目模板、`resolve_config.py`。
- 新增 `kar-doc-template`：唯一文档模板、`template.json`（4.1 + sha256）、`materialize_template.py`。
- 文档模板从项目配置改为小队资产；项目只提供 Docs Home。
- 项目描述改为 `squad-overlay` 薄覆盖层；共性配置移入小队默认值。
- `bootstrap.py` 支持 `skill files upsert`；`verify.py` 校验 Skill 文件、模板 hash、Squad 指令。
- 配置手册升为 v4.1；新增人类快速上手、路线图、ADR。

## 4.0.0

- 三条工作道 Quick/Standard/Program。
- 运行时人类 roster；Decision Owner = 根父 issue 创建人。
- 父 key 变更集与 Program 子分支。
- 灵活拆分 P0/P1/P2；像素级原型模式 B。
- 按需复盘；迁移包与 `verify.py`。

## 3.0.0

- 8 席 / 17 Skill / 1 Squad；H1–H3；问题优先；并行 A4/A5。
- 旧基线，保留作历史参考。
