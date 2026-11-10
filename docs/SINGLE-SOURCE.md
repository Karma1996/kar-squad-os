# 单一源生成

v4.4 之前，`skills.json`、`agents.json`、`squad/KAR-Delivery-Squad.json`、`bootstrap.json` 与 `kar-squad-profile/squad.json` 是五份手写 JSON：改一个 Agent 的并发或 Skill 绑定，要同步改几处，漏一处就是漂移。现在只有 **`sources/squad.json`** 一份源，其余由 `scripts/generate.py` 渲染。

## 1. 源文件结构

```json
{
  "kit": {
    "name": "KAR Delivery Squad",
    "version": "4.4.0",
    "bootstrap_profile": "KAR-Squad-Bootstrap-v4.4",
    "config": "config/KAR-Squad-Config-v4.4.md",
    "requires": {"python": "3.9+", "multica_cli": ">=0.8.1"},
    "squad_file": "squad/KAR-Delivery-Squad.json",
    "squad_instructions": "squad/KAR-Delivery-Squad.md",
    "init_template": "skills/kar-squad-profile/templates/project-description.md",
    "squad_description": "…",
    "notes": ["…"]
  },
  "skills": [
    {"name": "kar-constitution", "description": "…", "path": "skills/kar-constitution/SKILL.md"}
  ],
  "agents": [
    {"name": "KAR-01-Lead", "description": "…", "runtime_env": "KAR_CORE_RUNTIME_ID", "max": 6,
     "skills": ["kar-constitution", "kar-lead-operating"]}
  ],
  "squad": {"name": "KAR Delivery Squad", "leader": "KAR-01-Lead", "members": []},
  "defaults": {"lanes": {}, "gates": {}, "autonomy": {}, "queue": {}, "visual": {}}
}
```

## 2. 生成哪些文件

| 文件 | 来源 | 用途 |
| --- | --- | --- |
| `skills.json` | `skills` | `bootstrap.py` / `verify.py` 的 Skill 目录与支持文件 |
| `agents.json` | `agents` | Agent 创建/更新、Skill 绑定与并发 |
| `squad/KAR-Delivery-Squad.json` | `squad` | Squad 名册与 leader |
| `bootstrap.json` | `kit` | 迁移包元数据、版本、配置手册路径 |
| `skills/kar-squad-profile/squad.json` | `defaults` + `kit.version` | 小队默认值（工作道、门禁、autonomy/queue/visual 等） |

散文不生成：`SKILL.md`、`agents/*.md`、`squad/KAR-Delivery-Squad.md`、`docs/`、配置手册仍由人类/Agent 编写。生成器只负责**目录、绑定、名册、默认值、版本元数据**这类结构化事实。

## 3. 命令

```bash
python3 scripts/generate.py --check   # 与源一致？不一致打印 drift 并退出 1
python3 scripts/generate.py --write   # 重写 5 个生成文件
make generate                         # 等价于 --write
make check                            # 先跑 --check，再跑其余校验
```

`--json` 输出 `{"ok": true/false, "errors": [], "warnings": []}`，方便 CI 机读。`--root` 供测试指向临时目录。

## 4. 修改流程

1. 改 `sources/squad.json`（加 Agent、改并发、改 Skill 绑定、改默认值）。
2. 跑 `python3 scripts/generate.py --write`。
3. 跑 `python3 scripts/generate.py --check` 与 `make check`。
4. 只提交源文件 + 生成结果，不手改生成文件；手改会在 CI 里被 drift 拦下。

新增 Skill 时同时创建 `skills/<name>/SKILL.md`；有支持文件时在源里写 `files`（`path` + `source`）。生成器会校验路径非空，但**不校验文件是否存在**——`make check` 的 `build_release.py --check` 负责存在性。

## 5. 校验与失败语义

`generate.py --check` 逐文件比较**完整渲染文本**，任何空白、顺序、字段差异都算 drift。失败输出：

```text
GENERATE: FAIL
  ERROR: drift: agents.json does not match sources/squad.json (run python3 scripts/generate.py --write)
```

源本身不合法时（重复 Skill、Agent 绑定未知 Skill、`max` 越界、版本不是 `MAJOR.MINOR.PATCH`、leader 不在 Agent 名册）直接 FAIL，不产出半套文件。

## 6. 为什么用 JSON 而不是 YAML

迁移包与 CI 只允许 Python 标准库；YAML 需要第三方解析器（PyYAML），会把“零依赖”这个约束打破。JSON 同样能表达目录/绑定/默认值，且 `json.dumps(sort_keys)` 可稳定比较，漂移检测更可靠。项目侧仍可用 YAML 写自己的配置，小队仓库不解析它。

## 7. 边界与不做的事

- 不生成 `SKILL.md`/Agent 指令正文：散文需要人写，生成器不猜。
- 不生成 `docs/` 与配置手册：版本号从 `VERSION` 同步，但不重写历史说明。
- 不替代 `build_release.py --check`：后者校验文件存在、模板 hash、版本一致性、示例 manifest。
- 不自动提交/发布：生成器只写工作区文件。

## 8. 常见错误

| 现象 | 原因 | 修复 |
| --- | --- | --- |
| `drift: bootstrap.json ...` | 改了 VERSION/kit 但没重生成 | `python3 scripts/generate.py --write` |
| `unknown skill: kar-x` | Agent 绑定了源里没有的 Skill | 在 `skills` 里补条目或删绑定 |
| `duplicate ... name` | 源里重名 | 改名/删重复 |
| `squad.leader: must be an agent name` | leader 写错/漏 Agent | 修 `squad.leader` |
| `kit.version: expected MAJOR.MINOR.PATCH` | 版本格式错 | 改成 `4.4.0` 这类三段式 |
