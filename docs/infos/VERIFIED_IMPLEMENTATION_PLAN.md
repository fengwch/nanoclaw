# NanoClaw 企业智能体基座 — 已验证实施计划

> **一句话总结**：Host 管渠道与路由、凭证与选型，容器按群组串行跑 Agent；多群组并行、单库按群隔离，Docker+通义网关+飞书已打通。（50 字）
>
> **核心结论**：① 多群组之间是有限并行，单个群组内部是串行。② 实际调用 LLM 由容器发起，经 Host 代理转发到真实端点。

本文档仅包含**已在本仓库验证通过**的能力与操作步骤，作为可复现的落地计划。未验证的功能（如企业群组同步、审计与 Token 监控等）不写入本提纲。

---

## 一、背景

- **NanoClaw** 是以「单进程 + 容器隔离 + 技能扩展」为核心的个人/小团队 AI 助手基座，代码量小、可审计，具备**操作系统级容器隔离**与**显式挂载**，满足企业「安全可控」的基础要求。
- 本仓库在官方能力之上已完成：**本机 Docker 安装与镜像构建**、**国产大模型（通义千问）网关**、**飞书渠道接入**，以及**群组与记忆存储架构**的确认（单 SQLite + 按群目录/会话隔离、数据落 host）。
- 上述能力已在实际环境中跑通，可作为企业内智能体「最小可用内核」的基线。

---

## 二、需求（本计划所覆盖部分）

| 需求项 | 本计划是否覆盖 | 说明 |
|--------|----------------|------|
| 安全可控 | 是 | 容器隔离、凭证不落容器、挂载白名单、群组隔离已验证。 |
| 使用国产大模型（如通义） | 是 | 通过 DashScope 网关 + .env 配置，已验证。 |
| 企业级通信渠道（飞书） | 是 | add-feishu Skill 与 SETUP_FEISHU_ZH 已验证。 |
| 群组级记忆与数据落 host | 是 | 单 SQLite + 按群目录/会话隔离、Docker 挂载 host 路径已明确并验证。 |
| 一键/脚本化安装（Docker） | 是 | `scripts/install-docker.sh` 与 INSTALL_DOCKER_ZH 已验证。 |
| 审批流程（请假等） | 是 | 容器内 approval-system Skill：触发词识别、参数收集、Python 脚本提交（含模拟）已验证。 |

以下需求**未验证**，不纳入本计划提纲：对话意图识别增强、企业群组/权限同步、审计与 Token 监控。

---

## 三、解决思路

- 将 NanoClaw 作为**安全隔离内核**：Agent 在容器内执行，仅能访问显式挂载的目录；凭证经 Host 代理注入，容器内无真实 Key。
- **国产模型**：不修改 NanoClaw 核心请求逻辑，通过本机**协议转换网关**（Anthropic → 通义）统一入口，`.env` 中配置 `ANTHROPIC_BASE_URL` 指向网关即可。
- **企业渠道**：通过官方 Skill 机制接入飞书（add-feishu），按飞书开放平台配置应用与长连接，实现「飞书 ↔ NanoClaw」双向消息。
- **记忆与持久化**：沿用现有「单 SQLite + 按群目录 + 按群会话」设计，所有持久化目录（store/、data/、groups/）位于 host，通过 Docker 挂载进容器，重启不丢数据。

---

## 四、方案原理

### 4.1 已验证架构要点

- **单 Node 进程（Host）**：负责渠道连接、消息轮询（SQLite）、群组队列、计划任务、IPC 处理、凭证代理；不运行大模型推理。
- **容器（Agent）**：每个会话/群组任务在独立容器中运行 Claude Agent SDK，通过 stdin/stdout 与 Host 通信；模型请求发往 `ANTHROPIC_BASE_URL`（即本机网关或真实 Anthropic）。
- **凭证代理**：Host 读取 `.env` 中的 `ANTHROPIC_API_KEY`（或 DashScope Key），将请求转发到 `ANTHROPIC_BASE_URL` 时注入 x-api-key，容器内始终为占位符，无真实密钥。
- **存储**：
  - **单库**：`store/messages.db`，表包括 messages、chats、scheduled_tasks、sessions、registered_groups、router_state 等，通过 `chat_jid` / `group_folder` 区分群组。
  - **按群目录**：`groups/{channel}_{name}/`（CLAUDE.md、日志、Agent 生成文件）、`data/sessions/{group_folder}/`（会话数据）；Docker 将 host 上这些路径挂载进容器，数据落 host。

