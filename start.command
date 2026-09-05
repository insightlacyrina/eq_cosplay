#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Kill any existing lingering process
pkill -f "EQCosplayApp" 2>/dev/null || true

# Preflight: Check if built app exists, or if an auto-build is needed on a new Mac
if [ ! -d "$DIR/dist/EQ Cosplay.app" ]; then
    echo "=========================================================="
    echo "  首次运行检测：未发现已打包的 EQ Cosplay.app"
    echo "  正在执行依赖自检与原生 Release 打包..."
    echo "=========================================================="
    
    if ! command -v swift >/dev/null 2>&1; then
        echo "❌ 错误: 未检测到 Swift 编译环境 (Xcode / Command Line Tools)。"
        echo "   请先在终端运行 'xcode-select --install' 安装命令行工具后再启动。"
        read -n 1 -s -r -p "按任意键退出..."
        exit 1
    fi
    
    chmod +x "$DIR/build_app.sh"
    "$DIR/build_app.sh"
fi

# Remove quarantine attribute if present
xattr -dr com.apple.quarantine "$DIR/dist/EQ Cosplay.app" 2>/dev/null || true

echo "正在启动 EQ Cosplay (Swift 原生版)..."
open "$DIR/dist/EQ Cosplay.app"
