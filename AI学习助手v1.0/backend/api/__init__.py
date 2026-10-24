"""接口包。

所有蓝图统一挂在 /api 前缀下，与前端 api.js 里的 BASE_URL 对应。
"""

from api.chat import bp as chat_bp
from api.materials import bp as materials_bp
from api.progress import bp as progress_bp
from api.quizzes import bp as quizzes_bp
from api.reports import bp as reports_bp
from api.system import bp as system_bp

API_PREFIX = '/api'

BLUEPRINTS = (
    system_bp,
    materials_bp,
    chat_bp,
    quizzes_bp,
    progress_bp,
    reports_bp,
)


def register_blueprints(app):
    for bp in BLUEPRINTS:
        app.register_blueprint(bp, url_prefix=API_PREFIX)