### 4.2 国产模型（通义）原理

- **DashScope 网关**（`dashscope_gateway/`）：监听本机 8005，接收 Anthropic 格式 `POST /v1/messages`，转成 DashScope 兼容接口请求，再将响应转回 Anthropic 格式。
- NanoClaw 容器内请求发往 `http://host.docker.internal:8005`，由 Host 的 credential proxy 转发并注入 Key；网关用该 Key 调通义，容器无感知。

### 4.3 飞书渠道原理

- **add-feishu** Skill：向仓库注入飞书渠道实现（`src/channels/feishu.ts`）及注册逻辑；飞书使用 **WebSocket 长连接** 接收消息，无需公网 Webhook URL。
- 消息流向：飞书 → 渠道层写入 SQLite → Host 轮询 → 按群组调度容器 → Agent 回复经渠道发回飞书。

### 4.4 消息路由原理

- **路由发生在 Host，不是容器内**：由 Host 上的消息循环与群组队列决定「哪条消息发给哪个群组、对应哪个容器」；容器只接收已经按群组分好、通过 stdin 喂入的消息，**不在容器内部再做按群组的路由**。
- **按群组归属**：渠道收到消息时带上 `chat_jid`（群组标识），写入 SQLite；Host 的 `startMessageLoop` 从 DB 拉新消息后按 `chat_jid` 聚成 `messagesByGroup`，每个 `chatJid` 对应一个群组。
- **按群组选容器**：
  - 若该群组**已有在跑容器**：Host 调用 `queue.sendMessage(chatJid, formatted)`，将格式化后的消息通过 **stdin 管道** 发给该群组当前占用的容器。
  - 若该群组**没有在跑容器**：Host 调用 `queue.enqueueMessageCheck(chatJid)`，由 GroupQueue 为该群组**启动一个专用容器**，再在 `processGroupMessages(chatJid)` 中把该群消息喂给该新容器。
- **一容器一群组**：每个容器实例从启动起只绑定一个 `chatJid`，生命周期内只处理该群组的消息与回复；不存在「多个群组消息先进同一容器再在容器内路由」。
- **出站路由（router.ts）**：`routeOutbound` / `findChannel` 负责**回复时选渠道**（根据 JID 决定由飞书/WhatsApp 等哪个 channel 发出），与「消息进哪个容器」无关；进容器的路由在 `index.ts` + `group-queue.ts` 完成。

### 4.5 Host 侧与容器侧分工

| 维度 | Host 侧（Node 单进程） | 容器侧（按群组起的 Docker 容器） |
|------|------------------------|----------------------------------|
| **消息入口** | 各渠道（飞书等）回调 `onMessage(chatJid, msg)`，Host 写入 SQLite，带 `chat_jid`。 | 不直接收渠道消息；只通过 Host 转发的 stdin 收该群组的消息。 |
| **路由决策** | 轮询 DB 得到新消息 → 按 `chat_jid` 分组 → 判断该群是否有活跃容器 → 有则 pipe 到该容器，无则入队并启动新容器。 | 无路由逻辑；只处理本容器绑定的单群组 stdin 输入。 |
| **并发与队列** | GroupQueue 管理「每群一个容器」、最大并发容器数、排队；`enqueueMessageCheck` / `runForGroup` / `sendMessage`。 | 单进程运行 Claude Agent SDK，顺序处理 stdin 输入、产生 stdout 输出。 |
| **模型请求** | 不跑推理；提供 credential proxy，转发容器发出的 API 请求并注入 `ANTHROPIC_API_KEY`。 | 运行 Agent，向 `ANTHROPIC_BASE_URL` 发请求（经 Host 代理），得到模型回复后经 stdout 输出。 |
| **回复出口** | 解析容器 stdout（含 send_message 等），根据 JID 用 `findChannel` 找到渠道，调用 `channel.sendMessage(jid, text)` 发回飞书等。 | 仅通过 stdout 输出结构化结果（如 send_message）；不直接连渠道。 |
| **存储与状态** | 维护 SQLite（messages、chats、sessions、registered_groups、router_state）、`lastTimestamp` / `lastAgentTimestamp`、计划任务、IPC。 | 仅能读写挂载进容器的目录（如该群 `groups/{name}/`、`data/sessions/{name}/`）；不直接访问 DB。 |
| **凭证与配置** | 读取 `.env`（含 `ANTHROPIC_API_KEY`、渠道密钥），通过 data/env 挂载与代理注入容器；容器内无真实 Key。 | 使用占位符或代理地址；模型请求经 Host 代理发出。 |

