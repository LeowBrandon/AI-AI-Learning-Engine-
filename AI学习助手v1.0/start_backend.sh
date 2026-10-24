#!/usr/bin/env bash
# 启动后端（Flask API）：自动创建虚拟环境 → 安装依赖 → 启动服务，并打开前端页面。
#
# 用法：bash start_backend.sh   （或先 chmod +x 再 ./start_backend.sh）

set -e

cd "$(dirname "$0")/backend"

VENV_PY=".venv/bin/python"
PYTHON="${PYTHON:-python3}"

# ---------- 1. 虚拟环境 ----------
if [ -x "$VENV_PY" ]; then
  echo "[1/3] 虚拟环境已存在：backend/.venv"
else
  echo "[1/3] 创建虚拟环境 backend/.venv ..."

  if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo ""
    echo "  [错误] 找不到 $PYTHON。"
    echo "         请先安装 Python 3.10 以上版本（macOS 可用 brew install python3）。"
    echo "         下载：https://www.python.org/downloads/"
    echo ""
    exit 1
  fi

  "$PYTHON" -m venv .venv
fi

# ---------- 2. 依赖 ----------
echo "[2/3] 安装依赖（首次会比较慢）..."
"$VENV_PY" -m pip install --upgrade pip -q
"$VENV_PY" -m pip install -r requirements.txt -q

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo "  [注意] 已生成 backend/.env，但里面还没有填 LLM_API_KEY。"
  echo "         不填的话，聊天 / 出题 / 改卷 / 周报 会报错，其余功能正常。"
  echo "         填好后重新运行本脚本即可。"
  echo ""
fi

# ---------- 3. 启动 ----------
echo "[3/3] 启动后端：http://127.0.0.1:8765"
echo "      按 Ctrl+C 停止。"
echo ""

# 先把页面打开；右上角的圆点会在服务起来后自动变绿（页面每 8 秒重查一次）
APP="../frontend/index.html"
if [ -f "$APP" ]; then
  FULL="$(cd "$(dirname "$APP")" && pwd)/$(basename "$APP")"
  if command -v open >/dev/null 2>&1; then
    open "$FULL" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$FULL" >/dev/null 2>&1 || true
  fi
fi

exec "$VENV_PY" app.py
