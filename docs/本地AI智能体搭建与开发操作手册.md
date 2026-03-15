# 基于本地 NanoClaw 的 AI Agent 智能体搭建与开发操作手册

本文档基于实际落地操作记录整理，涵盖从环境准备、飞书接入、多群组注册、容器构建与运行，到 Skill 开发、测试与排错的全流程，便于在本地复现与二次开发。

---

## 一、环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | macOS 或 Linux（Windows 需 WSL2 + Docker） |
| Node.js | 20+（建议 22） |
| 容器运行时 | Docker Desktop 已安装且运行中 |
| Python | 3.9+（仅在使用通义网关或容器内 Python Skill 时需要） |

检查命令：

```bash
node --version   # 建议 v22.x
docker info      # 确认 Docker 可用
```

---

## 二、克隆与初始化

### 2.1 克隆仓库

```bash
git clone https://github.com/<your-username>/nanoclaw.git
cd nanoclaw
```

若从官方仓库 fork，建议保留 upstream 便于同步：

```bash
git remote rename origin upstream
git remote add origin https://github.com/<your-username>/nanoclaw.git
git push -u origin main
```

### 2.2 一键安装（Bootstrap）

```bash
bash setup.sh
```

关注输出：`NODE_OK`、`DEPS_OK`、`NATIVE_OK` 均为 true 表示通过。

### 2.3 构建 Agent 容器镜像

```bash
# 进入 container 目录执行（使用无代理、无重定义的 Docker 环境）
cd container
./build.sh
# 或指定 tag：./build.sh v1.0
```

或通过 setup 步骤构建：

```bash
npx tsx setup/index.ts --step container -- --runtime docker
```

构建成功后镜像名为 `nanoclaw-agent:latest`（或所指定 tag）。

---

## 三、配置

### 3.1 复制并编辑 .env

```bash
cp .env.example .env
# 编辑 .env，至少配置以下项
```

**必配项示例：**

```bash
# 模型端点：直连 Anthropic 或经本机网关（如通义）
ANTHROPIC_BASE_URL=http://127.0.0.1:8005
ANTHROPIC_API_KEY=sk-xxx

# 助手名，与群里 @ 的名字一致
ASSISTANT_NAME=Andy

# 容器
CONTAINER_RUNTIME=docker
CONTAINER_IMAGE=nanoclaw-agent:latest

# 并发容器数（多群同时对话时可调大）
MAX_CONCURRENT_CONTAINERS=5
```

**重要说明：**

- Credential Proxy 运行在宿主机，若使用本机网关（如 DashScope），`ANTHROPIC_BASE_URL` 应填 **`http://127.0.0.1:8005`**，不要填 `host.docker.internal`（该域名供容器访问宿主机用）。
- 容器内通过 `host.docker.internal:3001` 访问宿主机上的 Credential Proxy，由 Proxy 将请求转发到 `ANTHROPIC_BASE_URL` 并注入 Key。

### 3.2 飞书应用配置（使用飞书时）

