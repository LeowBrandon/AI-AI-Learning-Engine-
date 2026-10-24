"""配置。

所有可变项都从环境变量读，优先读 backend/.env（见 .env.example）。
大模型的地址、密钥、模型名三者互相独立，可分别替换成任意 OpenAI 兼容服务。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / 'instance'

load_dotenv(BASE_DIR / '.env')


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _float(name, default):
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class Config:
    # ---------- Flask ----------
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
    DEBUG = False

    # 监听端口。刻意不用 8000 —— 那个端口太常被别的程序占用
    # （本机上就被一个系统服务常驻占用，导致后端起不来）。
    # 改这里的话，前端 frontend/js/api.js 里的 BASE_URL 也要跟着改。
    PORT = _int('PORT', 8765)

    # 前端用 file:// 或其它端口打开页面，开发期默认放开跨域
    CORS_ORIGIN = os.environ.get('CORS_ORIGIN', '*')

    # ---------- 数据库 ----------
    # 默认 SQLite，放在 backend/instance/app.db；换成 PostgreSQL/MySQL 只改这一项
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'sqlite:///' + str(INSTANCE_DIR / 'app.db')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # 切片在后台线程里写，SQLite 需要放开线程检查
    SQLALCHEMY_ENGINE_OPTIONS = (
        {'connect_args': {'check_same_thread': False}}
        if SQLALCHEMY_DATABASE_URI.startswith('sqlite')
        else {}
    )

    # ---------- 上传 ----------
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', str(INSTANCE_DIR / 'uploads'))
    # 单文件上限。200 MB 够放课件级的 PDF / PPT。
    # 注意：前端的提示文案（frontend/index.html 的 dropzone__hint）写死了这个数字，
    # 改这里记得同步改那里。
    MAX_UPLOAD_MB = _int('MAX_UPLOAD_MB', 200)
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024
    # 真正能解析的格式。doc/ppt 这两个旧版二进制格式不在内，见 api/materials.py 的 LEGACY_HINTS
    ALLOWED_EXTENSIONS = {'pdf', 'pptx', 'docx', 'md', 'markdown', 'txt'}

    # ---------- 文字抽取 ----------
    # 切片长度（字符）。不用向量检索，切片只用于分块存储与拼接时按上限截断。
    CHUNK_SIZE = _int('CHUNK_SIZE', 1200)

    # ---------- 大模型（可单独配置） ----------
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_API_KEY = os.environ.get('LLM_API_KEY', '')
    LLM_MODEL = os.environ.get('LLM_MODEL', 'gpt-4o-mini')
    LLM_TIMEOUT = _int('LLM_TIMEOUT', 90)
    LLM_TEMPERATURE = _float('LLM_TEMPERATURE', 0.3)
    # 失败后最多再重试几次（总尝试次数 = 1 + 重试次数）。
    # 只对网络问题、5xx、429 重试；4xx 是请求本身有问题，重试没意义。
    #
    # 时间预算：最坏 4 次尝试 × LLM_TIMEOUT(90s) + 退避 ≈ 370 秒。
    # 前端对走大模型的请求给了 240 秒（见 frontend/js/api.js 的 LLM_TIMEOUT），
    # 正常情况和「失败一两次后成功」都够用；只有极端情况下才会在前端先超时。
    LLM_MAX_RETRIES = _int('LLM_MAX_RETRIES', 3)
    # 重试间隔基数（秒），实际等待 = 基数 × 第几次，做简单的退避
    LLM_RETRY_DELAY = _float('LLM_RETRY_DELAY', 1.5)

    # 不用向量检索：直接把选中资料的正文拼进提示词，这里是单次请求的字符上限
    MATERIAL_CONTEXT_LIMIT = _int('MATERIAL_CONTEXT_LIMIT', 24000)


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


CONFIGS = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}

# 用 APP_ENV 而不是 FLASK_ENV：后者在 Flask 2.3 起已废弃，容易误解
ENV_VAR = 'APP_ENV'


def get_config(name=None):
    return CONFIGS.get(name or os.environ.get(ENV_VAR, 'default'), DevelopmentConfig)
