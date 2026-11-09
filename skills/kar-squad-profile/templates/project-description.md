# {PROJECT_NAME}

<!--
这是项目覆盖层模板，不是小队配置。
只写项目特有、无法从仓库推断的事实；工作道、门禁、文档清单、模板、WIP、角色等由 kar-squad-profile 提供。
-->

## 说明（可选）

{一两句话说明项目目标/边界}

<!-- squad-overlay -->
```json
{
  "version": 1,
  "repos": [
    {
      "id": "{REPO_ID}",
      "url": "{REPO_URL}",
      "role": "{ROLE}",
      "branch": "{DEFAULT_BRANCH}",
      "install": "{INSTALL_CMD}",
      "build": "{BUILD_CMD}",
      "test": "{TEST_CMD}",
      "lint": "{LINT_CMD}"
    }
  ],
  "docs_home": "{DOCS_HOME}",
  "ci": {"name": "{CI_NAME}", "required": ["{REQUIRED_CHECK}"]},
  "staging": "{STAGING_OR_EMPTY}",
  "human_defaults": {"backup": "{BACKUP_OR_EMPTY}"},
  "constraints": ["{CONSTRAINT}"],
  "overrides": {"merge_model": "integration"}
}
```
<!-- /squad-overlay -->

## 备注

- 不写模板路径、文档清单、门禁、WIP、角色；这些由小队配置提供。
- 旧字段会被忽略并 warning；缺失字段用默认值。