1. 在 [飞书开放平台](https://open.feishu.cn/app) 创建应用。
2. **事件订阅**：启用 **长连接（WebSocket）**，添加事件 `im.message.receive_v1`。
3. **权限**（缺一不可）：
   - 以应用身份发消息（`im:message:send_as_bot`）
   - **获取群组中所有消息（敏感权限）**：未开通则群消息不会推送，@ 也无回复
   - 读取用户发给机器人的单聊消息（若需单聊）
4. **发布应用**（草稿状态不接收事件）。

在 `.env` 中填写：

```bash
FEISHU_APP_ID=cli_xxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxx
FEISHU_BOT_NAME=NanoClaw助手
```

### 3.3 添加飞书渠道（Host 侧）

飞书渠道通过 add-feishu Skill 注入：

```bash
npx tsx scripts/apply-skill.ts .claude/skills/add-feishu
npm run build
```

---

## 四、注册群组与多群组

### 4.1 群组 folder 命名规则

- 仅允许：英文字母、数字、下划线、连字符。
- 长度 1–64 字符。
- 非法 folder 会导致启动时 `Skipping registered group with invalid folder`，该群不会加载。

示例：`feishu`、`feishu_group1`、`feishu_xiangmuzu`。

### 4.2 获取群 Chat ID

启动服务后，在飞书群内发一条消息（或 @ 机器人），然后查库：

```bash
sqlite3 store/messages.db "SELECT jid, name FROM chats WHERE jid LIKE '%@feishu'"
```

得到 `jid` 形如：`oc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx@feishu`。

### 4.3 手动注册单个群

```sql
-- 先写入 chats（若尚未存在）
INSERT OR REPLACE INTO chats (jid, name, last_message_time, channel, is_group)
VALUES ('oc_xxx@feishu', '群名称', datetime('now'), 'feishu', 1);

-- 再注册为可触达群组
INSERT OR REPLACE INTO registered_groups (jid, name, folder, trigger_pattern, added_at, requires_trigger)
VALUES ('oc_xxx@feishu', '群名称', 'feishu_group1', '@Andy', datetime('now'), 1);
```

执行：

```bash
sqlite3 store/messages.db
# 在 sqlite3 中粘贴上述 SQL
```

### 4.4 批量注册多群（SQL 脚本）

项目中可维护 `scripts/register-feishu-groups.sql`，按实际群 ID 与 folder 填写后执行：

```bash
sqlite3 store/messages.db < scripts/register-feishu-groups.sql
```

脚本示例结构（替换 jid 与 folder）：

```sql
INSERT OR REPLACE INTO chats (jid, name, last_message_time, channel, is_group)
VALUES ('oc_群1id@feishu', '飞书群1', datetime('now'), 'feishu', 1);
INSERT OR REPLACE INTO registered_groups (jid, name, folder, trigger_pattern, added_at, requires_trigger)
VALUES ('oc_群1id@feishu', '飞书群1', 'feishu_group1', '@Andy', datetime('now'), 1);
-- 群2、群3 同理
```

**注册后需重启 NanoClaw 服务** 使新群生效。

---

## 五、启动与日常运维

### 5.1 启动服务

```bash
npx tsx setup/index.ts --step service
```

macOS 下会写入 launchd plist，常用命令：

```bash
# 重启
launchctl kickstart -k gui/$(id -u)/com.nanoclaw

# 停止
launchctl unload ~/Library/LaunchAgents/com.nanoclaw.plist

# 查看状态（PID 非 - 表示在跑）
launchctl list | grep nanoclaw
```

### 5.2 开发时前台运行

```bash
npm run dev
# 或
npx tsx src/index.ts
```

可配合 `LOG_LEVEL=debug` 排查触发与路由：

```bash
LOG_LEVEL=debug npm run dev
```

### 5.3 查看日志

```bash
tail -f logs/nanoclaw.log
```

---

## 六、容器生命周期与关闭原因

容器不会在「回复完一条消息」后立即退出，会保留一段时间以复用；关闭由以下逻辑触发，并已打关键日志便于排查。

### 6.1 关闭触发的四种原因

| 原因 | 说明 | 日志关键字 |
|------|------|------------|
| **idle_timeout** | 距上次 Agent 结果超过 `IDLE_TIMEOUT`（默认 30 分钟）无新消息 | `Idle timeout reached, closing container stdin (reason: idle_timeout)` |
| **task_done_10s_delay** | 计划任务跑完后 10 秒主动关容器（不等待 30 分钟） | `Closing task container after result (reason: task_done_10s_delay)` |
| **idle_preempt_new_task** | 容器已空闲，新任务入队，立即关当前容器以跑新任务 | `Preempting idle container for new task (reason: idle_preempt_new_task)` |
| **idle_preempt_pending_tasks** | 容器刚变为 idle 但队列中已有待执行任务 | `Container idle but pending tasks exist, closing (reason: idle_preempt_pending_tasks)` |

统一写 _close 时会有：

```
Container close requested: wrote _close sentinel (container will exit)
```

在日志中搜 **`Container close requested`** 或 **`reason:`** 即可定位是哪一种原因导致关闭。

### 6.2 可调参数

- **项目根目录 `.env`**（由 Host 读取，容器内 `data/env/.env` 不控制等待时长）：
  - `IDLE_TIMEOUT`：空闲多少毫秒后写 _close（默认 1800000 = 30 分钟）
  - `CONTAINER_TIMEOUT`：硬超时毫秒数，防止容器卡死

---

## 七、Skill 开发

### 7.1 容器内 Skill 位置与同步

- **Host 源码**：`container/skills/` 下每个子目录为一个 Skill（如 `weather/`、`approval-system/`）。
- **同步时机**：每次为该群**启动新容器**时，Host 会将 `container/skills/` 同步到该群的 `data/sessions/{group}/.claude/skills/`，再挂载进容器。
- **结论**：改 Host 上 `container/skills/` 即可，**无需重建 Docker 镜像**；仅当修改 Dockerfile 或 `container/agent-runner` 源码时才需重新 `./container/build.sh`。

### 7.2 新增 MCP 工具（如天气）

1. **实现逻辑**：在 `container/agent-runner/src/` 中可抽离独立模块（如 `weather.ts`），在 `ipc-mcp-stdio.ts` 中注册 MCP 工具并调用该模块。
2. **容器内测试**：在 `container/agent-runner` 下为逻辑写单元/集成测试（如 `weather.test.ts`），使用 vitest：

   ```bash
   cd container/agent-runner
   npm install
   npm test
   ```

   集成测试会真实请求 Open-Meteo；若需跳过网络：`SKIP_WEATHER_INTEGRATION=1 npm test`。
3. **Skill 说明**：在 `container/skills/weather/` 下提供 `SKILL.md`、`config.json`，描述何时使用、allowed-tools（如 `mcp__nanoclaw__get_weather`）。

### 7.3 审批类 Skill（Python）

- 在 `container/skills/approval-system/` 下放置 `index.py`、`oa_connector.py`、`config.json`、`SKILL.md`。
- Dockerfile 中需安装 `python3`、`python3-venv`，并做 `python` → `python3` 链接，以便容器内执行 `python index.py --action submit --type leave ...`。

---

## 八、IPC 权限简述

- **主群**：可向任意已注册会话发消息、为任意群建/管任务、`register_group`、`refresh_groups`。
- **非主群**：仅能向本群发消息、为本群建任务、管理本群任务；不能注册新群或刷新群列表。

详细说明见 **docs/IPC_PERMISSIONS_ZH.md**。

---

## 九、常见问题与排查

### 9.1 群里 @Andy 无回复

1. **看是否收到消息**：`tail -f logs/nanoclaw.log`，在群里发 `@Andy 你好`。  
   - 无 `Feishu message received` → 飞书未推送。检查：机器人是否在群内、是否开通「获取群组中所有消息」、是否已发布应用、事件是否为长连接 + `im.message.receive_v1`。
   - 有 `Feishu message from unregistered group` → 该群未注册或 folder 非法，检查 `registered_groups` 与 folder 规则，重启服务。
2. **确认触发词一致**：`.env` 中 `ASSISTANT_NAME=Andy`，则 `registered_groups` 中该群 `trigger_pattern` 应为 `@Andy`。
3. **无触发词跳过**：用 `LOG_LEVEL=debug npm run dev` 再发一条，若出现 `Skip: no trigger in messages (non-main group)`，说明内容未匹配到触发词。

### 9.2 端口 3001 被占用（EADDRINUSE）

```bash
lsof -ti :3001 | xargs kill -9
launchctl kickstart -k gui/$(id -u)/com.nanoclaw
```

### 9.3 Credential Proxy 连接网关失败（ECONNRESET）

- 将 `.env` 中 `ANTHROPIC_BASE_URL` 改为 **`http://127.0.0.1:8005`**，不要用 `host.docker.internal`（宿主机上 Proxy 访问网关应用 127.0.0.1）。

### 9.4 注册群组报错 Skipping registered group with invalid folder

- folder 只能包含英文字母、数字、下划线、连字符，且 1–64 字符；如将中文或非法字符改为 `feishu_xiangmuzu` 等。

---

## 十、相关文档

| 文档 | 说明 |
|------|------|
| **docs/SETUP_FEISHU_ZH.md** | 飞书安装部署与排错 |
| **docs/IPC_PERMISSIONS_ZH.md** | IPC 权限与 MCP 工具说明 |
| **docs/infos/VERIFIED_IMPLEMENTATION_PLAN.md** | 已验证架构与落地步骤 |
| **docs/SECURITY.md** | 安全模型与边界 |

---

*本手册基于历史操作记录整理，随仓库更新可酌情修订。*
