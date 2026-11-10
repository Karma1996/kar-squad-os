# 视觉回归工具化

v4.4 P2 的“视觉回归工具化”是一个**工具适配器**：项目声明自己的视觉工具、断点、主题、阈值和关键界面，`scripts/visual.py` 负责采集、覆盖检查与阈值判定。仓库不内置浏览器、渲染器或图像库。

## 1. 目标与边界

- 目标：把“每个界面 × 断点 × 主题都必须有可审计的差异结果”变成可执行检查，关键界面默认零差异。
- 边界：`visual.py` 只做适配与裁定，不负责渲染、截图、像素比较；这些由项目声明的 `command` 完成。
- 依赖：Python 3.9+ 标准库。CI 用 fake command 验证环境变量、聚合和失败语义，不依赖真实浏览器、网络或第三方包。
- 失败语义：缺失组合、重复组合、工具不可用、命令失败、结果不可解析都显式失败，不写 PASS；工具不可用标记为 BLOCKED。
- 人工验收仍不可替代：视觉工具通过不等于人类批准 H3；结构性差异、状态缺失、权限错误、断点错位必须阻塞。

## 2. 项目事实配置

项目事实文件建议放在 `multica/project/visual.json`，由项目维护，不写进小队默认值。完整示例见 [`docs/examples/visual-config.json`](examples/visual-config.json)：

```json
{
  "version": 1,
  "tool": "playwright",
  "command": ["node", "visual/compare.mjs"],
  "breakpoints": [
    {"name": "mobile", "width": 375},
    {"name": "desktop", "width": 1440}
  ],
  "themes": ["light", "dark"],
  "thresholds": {"max_diff_ratio": 0.005, "critical_max_diff_ratio": 0.0},
  "screens": [
    {"id": "SC-01-login", "url": "/login", "critical": true},
    {"id": "SC-02-home", "url": "/"}
  ],
  "critical_screens": ["SC-01-login"]
}
```

字段：

| 字段 | 必填 | 规则 |
| --- | --- | --- |
| `version` | 否 | 出现时必须为 `1`。 |
| `tool` | 是 | 非空字符串，例如 `playwright`；`check` 要求结果文件的 `tool` 与它一致。 |
| `command` | 否 | 字符串数组；`capture` 必填且非空。数组元素不能为空字符串；不通过 shell 执行。 |
| `breakpoints` | 是 | 非空数组；每项 `{name, width}`，`name` 唯一且非空，`width` 为正整数（像素）。 |
| `themes` | 是 | 非空字符串数组，元素唯一且非空，例如 `["light", "dark"]`。 |
| `thresholds.max_diff_ratio` | 是 | `[0, 1]` 内的数字；非关键界面的差异上限。 |
| `thresholds.critical_max_diff_ratio` | 否 | 默认 `0.0`；`[0, 1]` 内且必须 `<= max_diff_ratio`。 |
| `screens` | 是 | 非空数组；每项 `{id, url, critical?}`，`id` 唯一且非空，`url` 是采集用的路径或相对 URL。 |
| `screens[].critical` | 否 | 布尔；为 `true` 时该界面使用关键阈值。 |
| `critical_screens` | 否 | 字符串数组，必须是 `screens[].id` 的子集；列出的界面同样按关键界面处理。 |

关键界面的判定是两者的并集：

```text
critical = (screens[].critical == true) OR (id in critical_screens)
```

规范：

- `screens[].url` 在 `check` 中可省略（只看覆盖与结果），但 `capture` 必须有非空值，否则拒绝采集。
- 断点宽度只用于传给工具的 `KAR_VISUAL_WIDTH`，不用于推断项目支持范围。
- 阈值和界面清单是项目事实；改阈值、豁免关键界面必须由人类书面确认并留痕，不能靠改配置“顺手放过”。

## 3. 结果文件格式

结果文件由 `capture` 生成，也可以由项目自己的工具直接产出；示例见 [`docs/examples/visual-results.json`](examples/visual-results.json)：

