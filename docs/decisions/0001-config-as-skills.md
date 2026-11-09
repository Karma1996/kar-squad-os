# ADR 0001：用 Skill 承载小队配置

- 状态：Accepted
- 日期：2026-11-09
- 决策人：Human Decision Owner + Agent Maintainer

## 背景

Multica 的 Squad 对象只有 `name / description / instructions / leader / members / avatar`，没有文件存储，也没有任意 JSON 配置字段。文档模板与共性配置原先放在项目描述里，导致每个项目都要复制模板、对齐字段；换项目就漂移。

## 决定

1. **文档模板**放在 `kar-doc-template` Skill：HTML + `template.json`（version + sha256 + slots）+ materialize 脚本。
2. **共性配置**放在 `kar-squad-profile` Skill：`squad.json` 默认值 + 解析规则 + `resolve_config.py`。
3. **项目描述**只保留 `squad-overlay`：repos、命令、CI、staging、Docs Home、human fallback、constraints、显式 overrides。
4. 解析顺序：Squad 默认 → 仓库探测 → 项目 overlay → issue 运行时覆盖。

## 后果

- 换项目零模板配置；模板升级随小队版本走，`data-template-version` + sha256 校验。
- 项目描述变薄；旧字段忽略并 warning，不阻断。
- Skill 文件是支持文件，不整篇进 prompt；`materialize_template.py` 通过 CLI 取文件，跨 runtime 有兜底。
- Squad 不变式（独立验证、人类门禁、main 人类、单写者、证据、无秘密、失败显式）不可被项目 override 取消。
- 项目级模板 override 只允许显式 `overrides.template=project` + `template_path` + 人类批准。

## 备选方案

| 方案 | 为什么不选 |
| --- | --- |
| 放在 Squad instructions | 无文件存储；每项目/每次改都要重复，无法版本化模板 |
| 放在项目描述 | 就是当前问题：每个项目复制，漂移 |
| 外部配置服务 | 增加运行依赖；小队应只依赖 Agent + Skill + Git + 项目资源 |
| 把模板整篇塞进 SKILL.md | prompt 膨胀、维护困难；支持文件更合适 |

## 复审条件

- 平台为 Squad 增加文件/JSON 配置能力；
- Skill 文件在主流 runtime 不可用；
- 模板/默认值变更频率高到需要项目 pin 版本。
