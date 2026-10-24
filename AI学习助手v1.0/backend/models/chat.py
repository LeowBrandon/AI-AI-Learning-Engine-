"""对话相关表：chat_sessions / chat_messages。"""

from datetime import datetime

from extensions import db
from models.base import BigIntPK


class ChatSession(db.Model):
    """一次对话会话。"""

    __tablename__ = 'chat_sessions'

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    title = db.Column(db.String(255), nullable=False)
    # 本次会话限定的资料范围；NULL 表示「全部资料」
    material_ids = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    messages = db.relationship(
        'ChatMessage',
        back_populates='session',
        cascade='all, delete-orphan',
        order_by='ChatMessage.id'
    )

    def __repr__(self):
        return '<ChatSession %s %s>' % (self.id, self.title)


class ChatMessage(db.Model):
    """会话里的一条消息。"""

    __tablename__ = 'chat_messages'

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    session_id = db.Column(
        db.BigInteger,
        db.ForeignKey('chat_sessions.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    role = db.Column(db.String(16), nullable=False)          # user / assistant
    content = db.Column(db.Text, nullable=False)
    # 助手消息引用的资料片段：[{material_id, material_name, chunk_index, snippet}]
    references = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    session = db.relationship('ChatSession', back_populates='messages')

    __table_args__ = (
        db.Index('ix_chat_messages_session_created', 'session_id', 'created_at'),
    )

    def __repr__(self):
        return '<ChatMessage %s %s>' % (self.id, self.role)
