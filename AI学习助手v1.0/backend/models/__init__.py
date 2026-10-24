"""模型包。

导入本包即把所有模型注册到 SQLAlchemy 的 metadata，
`db.create_all()` 才能看到它们。app.py 里只需 `import models`。
"""

from models.chat import ChatMessage, ChatSession
from models.material import Material, MaterialChunk
from models.quiz import Answer, Question, Quiz
from models.report import Report

__all__ = [
    'Material',
    'MaterialChunk',
    'ChatSession',
    'ChatMessage',
    'Quiz',
    'Question',
    'Answer',
    'Report',
]