```json
{
  "version": 1,
  "tool": "playwright",
  "generated_at": "2026-11-05T08:00:00Z",
  "tool_available": true,
  "screens": [
    {
      "screen": "SC-01-login",
      "breakpoint": "mobile",
      "theme": "light",
      "diff_ratio": 0.0,
      "baseline_sha": "0123456789abcdef",
      "current_sha": "0123456789abcdef",
      "artifact": "evidence/visual/SC-01-login-mobile-light.png"
    }
  ]
}
```

字段：

| 字段 | 规则 |
| --- | --- |
| `version` | 出现时必须为 `1`。 |
| `tool` | 必须等于配置的 `tool`。 |
| `generated_at` | RFC3339 时间戳，必须带时区（`Z` 或 `+08:00`），例如 `2026-11-05T08:00:00Z`。 |
| `tool_available` | 必须严格为 `true`；`false`、缺失、`1` 都不算通过，报“工具不可用，不能判定通过（BLOCKED）”。 |
| `screens` | 结果数组，每个 `screen × breakpoint × theme` 恰好一条。 |
| `screens[].screen` | 必须是配置声明过的界面 id。 |
| `screens[].breakpoint` | 必须是配置声明过的断点名。 |
| `screens[].theme` | 必须是配置声明过的主题。 |
| `screens[].diff_ratio` | `[0, 1]` 内的数字；缺失、布尔或越界均失败。 |
| `screens[].baseline_sha` | 非空字符串；建议至少 8 位十六进制，短于 8 位仅告警。 |
| `screens[].current_sha` | 非空字符串；建议至少 8 位十六进制。`capture` 不接受 `unknown` 占位。 |
| `screens[].artifact` | 可选；差异大于 0 时建议填写截图/差异图路径，为空会告警。 |

`capture` 失败时仍会写结果文件：成功的组合保留在 `screens`，`tool_available: false`，并附加 `errors`（必要时 `warnings`）便于审计。附加字段不属于判断依据，`check` 只使用上表字段。

## 4. 采集与比较

### 4.1 三条命令

```bash
# 生成项目模板；已存在时拒绝覆盖
python3 scripts/visual.py init --out multica/project/visual.json
python3 scripts/visual.py init --out multica/project/visual.json --force

# 校验配置、结果、覆盖和阈值
python3 scripts/visual.py check \
  --config multica/project/visual.json \
  --results evidence/visual/results.json

# 按配置逐屏、逐断点、逐主题调用项目工具
python3 scripts/visual.py capture \
  --config multica/project/visual.json \
  --out evidence/visual/results.json \
  --cwd . \
  --timeout 120
```

`--json` 可用于三条命令。`check --json` 固定输出：

```json
{
  "ok": true,
  "tool": "playwright",
  "coverage": {"expected": 8, "covered": 8, "missing": [], "duplicates": []},
  "failures": [],
  "warnings": [],
  "errors": []
}
```

`failures` 是阈值超限；`errors` 是结构/覆盖/工具问题。`warnings` 不改变退出码，但必须在 QA 报告中处理或说明。

### 4.2 capture 的调用契约

对每个组合调用一次 `command`，并注入以下环境变量（均为字符串）：

| 变量 | 值 |
| --- | --- |
| `KAR_VISUAL_SCREEN` | `screens[].id` |
| `KAR_VISUAL_BREAKPOINT` | `breakpoints[].name` |
| `KAR_VISUAL_THEME` | 主题名 |
| `KAR_VISUAL_URL` | `screens[].url` |
| `KAR_VISUAL_WIDTH` | `breakpoints[].width` 的字符串形式，例如 `"375"` |

每次调用必须在 stdout **只打印一个 JSON 对象**，至少包含：

```json
{"diff_ratio": 0.0, "baseline_sha": "<sha>", "current_sha": "<sha>", "artifact": "evidence/visual/SC-01-home-mobile-light.png"}
```