### 4.6 使用哪个 LLM：配置与调用在哪一侧

- **配置在 Host 侧**：选用哪个 LLM（即请求发往哪个端点）由 Host 的 `.env` 决定：`ANTHROPIC_BASE_URL`（如 `http://host.docker.internal:8005` 走 DashScope 网关）、`ANTHROPIC_API_KEY`（真实 Key 或网关用 Key）。这些仅在 Host 上读取，**不会**以明文写入容器。
- **调用在容器侧**：容器内运行 Claude Agent SDK，由 **容器进程** 向「模型 API」发起 HTTP 请求。容器内配置的 `ANTHROPIC_BASE_URL` 被设为 **Host 的 credential proxy 地址**（如 `http://host.docker.internal:3001`），`ANTHROPIC_API_KEY` 为占位符。即：**发起请求的是容器，但请求先到 Host 的 credential proxy**。
- **代理转发**：Host 上的 credential proxy 收到容器的请求后，用 Host 的 `.env` 中的真实 `ANTHROPIC_BASE_URL` 与 `ANTHROPIC_API_KEY` 转发到真实端点（Anthropic 或自建网关），再把响应回给容器。因此「用哪个 LLM」由 Host 的 `.env` 决定，**实际调用由容器发起、经 Host 代理转发**。

### 4.7 并行与串行处理

- **跨群组：并行**：多个群组可同时各占一个容器，由 GroupQueue 管理。最大并发容器数由 `MAX_CONCURRENT_CONTAINERS` 控制（默认 5，可通过环境变量覆盖）。例如群组 A、B、C 同时有消息时，最多可同时跑 3 个容器分别处理 A、B、C。
- **群组内：串行**：同一群组在同一时刻只对应一个容器，该群组的消息按顺序通过 stdin 喂给该容器，由容器内 Agent 串行处理；同一群组不会多容器并行。
- **超出并发时**：当已运行的容器数达到上限，新有消息的群组会进入等待队列（`enqueueMessageCheck`），等有容器退出后再为其启动新容器并处理，因此整体是**有限并行（多群组并行 + 单群组串行）**。

**如何同时调起多个容器**

1. **提高并发上限**（可选）：在 `.env` 或启动前设置 `MAX_CONCURRENT_CONTAINERS=10`（或更大），则最多允许同时运行 10 个容器；不设则默认 5。
2. **准备多个已注册群组**：在 `registered_groups` 里为每个要并行的群各一条记录（不同 `jid`、不同 `folder`），例如主群 + 飞书群 A、飞书群 B、飞书群 C。
3. **同时触发**：在**不同群**里几乎同时发一条会触发处理的消息（非主群需带触发词，如 `@Andy 你好`）。Host 消息循环按 `chat_jid` 分组后，会为每个有消息的群调用 `enqueueMessageCheck(chatJid)`；GroupQueue 会为每个群各起一个容器，直到达到 `MAX_CONCURRENT_CONTAINERS`，其余排队。
4. **验证**：看日志应出现多条 `Spawning container agent` 或 `Container mount configuration`，容器名分别为 `nanoclaw-{folder1}-*`、`nanoclaw-{folder2}-*` 等；或 `docker ps` 可看到多个 nanoclaw 容器。

### 4.8 容器何时被关闭（销毁）及判断条件

容器**不会**在「消息处理完」后立刻退出，而是会保留一段时间，以便同一群组的新消息直接 pipe 进该容器，无需重新起容器。关闭由以下两个机制决定：

**1. 空闲超时（正常关闭）**

