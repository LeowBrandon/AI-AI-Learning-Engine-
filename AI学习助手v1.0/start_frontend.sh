#!/usr/bin/env bash
# 在默认浏览器里打开前端页面。
#
# 前端是纯静态的 HTML/CSS/JS，没有构建步骤，直接用 file:// 打开就行 ——
# 后端已经允许跨域，实测 file:// 页面能正常调接口，不需要再起一个静态文件服务。
#
# 用法：bash start_frontend.sh   （或先 chmod +x 再 ./start_frontend.sh）

set -e

cd "$(dirname "$0")"

APP="frontend/index.html"

if [ ! -f "$APP" ]; then
  echo "[错误] 找不到 $APP。"
  echo "       请把本脚本放在项目根目录（与 frontend、backend 同级）。"
  exit 1
fi

FULL="$(cd "$(dirname "$APP")" && pwd)/$(basename "$APP")"

echo "正在浏览器中打开："
echo "  $FULL"
echo ""

if command -v open >/dev/null 2>&1; then
  open "$FULL"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$FULL" >/dev/null 2>&1
else
  echo "没能自动打开浏览器，请手动打开上面这个文件。"
fi

echo "提示：后端要先启动，否则页面右上角的圆点是红的。"
echo "      先运行 bash start_backend.sh。"
