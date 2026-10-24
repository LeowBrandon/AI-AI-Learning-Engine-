"""系统接口：健康检查。

前端顶栏的连接状态点轮询这个接口，能拿到 200 就亮绿灯。
"""

from flask import Blueprint, jsonify

bp = Blueprint('system', __name__)


@bp.get('/health')
def health():
    return jsonify({'status': 'ok'})