- **判断**：自该容器**上一次产生 Agent 结果**（一次流式输出算一次）起，若在 **IDLE_TIMEOUT** 时间内**没有**新消息被 pipe 进该容器，则视为可关闭。
- **默认时长**：`IDLE_TIMEOUT` 默认 **30 分钟**（1800000 ms），可通过 `.env` 中 `IDLE_TIMEOUT` 修改。
- **动作**：Host 调用 `queue.closeStdin(chatJid)`，向该群 IPC 目录写入 **`_close`** 标记；容器内 agent-runner 轮询到该文件后**主动退出**；进程退出后 Docker 因 `run --rm` 自动删除容器。
- **重置**：只要在 IDLE_TIMEOUT 内又有新消息 pipe 进该容器（或产生新的 result），空闲计时会重置，容器继续保留。

**2. 硬超时（防止卡死）**

- **判断**：自容器启动（或自上次「有流式输出」）起，若超过 **timeoutMs** 仍未退出，则强制关闭。
- **时长**：`timeoutMs = max(CONTAINER_TIMEOUT, IDLE_TIMEOUT + 30_000)`。默认 `CONTAINER_TIMEOUT` 为 30 分钟，故通常为 **IDLE_TIMEOUT + 30 秒**（给 _close 留出执行时间）。
- **动作**：Host 执行 `docker stop <containerName>`；若未在规定时间内停掉，再发 SIGKILL。容器退出后同样由 `--rm` 回收。

**小结**

| 条件 | 时长（默认） | 行为 |
|------|--------------|------|
| 空闲：上次结果后无新消息/无新 result | IDLE_TIMEOUT = 30 分钟 | 写 _close → 容器主动退出 → 容器被销毁 |
| 硬超时：容器一直未退出 | max(CONTAINER_TIMEOUT, IDLE_TIMEOUT+30s) | docker stop → 容器退出 → 容器被销毁 |

环境变量：`.env` 中 `IDLE_TIMEOUT`（毫秒）、`CONTAINER_TIMEOUT`（毫秒）可调；单群可覆盖见 `group.containerConfig.timeout`。

### 4.9 容器内部运行与 Skills

**容器内如何运行：**

- **入口**：容器启动时从 stdin 接收一条 JSON（`ContainerInput`，含 prompt、群组信息、是否主群等），然后执行 `container/agent-runner` 编译后的 Node 脚本；工作目录为 `/workspace/group`（挂载自 host 的 `groups/{channel}_{name}/`）。
- **挂载**：每个群组挂载（1）该群目录 `groups/{name}/` → `/workspace/group`；（2）该群会话目录 `data/sessions/{group}/.claude/` → `/home/node/.claude`（Agent 用其下的 skills、settings）；（3）该群 IPC 目录 → `/workspace/ipc`；（4）主群额外只读挂载项目根 → `/workspace/project`（且遮蔽 `.env`）。凭证不挂进容器，模型请求经 Host 代理发出。
- **Agent 运行**：容器内运行 Claude Agent SDK 的 `query()`，cwd 为 `/workspace/group`，可从 `/home/node/.claude` 读配置与 skills；支持的工具包括 Bash、Read/Write/Edit、Glob/Grep、WebSearch/WebFetch、Task、SendMessage、Skill、MCP（nanoclaw IPC）等；输出通过 stdout 以约定格式回传 Host。

**是否需要更新容器内的 Skills：**

- **不需要在「容器内部」单独更新**。容器内 Agent 使用的 skills 来自 **Host 上的 `container/skills/`**：每次为该群组**启动容器**时，Host 会先把 `container/skills/` 下的内容**同步**到该群的 `data/sessions/{group}/.claude/skills/`，再将该目录挂载为容器内的 `/home/node/.claude`。因此：
  - 在 **Host** 上增改 `container/skills/` 下的 skill 即可；**下一次**该群组有新消息或新任务触发起容器时，新容器就会带上最新 skills，**无需重建 Docker 镜像**。
  - 只有修改了 **Docker 镜像本身**（如 Dockerfile、`container/agent-runner` 源码、镜像内全局依赖）时才需要重新执行 `./container/build.sh` 构建镜像。
- **渠道相关 skills**（如 add-feishu）安装在项目根 `.claude/skills/`，用于 Host 侧「添加渠道」等操作，运行在 Host，不通过上述同步进容器；容器内用的是 `container/skills/` 里为 Agent 准备的工具型 skills（如 agent-browser）。

---

## 五、落地操作方式详细步骤

以下步骤均为**已验证**流程，按顺序执行即可复现。

### 5.1 环境与依赖

