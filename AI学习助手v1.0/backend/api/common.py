"""蓝图共用的响应工具。

统一错误体，与《功能需求文档.md》约定一致：
    { "error": { "code": "XXX", "message": "人话描述" } }
"""

from flask import jsonify


def error(code, message, status):
    return jsonify({'error': {'code': code, 'message': message}}), status
