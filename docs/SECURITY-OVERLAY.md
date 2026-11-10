# R3 安全 overlay

任何 `risk: R3` 的变更集，除正常门禁外必须完成安全 overlay：**威胁模型、权限矩阵、密钥扫描、依赖扫描、回滚演练、独立安全评审人**。缺一项，H3 不得通过。

## 1. 何时触发

按 `config/KAR-Squad-Config-v4.4.md` §3.1 的风险定义：认证/授权、支付/计费、密钥/生产配置、不可逆数据、合规。Lead 在 intake 判定 `R3` 后立即：

1. 在 H1 卡上写明“这是 R3，需要独立安全评审”。
2. 指定独立安全评审人（不能是 Developer/Reviewer 本人，也不能是同一个 Agent 身份）。
3. 在 H2 设计方案里包含“安全/权限/隐私/审计”章节，不写一句话结论。

## 2. 四份产物

放在需求目录下，平铺、纳入 manifest `security_overlay`：

| 产物 | 内容 | 谁写 |
| --- | --- | --- |
| 威胁模型.html | 资产、角色、入口、信任边界、STRIDE/攻击面、top 风险与缓解、残余风险 | Architect |
| 权限矩阵.html | 资源 × 角色 × 动作；默认拒绝；越权路径；测试证据 | Architect + Reviewer |
| 安全扫描报告.html | 密钥扫描 + 依赖扫描；命令、版本、时间、结果、例外 | Developer/QA |
| 回滚演练记录.html | 回滚步骤、执行环境、耗时、数据恢复、证据链接 | QA |

### 2.1 威胁模型最小结构

```text
1. 资产：数据、凭证、资金、审计记录
2. 角色与权限：匿名/用户/管理员/服务
3. 入口与信任边界：API、Webhook、上传、后台
4. 攻击面与 STRIDE：每项给缓解与测试
5. Top 风险：影响 × 可能性 → 处置（缓解/接受/转移）
6. 残余风险：谁接受、复审时间
```

### 2.2 权限矩阵最小结构

```text
| 资源 | 动作 | 匿名 | 用户 | 管理员 | 服务 | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| /orders | read | ✗ | 仅本人 | 全部 | 只读 | TC-12 |
```

- 默认拒绝；每个 ✗ 至少一条越权测试。
- 服务身份最小权限；不共享管理员凭证。
- 矩阵变化视为契约变化，走 H2 或新 change set。

### 2.3 密钥扫描

推荐命令（任选其一，记录版本与结果）：

```bash
gitleaks detect --no-git --redact --verbose
trufflehog filesystem . --only-verified
git secrets --scan
```

- `findings` 必须为 0；发现真密钥：停止、保留证据、升级人类、轮换凭证，不写进 issue。
- 第三方 token 只通过 Web 设置页配置，不进仓库、不进日志、不进 manifest。

### 2.4 依赖扫描

```bash
npm audit --audit-level=high
pip-audit
osv-scanner -r .
```

- 阈值：high/critical 必须处置；中低风险记录并给 owner/到期。
- 未处置发现阻塞 H3；不要用 `|| true` 让扫描“看起来绿”。

### 2.5 回滚演练

- 在 staging（或可回退的等价环境）实际执行回滚，不只写步骤。
- 记录：触发条件、命令、耗时、数据恢复结果、失败点、证据路径。
- 不可逆数据变更必须有人类书面接受；没有演练不得进 H3。

## 3. manifest 记录

```json
"security_overlay": {
  "threat_model": {"path": ".../威胁模型.html", "version": "1.0", "sha": "<64 hex>"},
  "permission_matrix": {"path": ".../权限矩阵.html", "version": "1.0", "sha": "<64 hex>"},
  "secret_scan": {"tool": "gitleaks detect --no-git --redact", "status": "passed", "findings": 0, "at": "2026-11-05T09:00:00Z"},
  "dependency_scan": {"tool": "npm audit --audit-level=high", "status": "passed", "severity": "high", "findings": 0, "at": "2026-11-05T09:10:00Z"},
  "rollback_drill": {"at": "2026-11-05T14:30:00Z", "result": "passed", "duration_minutes": 8, "evidence": "evidence/reports/rollback-drill.md"},
  "reviewer": {
    "id": "<user-id>",
    "role": "security",
    "independent": true,
    "verdict": "pass",
    "at": "2026-11-05T16:00:00Z",
    "scope": "认证授权、密钥、不可逆数据与回滚路径"
  }
}
```

## 4. 独立安全评审人

- `role` 必须是 `security`；`independent` 必须是 `true`。
- 不能是 `manifest.developer` / `manifest.reviewer`，也不能与主责 Developer/Reviewer 是同一 Agent 身份。
- **与 H3 的 `gates.h3.second_reviewer` 是同一个人**：同一位评审人既签 overlay，也做 H3 第二人复核；`policy.py` 校验两者 id 一致、role 为 `security`。
- 复核范围至少：威胁模型、权限矩阵、密钥/依赖扫描结论、回滚演练、H3 三项检查。
- 安全评审人的 `pass` 不代替人类 H3 批准；人类仍然 `/approve`。

## 5. 门禁与命令

H3 前：

```bash
python3 scripts/manifest.py check --profile h3 --manifest <path> --check-remotes --check-prs --check-ci
python3 scripts/policy.py check --manifest <path> --profile h3
```

失败处理：

| 失败 | 处理 |
| --- | --- |
| 缺威胁模型/权限矩阵 | 回到设计，补齐后重新走 H2 或记录变更 |
| 扫描失败/有发现 | 修复或由人类书面接受并记入风险登记册；未处置不进 H3 |
| 回滚演练失败 | 阻塞；修回滚方案并重演 |
| 评审人非独立 | 更换评审人后重做 |
| 第二人 id 不一致 | 统一为同一位独立安全评审人 |

## 6. 禁止

- 不把安全评审做成“勾选框”：没有证据的 pass 视为橡皮图章，H3 抽样发现后整门退回。
- 不把密钥、token、生产数据写进文档、manifest、issue 或截图。
- 不以“内部系统”“只在内网”为由跳过授权与回滚检查。
- 不允许 Agent 代替人类接受残余风险。
