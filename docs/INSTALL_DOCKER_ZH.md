# NanoClaw 本机 Docker 安装指南

在本地使用 **Docker** 作为 Agent 容器运行时，完成 NanoClaw 的安装与运行。

## 前置要求

- **操作系统**：macOS 或 Linux
- **Node.js**：20 及以上（建议 22）
- **Docker**：已安装且 Daemon 处于运行状态
- **Claude 认证**：Claude 订阅 Token 或 Anthropic API Key（二选一）；若使用**国内模型**，见下文「使用国内模型（DashScope 网关）」。

## 一、安装步骤

### 1. 克隆/进入项目目录

```bash
cd /path/to/nanoclaw
```

### 2. 安装 Node 依赖

```bash
npm install
```

若存在 `package-lock.json` 且希望严格一致，可使用：

```bash
npm ci
```

### 3. 确认 Docker 已运行

```bash
docker info
```

若报错，请先启动 Docker：

- **macOS**：打开 Docker Desktop，或 `open -a Docker`
- **Linux**：`sudo systemctl start docker`

### 4. 构建 Agent 容器镜像

在项目根目录执行：

```bash
./container/build.sh
```

或指定 tag：

```bash
CONTAINER_RUNTIME=docker ./container/build.sh
```

镜像名为 `nanoclaw-agent:latest`。构建完成后可用下面命令自测：

```bash
echo '{}' | docker run -i --rm --entrypoint /bin/echo nanoclaw-agent:latest "Container OK"
```

若输出 `Container OK` 即表示镜像正常。

### 5. 编译 Host 端 TypeScript

```bash
npm run build
```

### 6. 配置 Claude 认证（.env）

在项目根目录创建 `.env` 文件，并填入以下**二选一**：

**方式 A：Claude 订阅（OAuth Token）**

```bash
# 在终端执行 claude setup-token 获取 Token，再写入 .env
CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-...
```

**方式 B：Anthropic API Key（按量计费）**

```bash
ANTHROPIC_API_KEY=sk-ant-api03-...
```

可选配置：

```bash
# 助手触发词，默认 @Andy
ASSISTANT_NAME=Andy
```

### 7. 同步认证到容器用 env 文件

Host 只会把认证相关变量写入 `data/env/env` 供容器挂载，需先创建并同步：

```bash
mkdir -p data/env
cp .env data/env/env
```

后续若修改 `.env` 中的 `CLAUDE_CODE_OAUTH_TOKEN` 或 `ANTHROPIC_API_KEY`，需重新执行：

```bash
cp .env data/env/env
```

### 8. 初始化挂载白名单（可选）

若希望 Agent 能访问本机其他目录，需在宿主机配置白名单（容器不会挂载该文件）：

```bash
mkdir -p ~/.config/nanoclaw
# 空白名单表示不允许额外挂载
echo '{"allowedRoots":[],"blockedPatterns":[],"nonMainReadOnly":true}' > ~/.config/nanoclaw/mount-allowlist.json
```

保持空数组即仅使用项目内 `groups/` 等默认挂载。

---

## 二、运行方式

### 前台运行（调试）

```bash
npm run dev
```

或：

```bash
node dist/index.js
```

看到日志且无报错即表示 Host 已启动。此时**尚未配置任何消息渠道**，不会收到消息；需要先添加渠道（见下文）。

### 后台服务（推荐）

- **macOS**：使用 launchd  
  ```bash
  cp launchd/com.nanoclaw.plist ~/Library/LaunchAgents/
  # 编辑 plist 中的 {{PROJECT_ROOT}}、{{NODE_PATH}}、{{HOME}}
  launchctl load ~/Library/LaunchAgents/com.nanoclaw.plist
  ```
- **Linux**：使用项目提供的 setup 步骤安装 systemd 用户服务  
  ```bash
  npx tsx setup/index.ts --step service
  ```

---

## 三、添加消息渠道（WhatsApp / Telegram / Slack / Discord）

NanoClaw 核心**不内置**任何渠道，需通过 **Claude Code skills** 按需添加：

1. 在项目目录启动 Claude Code：`claude`
2. 在对话中执行对应技能，例如：
   - `/add-whatsapp` — WhatsApp（扫码或配对码认证）
   - `/add-telegram` — Telegram（Bot Token）
   - `/add-slack` — Slack（Socket Mode）
   - `/add-discord` — Discord（Bot Token）

每个技能会引导你完成：写入 `.env`、认证、注册主群组等。添加渠道后需：

```bash
cp .env data/env/env
npm run build
# 若已用服务运行，需重启服务
```

---

## 四、一键安装脚本（仅完成到“可运行 Host + Docker 镜像”）

项目根目录下的 `scripts/install-docker.sh` 可自动执行：依赖安装、Docker 检查、镜像构建、TypeScript 编译。**不会**替你填写 `.env` 或添加渠道，认证与渠道仍需按上面步骤手动完成。

使用方式：

```bash
chmod +x scripts/install-docker.sh
./scripts/install-docker.sh
```

完成后请自行完成「6. 配置 .env」「7. 同步 data/env/env」及（可选）「添加渠道 + 后台服务」。

---

## 五、使用国内模型（DashScope 网关）

若不使用 Claude 官方 API，可改用 **阿里云 DashScope（通义千问）**：项目内提供 Python 网关，将 Anthropic 格式请求转为 DashScope 调用。

1. **安装并启动网关**（在 NanoClaw 仓库下的 `dashscope_gateway` 目录）：
   ```bash
   cd dashscope_gateway
   pip install -r requirements.txt
   uvicorn app:app --host 0.0.0.0 --port 8005
   ```
2. **NanoClaw 的 `.env`** 中配置（不要设置 `CLAUDE_CODE_OAUTH_TOKEN`）：
   ```bash
   ANTHROPIC_BASE_URL=http://host.docker.internal:8005
   ANTHROPIC_API_KEY=<你的 DashScope API Key>
   ```
3. 执行 `cp .env data/env/env`，然后启动 NanoClaw（`npm run dev`）。  
容器内请求会经 Host 的 credential proxy 转发到本机 8005 端口的网关，由网关调用 DashScope 并返回 Anthropic 格式。

详细说明、模型映射与故障排查见 [dashscope_gateway/README.md](../dashscope_gateway/README.md)。

---

## 六、常见问题

| 现象 | 处理 |
|------|------|
| `docker info` 报错 | 启动 Docker Desktop（macOS）或 `sudo systemctl start docker`（Linux）。 |
| `Cannot connect to the Docker daemon` | Linux 下当前用户可能不在 `docker` 组：`sudo usermod -aG docker $USER`，然后重新登录或 `newgrp docker`。 |
| 容器内 Agent 报认证错误 | 确认 `.env` 中已填 `CLAUDE_CODE_OAUTH_TOKEN` 或 `ANTHROPIC_API_KEY`，并已执行 `cp .env data/env/env`。 |
| 没有收到消息 | 核心默认无渠道，需在 Claude Code 中运行 `/add-whatsapp` 等技能添加至少一个渠道并完成认证与主群组注册。 |

---

## 七、参考

- 完整架构与配置：[docs/SPEC.md](SPEC.md)
- 安全模型：[docs/SECURITY.md](SECURITY.md)
- 官方快速开始（英文）：[README.md](../README.md)
