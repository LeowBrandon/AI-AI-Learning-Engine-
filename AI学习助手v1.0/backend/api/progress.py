"""进度接口（功能需求文档 D1~D4）。

全部由 answers / quizzes / materials / chat_messages 现算，不落库。
掌握等级口径见需求文档 4.x 节。
"""

from flask import Blueprint, jsonify

import stats
from extensions import db
from models import ChatMessage, Material

bp = Blueprint('progress', __name__)


@bp.get('/progress/overview')
def overview():
    """D1 总体概览。

    薄弱点个数不在这里返回 —— 前端从 D3 按同一口径自己数，
    这样卡片上的数字和下方列表永远一致。
    """
    return jsonify(stats.overview())


@bp.get('/progress/materials')
def materials_progress():
    """D2 按资料看进度（本版前端未使用）。"""
    per_material = stats.material_stats()
    learning_ids = _learning_material_ids()

    items = []
    for material in Material.query.order_by(Material.id).all():
        bucket = per_material.get(material.id)

        if bucket:
            state = 'quizzed'
            score_rate = bucket['score_rate']
        elif material.id in learning_ids:
            state = 'learning'
            score_rate = None
        else:
            state = 'not_started'
            score_rate = None

        items.append({
            'material_id': material.id,
            'name': material.name,
            'state': state,
            'score_rate': score_rate,
        })

    return jsonify({'items': items})


@bp.get('/progress/knowledge')
def knowledge_progress():
    """D3 知识点掌握情况。"""
    return jsonify({'items': stats.knowledge_stats()})


@bp.get('/progress/weak-points')
def weak_points():
    """D4 薄弱知识点（本版前端未使用）。"""
    return jsonify({'items': stats.weak_points()})


def _learning_material_ids():
    """被助手回答引用过的资料，视为「学习中」。

    引用记录存在 chat_messages.references 里（JSON 数组），
    在 Python 里扫一遍即可 —— 本机单用户的数据量很小。
    """
    ids = set()

    rows = (db.session.query(ChatMessage.references)
            .filter(ChatMessage.role == 'assistant')
            .filter(ChatMessage.references.isnot(None))
            .all())

    for (references,) in rows:
        if not isinstance(references, list):
            continue
        for item in references:
            if isinstance(item, dict) and item.get('material_id') is not None:
                try:
                    ids.add(int(item['material_id']))
                except (TypeError, ValueError):
                    continue

    return ids
