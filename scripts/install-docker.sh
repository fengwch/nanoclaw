#!/usr/bin/env bash
# NanoClaw 本机 Docker 安装脚本
# 执行：依赖安装、Docker 检查、Agent 镜像构建、Host 编译。
# 不会填写 .env 或添加消息渠道，需按 docs/INSTALL_DOCKER_ZH.md 完成认证与渠道配置。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "=== NanoClaw 本机 Docker 安装 ==="
echo "项目目录: $PROJECT_ROOT"
echo ""

# 1. Node.js 版本
if ! command -v node &>/dev/null; then
  echo "错误: 未找到 node。请安装 Node.js 20+。"
  exit 2
fi
NODE_VER=$(node -p "process.versions.node")
NODE_MAJOR=$(node -p "process.versions.node.split('.')[0]")
if [ "$NODE_MAJOR" -lt 20 ] 2>/dev/null; then
  echo "错误: Node.js 版本需 >= 20，当前: $NODE_VER"
  exit 2
fi
echo "✓ Node.js $NODE_VER"

# 2. Docker 可用且 daemon 运行
if ! command -v docker &>/dev/null; then
  echo "错误: 未找到 docker。请先安装 Docker 并启动 Docker Desktop / daemon。"
  exit 2
fi
if ! docker info &>/dev/null; then
  echo "错误: Docker daemon 未运行。请启动 Docker（macOS: 打开 Docker Desktop，Linux: sudo systemctl start docker）。"
  exit 2
fi
echo "✓ Docker 已就绪"

# 3. 安装依赖
echo ""
echo ">>> npm install ..."
npm install
echo "✓ 依赖安装完成"

# 4. 构建 Agent 容器镜像
echo ""
echo ">>> 构建 Agent 容器镜像 (nanoclaw-agent:latest) ..."
if [ -x "./container/build.sh" ]; then
  ./container/build.sh
else
  docker build -t nanoclaw-agent:latest ./container
fi
echo "✓ 镜像构建完成"

# 5. 测试镜像
if echo '{}' | docker run -i --rm --entrypoint /bin/echo nanoclaw-agent:latest "Container OK" 2>/dev/null | grep -q "Container OK"; then
  echo "✓ 容器自测通过"
else
  echo "警告: 容器自测未通过，请检查镜像。继续执行 Host 编译。"
fi

# 6. 编译 Host
echo ""
echo ">>> npm run build ..."
npm run build
echo "✓ Host 编译完成"

# 7. 提示 .env 与 data/env
echo ""
mkdir -p data/env
if [ ! -f .env ]; then
  echo "请创建 .env 并填入 Claude 认证（二选一）："
  echo "  CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-..."
  echo "  ANTHROPIC_API_KEY=sk-ant-api03-..."
  echo "然后执行: cp .env data/env/env"
else
  if [ ! -f data/env/env ] || [ .env -nt data/env/env ]; then
    echo "请执行以下命令，将认证同步到容器："
    echo "  cp .env data/env/env"
  else
    echo "✓ .env 已同步到 data/env/env"
  fi
fi

echo ""
echo "=== 安装步骤完成 ==="
echo "添加消息渠道请在项目目录运行: claude  然后执行 /add-whatsapp 或 /add-telegram 等。"
echo "前台运行: npm run dev"
echo "详细说明: docs/INSTALL_DOCKER_ZH.md"
