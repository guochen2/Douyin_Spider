#!/usr/bin/env bash
# 启动 Redis 监听服务
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV_DIR="$ROOT/.venv"
if [[ ! -d "$VENV_DIR" ]]; then
    echo "未找到虚拟环境，请先执行: ./scripts/install-linux.sh"
    exit 1
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
export RUN_IN_FOREGROUND=1

exec python launcher.py