- `current_sha` 必须由工具提供；不要用 `"unknown"` 占位，`capture` 会拒绝。
- stdout 里不要混入日志、进度条或多个 JSON；这些属于“不可解析”，会写 `tool_available: false`。
- 非零退出、超时、无法启动命令、stdout 不可解析：记录错误，继续尝试其余组合，最后写部分结果并以 1 退出。
- `--timeout` 是单次调用的秒数，默认 120；`--cwd` 是命令工作目录。
- `capture` 的退出码同时反映采集完整性与阈值：0 表示结果完整且阈值通过；1 表示失败或阻塞。

### 4.3 可复现要求

- 使用固定 fixture，不依赖随机数据；必要时在请求层固定种子。
- 截图前冻结动画/过渡（`animation: none`、`transition: none` 或工具等价开关）。
- 固定浏览器版本、字体、视口、设备像素比和主题；字体不可用时按第 5 节走人类书面豁免。
- 截图命名统一为 `SC-xxx-{breakpoint}-{theme}.png`，例如 `SC-01-login-mobile-light.png`；与结果中的 `artifact` 对应。
- 只采集受影响界面时，仍需覆盖配置声明的全部组合，或在 manifest/QA 中明确本次范围并重新生成完整结果。

## 5. 阈值与关键界面

- 非关键界面：`diff_ratio > thresholds.max_diff_ratio` 失败；等于阈值通过。
- 关键界面：使用 `critical_max_diff_ratio`，默认 `0.0`，即任何正差异都失败；等于 `0.0` 通过。
- 关键界面来源：`screens[].critical == true` 或 `critical_screens` 包含该 id。
- 失败信息必须能定位到 `screen/breakpoint/theme`、阈值和实际值，例如：
  `SC-01-login/mobile/light: diff_ratio 0.003 exceeds critical threshold 0.0`。
- 豁免必须由人类书面给出：写清范围、原因、影响、证据和到期条件，记录在 QA 报告/manifest；不得通过改大阈值、删除界面、删结果来“通过”。
- 结构性差异（布局错位、缺失状态、权限错误、断点错位、第二套视觉语言）不适用阈值豁免，必须阻塞。

## 6. 覆盖要求与失败语义

期望覆盖 = `screens × breakpoints × themes`。`check` 强制：

- 每个组合在 `screens` 中恰好出现一次；缺失或重复都失败。
- 未知 `screen` / `breakpoint` / `theme` 失败。
- `tool` 不一致、`generated_at` 非法、`tool_available` 非严格 `true`、`diff_ratio` 非法、`baseline_sha` / `current_sha` 为空都失败。
- 差异超阈值记 `failures`；结构问题记 `errors`。任一存在即 `VISUAL: FAIL`，退出码 1。
- 工具不可用或采集失败是 BLOCKED，不写 PASS；`capture` 会保留成功组合，但 `tool_available: false` 使 `check` 必然失败。
- 空结果、缺文件、无法解析 JSON 都是失败，不得按“没有差异”处理。
- 只有 `ok: true`（无 `failures`、无 `errors`）才是 0 退出。`warnings` 需要处理，但不单独改变退出码。

## 7. 与 manifest/QA 的关系

- 结果摘要写入 manifest 的 `visual_regression` 块；`scripts/policy.py check --profile h3` 校验以下字段：

```json
"ui_affected": true,
"visual_regression": {
  "config": {
    "path": "multica/project/visual.json",
    "version": "1.0",
    "sha": "<64 位小写十六进制>"
  },
  "tool": "playwright",
  "breakpoints": ["mobile", "desktop"],
  "themes": ["light", "dark"],
  "thresholds": {"max_diff_ratio": 0.005, "critical_max_diff_ratio": 0.0},
  "results": [
    {"screen": "SC-01-login", "breakpoint": "mobile", "theme": "light", "diff_ratio": 0.0, "critical": true},
    {"screen": "SC-02-home", "breakpoint": "desktop", "theme": "dark", "diff_ratio": 0.0012, "critical": false}
  ],
  "passed": true,
  "at": "2026-11-05T08:00:00Z"
}
```

