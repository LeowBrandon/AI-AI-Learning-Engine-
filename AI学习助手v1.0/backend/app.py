"""应用入口。

启动：
    cd backend
    python app.py            # 默认 http://127.0.0.1:8765

建表：
    python scripts/init_db.py
"""

from pathlib import Path

from flask import Flask, jsonify, request

import models  # noqa: F401  导入即把所有模型注册到 metadata
from api import register_blueprints
from config import get_config
from extensions import db


def create_app(config_name=None):
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    # 中文不转义成 \uXXXX
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    db.init_app(app)

    Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True, exist_ok=True)

    register_blueprints(app)
    _register_error_handlers(app)
    _register_cors(app)

    return app


def _register_error_handlers(app):
    """统一错误体，前端只认 { error: { code, message } } 这一种形状。"""

    @app.errorhandler(404)
    def _not_found(_e):
        return jsonify({'error': {'code': 'NOT_FOUND', 'message': '接口不存在'}}), 404

    @app.errorhandler(405)
    def _method_not_allowed(_e):
        return jsonify({'error': {'code': 'METHOD_NOT_ALLOWED', 'message': '请求方法不允许'}}), 405

    @app.errorhandler(413)
    def _too_large(_e):
        limit_mb = app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)
        return jsonify({'error': {
            'code': 'FILE_TOO_LARGE',
            'message': '文件超过 %d MB 上限' % limit_mb
        }}), 413

    @app.errorhandler(500)
    def _server_error(_e):
        db.session.rollback()
        return jsonify({'error': {'code': 'INTERNAL_ERROR', 'message': '服务内部错误'}}), 500


def _register_cors(app):
    """前端用 file:// 或其它端口打开页面，开发期放开跨域。

    生产环境把 CORS_ORIGIN 收窄成具体域名。
    """

    @app.after_request
    def _add_cors_headers(resp):
        resp.headers['Access-Control-Allow-Origin'] = app.config['CORS_ORIGIN']
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        resp.headers['Access-Control-Max-Age'] = '600'
        return resp


app = create_app()


if __name__ == '__main__':
    # threaded=True 是必须的：出题 / 改卷 / 周报都要等大模型返回，可能几十秒。
    # 单线程的话，这期间前端的状态点轮询会被阻塞，看起来像「后端挂了」。
    app.run(
        host='127.0.0.1',
        port=app.config['PORT'],
        debug=app.config['DEBUG'],
        threaded=True,
    )