| 项目 | 要求 |
|------|------|
| 操作系统 | macOS 或 Linux（Windows 需 WSL2 + Docker） |
| Node.js | 20 及以上（建议 22） |
| Docker | 已安装且 Daemon 运行中 |
| Python | 3.9+（仅用于运行 DashScope 网关，若使用通义） |

检查命令：

```bash
node --version
docker info
```

### 5.2 克隆与进入项目

```bash
git clone https://github.com/<your-fork>/nanoclaw.git
cd nanoclaw
```

（若已 clone 官方仓库，可 `git remote add origin <your-fork>` 并保持 `upstream` 指向 qwibitai/nanoclaw。）

### 5.3 安装依赖与构建容器镜像

**方式 A：一键脚本（推荐）**

```bash
chmod +x scripts/install-docker.sh
./scripts/install-docker.sh
```

脚本将依次：检查 Node/Docker、`npm install`、`./container/build.sh`、容器自测、`npm run build`。**不会**自动填写 `.env` 或添加渠道。

**方式 B：手动执行**

```bash
npm install
./container/build.sh
# 自测镜像（可选）
echo '{}' | docker run -i --rm --entrypoint /bin/echo nanoclaw-agent:latest "Container OK"
npm run build
```

### 5.4 配置认证与国产模型（通义）

1. **启动 DashScope 网关**（使用虚拟环境 nanoclaw_env，端口 8005）：

   ```bash
   cd dashscope_gateway
   # 若未创建虚拟环境，先执行：
   # python3 -m venv nanoclaw_env && ./nanoclaw_env/bin/pip install -r requirements.txt
   ./run.sh
   ```

   保持该终端运行；本机可访问 <http://127.0.0.1:8005/health> 做健康检查。

2. **在 NanoClaw 项目根目录创建/编辑 `.env`**（**不要**设置 `CLAUDE_CODE_OAUTH_TOKEN`）：

   ```bash
   ANTHROPIC_BASE_URL=http://host.docker.internal:8005
   ANTHROPIC_API_KEY=<你的 DashScope API Key>
   ASSISTANT_NAME=Andy
   ```

3. **同步到容器用 env 文件**：

   ```bash
   mkdir -p data/env
   cp .env data/env/env
   ```

   之后每次修改 `.env` 中认证相关变量，都需重新执行 `cp .env data/env/env`。

### 5.5 添加飞书渠道

1. **应用飞书 Skill**（若仓库已含 add-feishu）：

   ```bash
   npx tsx scripts/apply-skill.ts .claude/skills/add-feishu
   npm run build
   ```

   若使用 Claude Code 交互方式，则在项目目录执行 `claude`，在对话中输入 `/add-feishu` 并按提示操作。

