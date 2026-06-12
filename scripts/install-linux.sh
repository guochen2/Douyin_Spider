#!/usr/bin/env bash
# 在 Linux 服务器上安装运行环境（Python 3.10 + Node.js）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3.10}"
VENV_DIR="$ROOT/.venv"

echo "==> 检查 Python 3.10"
if ! command -v "$PYTHON" &>/dev/null; then
    echo "错误: 未找到 $PYTHON，请先安装 Python 3.10"
    echo "  Ubuntu/Debian: sudo apt install python3.10 python3.10-venv"
    exit 1
fi

PY_VERSION="$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "$PY_VERSION" != "3.10" ]]; then
    echo "警告: 当前 Python 版本为 $PY_VERSION，建议使用 3.10"
fi

echo "==> 检查 Node.js"
if ! command -v node &>/dev/null; then
    echo "错误: 未找到 node，请先安装 Node.js 18+"
    echo "  参考: https://nodejs.org/ 或 nvm install 20"
    exit 1
fi

echo "==> 创建虚拟环境: $VENV_DIR"
"$PYTHON" -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "==> 安装 Python 依赖"
pip install --upgrade pip
pip install -r requirements-docker.txt

echo "==> 安装 Node.js 依赖"
if [[ -f package-lock.json ]]; then
    npm ci --omit=dev
else
    npm install --omit=dev
fi

if [[ ! -f launcher_config.json ]]; then
    echo '{"redis_control_channel": "dy_live:control"}' > launcher_config.json
    echo "已创建默认 launcher_config.json"
fi

echo ""
echo "安装完成。启动服务："
echo "  ./scripts/run-linux.sh"
