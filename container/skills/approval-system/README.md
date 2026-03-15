# 审批系统 Skill（Python）

容器内 Agent 通过本技能发起请假/报销/采购审批或查询审批状态。逻辑为 Python 实现，无需重建镜像，下次起容器时会从 Host 的 `container/skills/approval-system/` 同步进群组 `.claude/skills/`。

## 文件说明

| 文件 | 说明 |
|------|------|
| SKILL.md | Agent 使用说明：触发词、工作流、调用示例 |
| config.json | 技能元数据、审批类型与必填参数、OA 环境变量名 |
| index.py | 主入口：解析 `--action submit/query` 与参数，调用 oa_connector |
| oa_connector.py | OA 连接器：未配置时返回模拟数据，配置后请求真实 OA API |

## 本地/容器内测试

```bash
# 发起请假（模拟）
python index.py --action submit --type leave --reason "家事" --days 3

# 查询状态（模拟）
python index.py --action query
```

## 对接真实 OA

1. 在 Host 或容器可见环境中配置环境变量（容器内可通过 data/env 或 credential 代理侧注入）：
   - `OA_BASE_URL`：OA 接口根地址，如 `https://oa.company.com/api`
   - `OA_API_TOKEN`：鉴权 Token
2. 在 `oa_connector.py` 中按企业 OA 实际接口调整：
   - `submit_approval`：POST 路径与请求体格式
   - `query_approval_status`：GET 路径与响应解析
3. 若 OA 使用 Cookie 或其它鉴权方式，在 `oa_connector._request` 中修改 headers。

## 权限

`config.json` 中 `permission_required: true` 表示建议在调用 OA 前做用户级权限校验；实际校验可在 Host 侧 IAM 或 Skill 外层逻辑中实现。
