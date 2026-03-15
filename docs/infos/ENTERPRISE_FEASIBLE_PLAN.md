# NanoClaw 企业智能体基座 — 可行方案

本文档基于 [落地概况 1.md](1.md) 的分析框架，结合**已在本仓库验证过的能力**（Docker 安装、DashScope 国产模型网关、飞书渠道、群组与存储架构），整理出一份可直接落地的可行方案。凡与现有实现不一致之处均已按代码与文档修正。

---

## 一、落地概况要点与事实校正

### 1.1 从 1.md 提炼的结论（保持）

- **安全可控**：NanoClaw 的容器级隔离、极简可审计代码，适合作为企业智能体基座的安全内核。
- **需求与能力对应**：意图识别可做（Host 层或 Agent+工具）；工作流/审批通过 **Skill + MCP** 对接；记忆与状态当前为单 SQLite + 按群目录隔离，数据落 host。
- **三场景**：1 对 1 数字助理、审批流程事务助理、项目小组型助理，均可通过「内核 + 场景化 Skill」实现。

### 1.2 与现有实现对齐的修正

| 1.md 中的表述 | 实际情况（已验证） | 可行方案中的采用 |
|---------------|--------------------|------------------|
| 修改 `src/container-runner.ts` 适配国产模型 API | 本仓库已采用 **DashScope 网关**：请求走 Anthropic 协议，网关转通义；无需改 container-runner。 | 企业环境继续使用 `ANTHROPIC_BASE_URL` + 网关（或自建 GLM/其他兼容网关）。 |
| `ANTHROPIC_BASE_URL=https://open.bigmodel.cn/...` | 国产模型应指向**本机网关**，容器通过 `host.docker.internal` 访问。 | `.env` 配置为 `ANTHROPIC_BASE_URL=http://host.docker.internal:8005`，网关再转发至 GLM/通义等。 |
| 修改 `src/groups.ts` 同步企业组织架构 | 仓库中**无** `src/groups.ts`；群组在 `src/db.ts` 的 `registered_groups` 表及 `src/index.ts` 的 `registerGroup()` 中维护。 | 企业化时在 **Skill** 或 **setup 后处理脚本**中调用企业 API，向 `registered_groups` 写入/更新群组；或扩展 db 层增加「成员/角色」表。 |
| 渠道配置「后续配置飞书」 | 本仓库已提供 **add-feishu** Skill 与 [SETUP_FEISHU_ZH.md](../SETUP_FEISHU_ZH.md)。 | 直接使用 `/add-feishu` 与文档完成飞书对接；如需钉钉/Slack，按同模式加 Skill。 |

### 1.3 存储与记忆（与深度分析一致）

- **单 SQLite**：`store/messages.db`，通过 `chat_jid` / `group_folder` 区分群组，**非**每群独立 SQLite。
- **按群隔离**：`groups/{channel}_{name}/`（CLAUDE.md、日志、Agent 生成文件）、`data/sessions/{group_folder}/`（会话数据）。
- **Docker 落 host**：上述目录与 `store/` 均在 host，挂载进容器，重启不丢数据；企业部署时保证挂载路径持久化即可。

若企业要求「每群独立 SQLite」或「每租户独立 DB」，需单独规划改造（按群/租户选择 DB 路径 + 卷挂载），本方案仍以当前单库 + 行级/目录级隔离为前提。

---

## 二、可行方案总览

采用 **「内核 + 场景化 Skill」** 的分阶段建设：

1. **阶段一**：基于 NanoClaw 搭建**最小可用内核**（环境 + 国产模型 + 企业渠道 + 基础对话 + 容器隔离）。
2. **阶段二**：优先做**审批流程助理**，用一个高质量 Skill 打通「对话 → 意图/参数 → OA 接口 → 状态回写」全流程，并加审计。
3. **阶段三**：将已验证的 Skill 模式与权限/审计习惯复用到 1 对 1 助理、项目小组助理，并视需要增强记忆与监控。

