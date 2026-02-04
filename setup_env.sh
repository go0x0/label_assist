#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -d ".venv" ]]; then
  echo ".venv 已存在，使用已有虚拟环境。"
else
  echo "创建虚拟环境 .venv..."
  python3 -m venv .venv
fi

# 激活并安装依赖
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "虚拟环境已准备好：.venv"