- `config` 用 `path` / `version` / `sha` 绑定项目视觉配置；`results` 是逐屏摘要（至少 `screen` / `breakpoint` / `diff_ratio`，可选 `theme` / `critical`），完整结果 JSON 仍放项目证据目录。
- `ui_affected: true` 时，H3 必须有 `visual_regression`、字段完整且 `passed: true`；缺失、`passed: false`、关键界面超阈值或字段不合法都失败。Program 子级继承父级视觉证据，不重复校验。
- `ui_affected` 为 `false` 时不强制该块；一旦有界面变更却被标成 `false`，按“证据优先”原则视为 manifest 错误，由 H3 复核。
- QA 的像素级一致性章节见 [`skills/kar-qa-conformance/SKILL.md`](../skills/kar-qa-conformance/SKILL.md) 第四节：固定 fixture、冻结动画、关闭随机数据、逐断点截图、关键区域无可见差异。
- 截图、差异图、采集日志等大文件只放**项目证据目录**（如 `evidence/visual/`），不提交到本仓库，也不进入迁移包。manifest 和结果 JSON 只引用证据路径。
- H3 结论仍需人类批准；视觉回归通过是证据之一，不是人类批准的替代。

## 8. 常见错误表

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `VISUAL: FAIL` + `missing combination ...` | 结果少采集了某个界面/断点/主题 | 重跑 `capture`，或补齐该组合的结果；不要手写假数据。 |
| `duplicate combination ...` | 同一组合出现多条结果 | 去重；确认工具没有重复输出。 |
| `unknown breakpoint/theme/screen ...` | 结果里的维度名与配置不一致 | 统一配置与工具命名，或修正结果。 |
| `工具不可用，不能判定通过（BLOCKED）` | `tool_available` 不是严格 `true`，或采集命令失败/超时 | 修复工具环境后重采；BLOCKED 不写成 PASS。 |
| `does not match config tool` | 结果由另一套工具生成 | 用配置声明的工具重跑，或经人类确认后同步配置。 |
| `generated_at: valid RFC3339 timestamp required` | 时间缺时区/格式错误 | 使用 `2026-11-05T08:00:00Z` 这类带时区的时间。 |
| `diff_ratio ... exceeds critical threshold 0.0` | 关键界面出现正差异 | 修复实现；若确属字体/抗锯齿等噪声，按第 5 节由人类书面豁免并留证。 |
| `diff_ratio ... exceeds threshold ...` | 非关键界面差异超项目阈值 | 修复或按流程申请书面豁免；不要直接改大阈值。 |
| `artifact is empty` 告警 | 差异大于 0 但没记录截图 | 补 `artifact` 路径，放项目证据目录。 |
| `baseline_sha/current_sha: non-empty string required` | 工具没提供基线或当前 SHA | 让工具输出真实 SHA；不要用空串或 `unknown` 占位。 |
| `command: non-empty list required for capture` | 配置只有阈值和界面，没有采集命令 | 在项目配置补 `command`，或直接提供合法结果文件。 |
| `stdout is not one JSON object` | 工具把日志/多段 JSON 打到 stdout | 日志改到 stderr，stdout 只保留一个 JSON 对象。 |
| `command timed out` | 单次采集超时 | 调大 `--timeout` 前先确认不是渲染死锁；记录环境信息。 |
| `thresholds.critical_max_diff_ratio: must be <= max_diff_ratio` | 配置自相矛盾 | 修正阈值；关键阈值不能比一般阈值更宽松。 |
| 仓库里出现大量截图 | 证据放错位置 | 移到项目证据目录并从版本库移除；manifest/结果只引用路径。 |

验收命令：

```bash
python3 scripts/visual.py check \
  --config docs/examples/visual-config.json \
  --results docs/examples/visual-results.json
python3 -m unittest discover -s tests -p 'test_visual.py' -v
```
