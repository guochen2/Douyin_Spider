#!/usr/bin/env bash
# Linux 打包脚本
# 用法:
#   ./build-linux.sh docker   构建 Docker 镜像并导出 tar（默认）
#   ./build-linux.sh package  打包源码发布包（tar.gz，在 Linux 上解压后安装运行）
#   ./build-linux.sh all      同时执行 docker + package

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

IMAGE_NAME="${IMAGE_NAME:-douyin-spider:latest}"
DIST_DIR="$ROOT/dist"
RELEASE_NAME="douyin-spider-linux"
VERSION="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$DIST_DIR"

build_docker() {
    echo "==> 构建 Docker 镜像: $IMAGE_NAME"
    echo "    （node_modules 在镜像内 npm install，无需本地上传）"
    docker build -t "$IMAGE_NAME" .

    TAR_PATH="$DIST_DIR/${RELEASE_NAME}-docker-${VERSION}.tar"
    echo "==> 导出镜像: $TAR_PATH"
    docker save "$IMAGE_NAME" -o "$TAR_PATH"

    echo ""
    echo "Docker 镜像已导出。在 Linux 服务器上执行："
    echo "  docker load -i $(basename "$TAR_PATH")"
    echo "  docker run -d --name douyin-spider --restart unless-stopped \\"
    echo "    -v \$(pwd)/launcher_config.json:/app/launcher_config.json \\"
    echo "    -e REDIS_HOST=你的Redis地址 \\"
    echo "    -e REDIS_PORT=6379 \\"
    echo "    -e REDIS_DB=2 \\"
    echo "    -e REDIS_PASSWORD=你的密码 \\"
    echo "    $IMAGE_NAME"
}

build_package() {
    ARCHIVE="$DIST_DIR/${RELEASE_NAME}-source-${VERSION}.tar.gz"
    STAGING="$DIST_DIR/douyin-spider-linux"
    rm -rf "$STAGING"
    mkdir -p "$STAGING"

    echo "==> 准备发布文件"
    rsync -a \
        --exclude='.git' \
        --exclude='__pycache__' \
        --exclude='*.py[cod]' \
        --exclude='.venv' \
        --exclude='venv' \
        --exclude='node_modules' \
        --exclude='dist' \
        --exclude='build' \
        --exclude='*.exe' \
        --exclude='.env' \
        --exclude='.env*' \
        "$ROOT/" "$STAGING/" 2>/dev/null || {
        # 无 rsync 时用 cp
        cp -r "$ROOT/builder" "$ROOT/dy_apis" "$ROOT/dy_live" "$ROOT/static" "$ROOT/utils" "$ROOT/scripts" "$STAGING/"
        cp "$ROOT/launcher.py" "$ROOT/launcher_config.json" "$ROOT/Dockerfile" "$ROOT/docker-compose.yml" \
           "$ROOT/requirements-docker.txt" "$ROOT/build-linux.sh" "$ROOT/package.json" "$STAGING/" 2>/dev/null || true
        cp "$ROOT/package-lock.json" "$STAGING/" 2>/dev/null || true
    }

    echo "==> 打包: $ARCHIVE"
    tar -czf "$ARCHIVE" -C "$DIST_DIR" "douyin-spider-linux"
    rm -rf "$STAGING"

    echo ""
    echo "源码包已生成。在 Linux 服务器上执行："
    echo "  tar -xzf $(basename "$ARCHIVE")"
    echo "  cd douyin-spider-linux"
    echo "  chmod +x scripts/*.sh build-linux.sh"
    echo "  ./scripts/install-linux.sh"
    echo "  ./scripts/run-linux.sh"
}

pack_docker_source() {
    ARCHIVE="$DIST_DIR/douyin-spider-docker-src.tar.gz"
    echo "==> 打包 Docker 构建源码（不含 node_modules）: $ARCHIVE"

    tar -czf "$ARCHIVE" \
        --exclude='node_modules' \
        --exclude='static/node_modules' \
        --exclude='.git' \
        --exclude='__pycache__' \
        --exclude='.venv' \
        --exclude='venv' \
        --exclude='dist' \
        --exclude='build' \
        --exclude='*.exe' \
        --exclude='.env' \
        --exclude='.env*' \
        -C "$ROOT" \
        Dockerfile docker-compose.yml .dockerignore requirements-docker.txt package-docker.json \
        launcher.py launcher_config.json \
        build-linux.sh run-on-linux.sh \
        builder dy_apis dy_live static utils scripts

    if [[ -f "$ROOT/package-lock.json" ]]; then
        tar -rzf "$ARCHIVE" -C "$ROOT" package-lock.json
    fi

    echo ""
    echo "已生成（不含 node_modules）: $ARCHIVE"
    echo "上传到 Linux 后执行:"
    echo "  tar -xzf $(basename "$ARCHIVE")"
    echo "  docker compose up -d --build"
}

MODE="${1:-docker}"

case "$MODE" in
    docker)
        build_docker
        ;;
    src|source)
        pack_docker_source
        ;;
    package)
        build_package
        ;;
    all)
        build_docker
        build_package
        ;;
    *)
        echo "用法: $0 [docker|src|package|all]"
        echo "  docker  - 构建镜像并导出 tar"
        echo "  src     - 打包源码（不含 node_modules），供 Linux 上 docker compose build"
        exit 1
        ;;
esac

echo ""
echo "==> 完成"
