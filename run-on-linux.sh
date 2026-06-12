#!/usr/bin/env bash
# 在 Linux 服务器上一键构建并运行
# 用法: chmod +x run-on-linux.sh && ./run-on-linux.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "======================================"
echo "  Douyin Spider - Linux 部署"
echo "======================================"

if command -v docker &>/dev/null; then
    echo "==> 检测到 Docker，使用 Docker 方式部署"
    if docker compose version &>/dev/null; then
        docker compose up -d --build
        echo ""
        echo "服务已启动。查看日志:"
        echo "  docker compose logs -f"
        docker compose logs --tail=20
    else
        docker build -t douyin-spider:latest .
        docker rm -f douyin-spider 2>/dev/null || true
        docker run -d --name douyin-spider --restart unless-stopped \
            -v "$ROOT/launcher_config.json:/app/launcher_config.json" \
            -e REDIS_HOST="${REDIS_HOST:-39.98.176.249}" \
            -e REDIS_PORT="${REDIS_PORT:-3521}" \
            -e REDIS_DB="${REDIS_DB:-2}" \
            -e REDIS_PASSWORD="${REDIS_PASSWORD:-}" \
            douyin-spider:latest
        echo ""
        echo "服务已启动。查看日志:"
        echo "  docker logs -f douyin-spider"
        docker logs --tail=20 douyin-spider
    fi
    exit 0
fi

echo "==> 未检测到 Docker，使用源码方式部署"
chmod +x scripts/*.sh 2>/dev/null || true
./scripts/install-linux.sh
echo ""
echo "==> 启动服务（前台运行，Ctrl+C 停止）"
exec ./scripts/run-linux.sh
