# DashScope 网关（NanoClaw 用）

将 **Anthropic Messages API** 格式的请求转发到 **阿里云 DashScope（通义千问）**，并把响应转回 Anthropic 格式，使 NanoClaw 容器内的 Claude Agent SDK 可以无感使用通义模型。

## 环境要求

- Python 3.10+
- 阿里云 DashScope API Key（[控制台](https://dashscope.console.aliyun.com/) 创建）

## 安装

推荐使用项目自带的虚拟环境 **nanoclaw_env**：

```bash
cd dashscope_gateway
python3 -m venv nanoclaw_env
./nanoclaw_env/bin/pip install -r requirements.txt
```

或本机全局安装：

```bash
cd dashscope_gateway
pip install -r requirements.txt
```

## 配置

网关通过 **环境变量** 或 **NanoClaw 注入的请求头** 获取 DashScope API Key：

| 方式 | 说明 |
|------|------|
| 请求头 `x-api-key` | NanoClaw 的 credential proxy 会把 `.env` 里的 `ANTHROPIC_API_KEY` 注入到发往网关的请求中，**推荐**：在 NanoClaw 的 `.env` 里设 `ANTHROPIC_API_KEY=<你的 DashScope Key>` |
| 环境变量 `DASHSCOPE_API_KEY` | 本机直接调试网关时可用 |

可选环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DASHSCOPE_BASE` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | DashScope 兼容模式 base URL |
| `DASHSCOPE_MODEL` | `qwen-plus` | 当 Anthropic 模型名未映射时使用的默认通义模型 |

## 启动网关

**方式一：使用虚拟环境 nanoclaw_env（推荐）**

```bash
cd dashscope_gateway
./run.sh
```

或手动激活后启动：

```bash
cd dashscope_gateway
source nanoclaw_env/bin/activate   # Windows: nanoclaw_env\Scripts\activate
uvicorn app:app --host 0.0.0.0 --port 8005
```

**方式二：直接使用 uvicorn**

```bash
cd dashscope_gateway
uvicorn app:app --host 0.0.0.0 --port 8005
```

- 本机访问：<http://127.0.0.1:8005/health>
- 容器内通过 Host 访问时需用 `host.docker.internal:8005`（Docker Desktop 默认支持）

## NanoClaw 侧配置

在 **NanoClaw 项目根目录** 的 `.env` 中设置：

```bash
# 指向本机网关（容器内通过 host.docker.internal 访问宿主机）
ANTHROPIC_BASE_URL=http://host.docker.internal:8005
# 填你的 DashScope API Key（NanoClaw 会把它注入到请求头，网关用其调 DashScope）
ANTHROPIC_API_KEY=sk-xxxxxxxxxxxxxxxx
```

然后同步到容器用 env 文件：

```bash
mkdir -p data/env
cp .env data/env/env
```

**注意**：不要同时设置 `CLAUDE_CODE_OAUTH_TOKEN`，否则 NanoClaw 会走 OAuth 模式而不是 API Key，网关收不到 Key。

启动 NanoClaw 前请先启动本网关（`uvicorn app:app --host 0.0.0.0 --port 8005`），再运行 `npm run dev`。

## 模型映射

Anthropic 模型名会映射到 DashScope 模型，默认对应关系：

| Anthropic 模型 | DashScope 模型 |
|----------------|----------------|
| claude-3-5-sonnet-20241022 | qwen-plus |
| claude-3-opus-20240229 | qwen-max |
| claude-3-sonnet-20240229 | qwen-plus |
| claude-3-haiku-20240307 | qwen-turbo |
| 其他 | 由 `DASHSCOPE_MODEL` 决定（默认 qwen-plus） |

可在 `app.py` 的 `MODEL_MAP` 中修改或扩展。

## 健康检查

```bash
curl http://127.0.0.1:8005/health
# 期望: {"status":"ok","gateway":"dashscope"}
```

## 故障排查

- **401 missing x-api-key**：NanoClaw 的 `.env` 未设置 `ANTHROPIC_API_KEY`，或未执行 `cp .env data/env/env`，或 credential proxy 未注入。
- **502 / 连接失败**：容器内无法访问宿主机网关。确认网关监听 `0.0.0.0:8005`，且 Docker 可访问 `host.docker.internal`（Linux 需在 run 时加 `--add-host=host.docker.internal:host-gateway`）。
- **DashScope 返回 4xx**：检查 API Key 是否有效、是否开通对应模型、请求体是否被网关正确转换。
