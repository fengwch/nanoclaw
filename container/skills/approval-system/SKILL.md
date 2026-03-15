---
name: approval-system
description: 处理审批流程：根据用户意图解析审批类型（请假/报销/采购等），收集必要参数后调用 OA 接口发起审批或查询状态。仅在用户明确提到审批相关触发词时使用。
allowed-tools: Bash(approval-system:*), Read, Write
---

# 审批流程 Skill（Approval System）

## 何时使用

当用户消息中包含以下意图之一时使用本技能：

- 发起审批：请假、报销、采购申请、提交审批
- 查询审批：查审批、审批状态、我的审批

## 工作流程

1. **识别类型**：根据用户表述确定 `leave`（请假）、`expense`（报销）、`purchase`（采购申请）或 `query`（查询状态）。
2. **收集参数**：向用户确认或从对话中提取必填项（见下方各类型参数）。
3. **调用脚本**：在技能目录下执行 Python 脚本（容器内技能路径一般为 `/home/node/.claude/skills/approval-system/`）：
   - 发起审批：`python index.py --action submit --type <leave|expense|purchase> [--key value ...]`
   - 查询状态：`python index.py --action query [--approval_id <id>]`
4. **反馈结果**：将脚本输出的 JSON 或文本用自然语言回复用户。

## 脚本调用示例

```bash
# 发起请假（必填：reason, days）
python /home/node/.claude/skills/approval-system/index.py --action submit --type leave --reason "家事" --days 3

# 发起报销（必填：amount, reason）
python /home/node/.claude/skills/approval-system/index.py --action submit --type expense --amount 500 --reason "办公用品"

# 查询审批状态（可选 approval_id）
python /home/node/.claude/skills/approval-system/index.py --action query
```

## 参数说明

| 类型 type | 必填参数 | 可选参数 |
|-----------|----------|----------|
| leave     | reason, days | start_date, end_date |
| expense   | amount, reason | category, attachments |
| purchase  | title, amount, reason | items |

## 权限与配置

- 若 `config.json` 中 `permission_required` 为 true，实际调用 OA 前应由企业 IAM 或 Host 侧校验用户身份与权限。
- OA 接口地址与 Token 通过环境变量配置（见 `config.json` 中 `oa_base_url_env`、`oa_token_env`）；容器内未配置时脚本返回友好提示，引导用户在 Host 配置。
