#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -d ".venv" ]]; then
  echo "未找到 .venv，请先创建虚拟环境并安装依赖"
  exit 1
fi

source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

pyinstaller \
  --name LabelAssist \
  --onefile \
  --windowed \
  main.py

echo "打包完成：dist/LabelAssist"
