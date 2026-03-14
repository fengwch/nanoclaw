#!/usr/bin/env bash
# 使用虚拟环境 nanoclaw_env 启动 DashScope 网关（端口 8005）
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
if [ ! -d "nanoclaw_env" ]; then
  echo "未找到 nanoclaw_env，请先创建并安装依赖："
  echo "  python3 -m venv nanoclaw_env"
  echo "  ./nanoclaw_env/bin/pip install -r requirements.txt"
  exit 1
fi
exec ./nanoclaw_env/bin/uvicorn app:app --host 0.0.0.0 --port 8005