---

## 三、阶段一：最小可用内核（已验证路径）

以下步骤均基于当前仓库已支持的安装与配置方式。

### 3.1 基础环境

- **系统**：macOS 或 Linux（Windows 用 WSL2 + Docker）。
- **依赖**：Node.js 20+、Docker 已安装并运行。
- **一键脚本（可选）**：`./scripts/install-docker.sh` 完成依赖安装、镜像构建、Host 编译。

详见 [INSTALL_DOCKER_ZH.md](../INSTALL_DOCKER_ZH.md)。

### 3.2 国产大模型（通义）

- 启动 **DashScope 网关**（端口 8005，虚拟环境 `nanoclaw_env`）：
  ```bash
  cd dashscope_gateway
  ./run.sh
  ```
- NanoClaw `.env` 配置（不填 `CLAUDE_CODE_OAUTH_TOKEN`）：
  ```bash
  ANTHROPIC_BASE_URL=http://host.docker.internal:8005
  ANTHROPIC_API_KEY=<DashScope API Key>
  ```
- 同步到容器：`mkdir -p data/env && cp .env data/env/env`。

其他国产模型（如 GLM）可自建同类「Anthropic 协议 → 厂商 API」网关，仅需将 `ANTHROPIC_BASE_URL` 指向该网关。

### 3.3 企业渠道（飞书）

- 在 Claude Code 中执行 `/add-feishu`，按 Skill 与 [SETUP_FEISHU_ZH.md](../SETUP_FEISHU_ZH.md) 完成应用创建、事件订阅、消息接收 URL（建议内网可访问地址）。
- 配置完成后执行 `cp .env data/env/env`、`npm run build`，重启服务。

### 3.4 群组与权限（企业化扩展）

- **当前**：群组由主频道通过对话注册（或 IPC 注册），数据在 `registered_groups` 表；无内置 RBAC。
- **可行扩展**（不改变内核前提下）：
  - 在 **Skill** 或独立「同步脚本」中调用企业 API（组织架构/项目成员），生成或更新群组列表，并调用现有 `registerGroup` 或等价写入逻辑（需通过主频道或受控 IPC 入口）。
  - 在 Skill 内调用企业 IAM/LDAP 做身份与角色校验；敏感工具调用在 `src/ipc.ts` 或 MCP 层打**审计日志**。

### 3.5 启动与自检

- 启动 NanoClaw：`npm run dev` 或配置 launchd/systemd。
- 确认至少一个渠道连接成功（无 “No channels connected”）、飞书内可触发助手回复。

---

## 四、阶段二：审批流程事务助理（核心价值验证）

### 4.1 目标

从自然语言到 OA 审批的**确定性、可审计**闭环：识别审批意图 → 拉取表单/参数 → 调用 OA 创建审批单 → 接收 webhook 状态回写 → 在对话中反馈。

### 4.2 实现方式（Skill + MCP）

- **新建 Skill**：例如 `.claude/skills/approval-flow/`，包含：
  - `SKILL.md`：说明能力、触发方式、所需权限与配置项。
  - 若需改 Host 代码：按现有 skill 规范提供 `modify/` 与 manifest；否则仅提供容器侧 MCP 或脚本。
- **审批逻辑**：
  - **方式 A**：在容器内通过 **MCP Server** 暴露「创建审批单」「查询审批状态」等工具，Agent 根据对话调用；OA 的 API Key 等由 Host 凭证代理或环境变量注入，不落容器。
  - **方式 B**：在 Host 侧增加 HTTP 回调或轮询，接收 OA webhook，将状态写入 DB 或 IPC，供 Agent 查询。
- **确定性**：在 Skill 或 MCP 工具中实现「确认 → 执行 → 回写」的固定流程；敏感操作前可要求用户二次确认（如“确定提交吗？”）。
- **审计**：在 `src/ipc.ts` 或 MCP 调用链上对「审批创建/查询/回写」打日志（谁、何时、哪个群、何种操作、结果），便于企业审计。

