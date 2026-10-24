"""对话接口（功能需求文档 B1~B3）。

不用向量检索：先从所选资料里按关键词挑出相关段落，
再把段落和问题一起交给大模型，让它基于这些内容回答。
"""

from datetime import datetime

from flask import Blueprint, current_app, jsonify, request

import context as ctx
from api.common import error
from extensions import db
from llm import LLMError, chat
from models import ChatMessage, ChatSession
from prompts import learner_system

bp = Blueprint('chat', __name__)

# 带多少条历史消息进提示词
HISTORY_LIMIT = 10
# 会话标题取首个问题的前若干字
TITLE_LENGTH = 24


@bp.post('/chat')
def ask():
    """B1 提问。"""
    payload = request.get_json(silent=True) or {}
    question = (payload.get('question') or '').strip()
    if not question:
        return error('BAD_REQUEST', '请求体缺少 question 字段', 400)

    session = _resolve_session(payload)
    material_ids = _resolve_material_ids(payload, session)

    materials = ctx.load_materials(material_ids)
    if material_ids and not materials:
        return error('NO_MATERIAL', '所选资料不存在或尚未解析完成', 400)

    pairs = ctx.select_relevant(
        materials, question, current_app.config['MATERIAL_CONTEXT_LIMIT'])

    try:
        answer = chat(_build_messages(session, question, pairs))
    except LLMError as exc:
        return error('LLM_FAILED', str(exc), 502)

    references = ctx.build_references(pairs)
    _save_messages(session, question, answer, references)

    return jsonify({
        'session_id': session.id,
        'answer': answer,
        'references': references,
        'no_reference': len(references) == 0,
        'created_at': datetime.now().isoformat(),
    })


@bp.post('/chat/sessions')
def create_session():
    """B0 创建对话。

    前端目前用的是「懒创建」：点新对话只清空界面，第一次发消息时由 B1 顺手建会话。
    这样历史列表里不会堆一串空的「新对话」。这个接口留给需要显式建会话的场景。
    """
    payload = request.get_json(silent=True) or {}

    material_ids = payload.get('material_ids') or None
    title = (payload.get('title') or '').strip() or '新对话'

    session = ChatSession(title=title[:TITLE_LENGTH], material_ids=material_ids)
    db.session.add(session)
    db.session.commit()

    return jsonify(_serialize_session(session)), 201


@bp.get('/chat/sessions')
def list_sessions():
    """B2 会话列表。"""
    sessions = ChatSession.query.order_by(
        ChatSession.created_at.desc(), ChatSession.id.desc()).all()

    return jsonify({'items': [_serialize_session(session) for session in sessions]})


@bp.get('/chat/sessions/<int:session_id>')
def get_session(session_id):
    """B3 会话消息。"""
    session = db.session.get(ChatSession, session_id)
    if session is None:
        return error('NOT_FOUND', '会话不存在', 404)

    return jsonify({
        'session_id': session.id,
        'messages': [{
            'role': message.role,
            'content': message.content,
            'references': message.references or [],
            'created_at': message.created_at.isoformat() if message.created_at else None,
        } for message in session.messages],
    })


@bp.delete('/chat/sessions/<int:session_id>')
def delete_session(session_id):
    """B4 删除对话。会话连同里面的消息一起删掉（关系上配了 cascade）。"""
    session = db.session.get(ChatSession, session_id)
    if session is None:
        return error('NOT_FOUND', '会话不存在', 404)

    message_count = len(session.messages)

    db.session.delete(session)
    db.session.commit()

    return jsonify({'deleted': True, 'id': session_id, 'message_count': message_count})


# ---------- 内部 ----------

def _serialize_session(session):
    return {
        'id': session.id,
        'title': session.title,
        'material_ids': session.material_ids or [],
        'created_at': session.created_at.isoformat() if session.created_at else None,
    }

def _resolve_session(payload):
    """有 session_id 就接着聊，没有或找不到就新建。"""
    session_id = payload.get('session_id')
    if session_id:
        session = db.session.get(ChatSession, session_id)
        if session is not None:
            return session
        # 前端可能拿着已删除的 id，静默新建比报错友好

    session = ChatSession(
        title='新对话',
        material_ids=payload.get('material_ids') or None,
    )
    db.session.add(session)
    db.session.commit()
    return session


def _resolve_material_ids(payload, session):
    """本次提问的资料范围：请求里带了就用请求的，否则沿用会话建立时的范围。"""
    ids = payload.get('material_ids')
    if ids:
        return ids
    if session.material_ids:
        return session.material_ids
    return None


def _build_messages(session, question, pairs):
    """system 放角色规则 + 参考资料，历史对话按序跟上，最后是本次问题。"""
    messages = [{
        'role': 'system',
        'content': learner_system(ctx.format_context(pairs)),
    }]

    history = (ChatMessage.query
               .filter_by(session_id=session.id)
               .order_by(ChatMessage.id.desc())
               .limit(HISTORY_LIMIT)
               .all())

    for message in reversed(history):
        messages.append({'role': message.role, 'content': message.content})

    messages.append({'role': 'user', 'content': question})
    return messages


def _save_messages(session, question, answer, references):
    if not session.title or session.title == '新对话':
        session.title = question[:TITLE_LENGTH]

    db.session.add(ChatMessage(session_id=session.id, role='user', content=question))
    db.session.add(ChatMessage(
        session_id=session.id,
        role='assistant',
        content=answer,
        references=references,
    ))
    db.session.commit()