2. **飞书开放平台配置**（详见 [SETUP_FEISHU_ZH.md](../SETUP_FEISHU_ZH.md)）：

   - 创建应用，获取 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`。
   - 事件订阅：启用 **WebSocket 长连接**，添加 `im.message.receive_v1`。
   - 权限：`im:message:send_as_bot`、`im:message` 等（见文档）。
   - 将上述变量写入 `.env`。

3. **再次同步 env 并重启**：

   ```bash
   cp .env data/env/env
   npm run build
   ```

### 5.6 挂载白名单（可选）

若需 Agent 访问 host 上除项目外的目录，在 host 上配置（该文件**不会**挂入容器）：

```bash
mkdir -p ~/.config/nanoclaw
echo '{"allowedRoots":[],"blockedPatterns":[],"nonMainReadOnly":true}' > ~/.config/nanoclaw/mount-allowlist.json
```

保持 `allowedRoots` 为空则仅使用项目内 `groups/` 等默认挂载。

### 5.7 启动 NanoClaw 与自检

1. **前台启动（调试）**：

   ```bash
   npm run dev
   ```

2. **确认**：
   - 日志中无 “No channels connected”，且出现飞书等渠道连接成功信息。
   - 在飞书内对已注册群组或主频道发送触发词（如 `@Andy`），可获得助手回复。
   - 发送「我要请假」等审批相关语句时，助手会识别为 `approval-system` 技能并进入交互式参数收集（见下节）。

3. **后台运行（可选）**：
   - macOS：复制并编辑 `launchd/com.nanoclaw.plist` 中的 `{{PROJECT_ROOT}}`、`{{NODE_PATH}}`、`{{HOME}}`，再 `launchctl load ~/Library/LaunchAgents/com.nanoclaw.plist`。
   - Linux：`npx tsx setup/index.ts --step service`。

### 5.8 审批流程（我要请假）已验证行为

以下流程已在飞书群组中验证：用户发送「我要请假」后，助手按 `approval-system` 技能完成识别与参数收集，并可通过 Python 脚本提交（当前为模拟，配置 OA 后对接真实接口）。

1. **触发词识别**：用户发送「我要请假」等语句时，助手根据 `container/skills/approval-system/config.json` 中的 `triggers`（如「请假」「报销」「审批」等）识别为审批场景，并匹配审批类型为 `leave`（请假）。
2. **技能说明**：助手回复中会说明已检测到触发词、符合 `approval-system` 的 `triggers`，并声明将调用该技能、解析为 `type: "leave"`，以及后续会收集参数并调用 OA（或模拟提交）。
3. **交互式参数收集**：助手按 `config.json` 中 `approval_types.leave` 的 `params` / `required` 向用户收集：
   - 请假开始日期（格式 `YYYY-MM-DD`）
   - 请假结束日期（格式同上）
   - 请假原因（如年假、事假等）  
   用户可一次性回复，例如：`2026-03-20, 2026-03-22, 年假`。
4. **提交与执行**：收集到必填参数后，助手通过 Bash 调用容器内 Python 脚本，例如：
   `python /home/node/.claude/skills/approval-system/index.py --action submit --type leave --reason "年假" --days 3 [--start_date ... --end_date ...]`  
   脚本输出 JSON（含 `approval_id` 或模拟提示），助手将结果用自然语言反馈给用户。
5. **依赖**：容器镜像需已安装 Python（见当前 Dockerfile）；技能目录 `container/skills/approval-system/` 在每次起容器时由 Host 同步到该群 `.claude/skills/`，无需重建镜像即可使用。

### 5.9 参考文档（均已验证可依序执行）

| 文档 | 内容 |
|------|------|
| [INSTALL_DOCKER_ZH.md](../INSTALL_DOCKER_ZH.md) | 本机 Docker 安装、.env 配置、同步 data/env、运行方式、常见问题。 |
| [dashscope_gateway/README.md](../../dashscope_gateway/README.md) | 网关安装（nanoclaw_env）、启动（run.sh / 8005）、NanoClaw .env 配置、模型映射、故障排查。 |
| [SETUP_FEISHU_ZH.md](../SETUP_FEISHU_ZH.md) | 飞书应用创建、事件与权限、WebSocket、.env 变量、apply-skill 与 build。 |

---

## 六、已验证能力提纲汇总

本计划提纲仅包含以下已验证项：

1. **Docker 安装与容器镜像**：`scripts/install-docker.sh`、`./container/build.sh`、`npm run build`；详见 [INSTALL_DOCKER_ZH.md](../INSTALL_DOCKER_ZH.md)。
2. **国产模型（通义）**：DashScope 网关 `dashscope_gateway/`，虚拟环境 `nanoclaw_env`，端口 8005，`./run.sh`；NanoClaw `.env` 配置 `ANTHROPIC_BASE_URL`、`ANTHROPIC_API_KEY`；`data/env/env` 同步。
3. **飞书渠道**：add-feishu Skill（apply-skill 或 Claude Code `/add-feishu`），飞书开放平台 WebSocket 与权限配置；详见 [SETUP_FEISHU_ZH.md](../SETUP_FEISHU_ZH.md)。
4. **群组与记忆架构**：单 SQLite（`store/messages.db`）+ 按群目录（`groups/{name}/`）+ 按群会话（`data/sessions/{name}/`）；Docker 挂载 host 路径，数据落 host、重启不丢。
5. **审批流程 Skill（approval-system）**：容器内 Python 技能；`config.json` 中配置触发词（如「请假」「报销」）与审批类型及必填参数；用户发送「我要请假」后，助手识别触发词、声明调用技能、交互式收集 start_date/end_date/reason 等，并通过 `index.py` 提交（未配置 OA 时为模拟）；容器已支持 Python，技能随 `container/skills/` 同步进群组，无需重建镜像。

未写入本提纲的能力（待后续验证后再纳入）：意图识别增强、企业群组/权限同步、审计与 Token 监控、其他渠道（钉钉/Slack 等）的具体步骤。