### 4.3 与 1.md 的对应

- 1.md 中的「approval-flow Skill」「监听关键词 → 调 OA API → webhook 回写」与本方案一致；具体实现以 **MCP 工具 + Skill 描述** 或 **Host 小服务 + Skill** 均可，视企业 OA 接口形式而定。

---

## 五、阶段三：1 对 1 与项目小组助理（复用模式）

### 5.1 1 对 1 数字助理

- **隔离**：每个用户对应一个群组（或主频道下的私聊），天然享有独立 `groups/{name}/` 与 `data/sessions/{name}/`。
- **个性化**：在对应群组的 `CLAUDE.md` 中维护偏好；可开发 Skill 连接日历、邮件等（通过 MCP 或 Host 代理）。
- **无需改内核**：仅新增 Skill 与 MCP/接口。

### 5.2 项目小组型助理

- **以项目为群组**：一个项目一个群组，严格按现有「群组 = 独立目录 + 会话」隔离。
- **项目上下文**：开发 `project-context` 类 Skill，将项目文档（Confluence/Git 等）同步到群组可访问的存储或向量库，通过 MCP 供 Agent 检索。
- **权限**：谁可触发「发布」「审批」等，在 Skill 内调用企业 IAM 或角色表判断；敏感操作继续打审计日志。

### 5.3 记忆与 Token 可观测（可选增强）

- **长记忆/检索**：在 Skill 或独立服务中引入向量库（如 Chroma），将重要摘要或文档向量化，通过 MCP 暴露给 Agent；不改变 NanoClaw 单 SQLite 的现状。
- **Token 计量**：在调用模型的位置（如 credential proxy 或网关）统计请求/响应 token，写入监控库或 Prometheus，再对接 Grafana 做看板与配额告警。

---

## 六、部署与安全加固（与 1.md 一致）

- **镜像**：基于现有 Dockerfile，保持非 root、最小依赖；可按企业规范再裁剪。
- **网络**：仅允许内网指定 IP/段访问 NanoClaw 与网关端口；飞书等回调 URL 使用内网可达地址。
- **秘密**：API Key、OA 密钥等放入 Vault 或 K8s Secrets，通过启动时注入环境变量或挂载文件，避免写死在 `.env` 并提交仓库。

---

## 七、总结：已验证 + 待建设

| 项目 | 状态 | 说明 |
|------|------|------|
| Docker 安装与容器镜像 | 已验证 | 见 [INSTALL_DOCKER_ZH.md](../INSTALL_DOCKER_ZH.md)、`scripts/install-docker.sh` |
| 国产模型（通义） | 已验证 | DashScope 网关 `dashscope_gateway/`，端口 8005，`.env` 配置 |
| 飞书渠道 | 已验证 | `/add-feishu`、[SETUP_FEISHU_ZH.md](../SETUP_FEISHU_ZH.md) |
| 群组与记忆架构 | 已明确 | 单 SQLite + 按群目录/会话隔离，数据落 host |
| 意图识别 | 待增强 | 可选 Host 层 NLU 或维持 Agent+工具 模式 |
| 审批/工作流 Skill | 待建设 | 按阶段二开发 approval-flow 类 Skill + MCP |
| 企业群组/权限同步 | 待扩展 | Skill 或脚本 + db/registerGroup 扩展 |
| 审计与 Token 监控 | 待注入 | ipc/网关层打日志与计量 |

**建议执行顺序**：先完成阶段一（内核 + 飞书 + 通义），再集中力量做一个审批场景 Skill（阶段二），验证通过后再复制到 1 对 1 与项目小组（阶段三），并视需要补记忆与监控。这样在安全可控的前提下，用最小改动和已验证组件形成企业可落地的智能体基座。
