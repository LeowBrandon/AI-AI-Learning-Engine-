"""学习数据的统计聚合。

全部由 answers / quizzes / materials / chat_messages 现算，不落库。
周报用这里的区间统计；进度页也用同一套口径。
"""

from datetime import datetime, time, timedelta

from sqlalchemy import Float, case, cast, func

from extensions import db
from models import Answer, ChatMessage, Material, Question, Quiz

# 得分率低于这个值算薄弱（与需求文档 4.x 节的「掌握等级口径」一致）
WEAK_THRESHOLD = 0.7

# 一份资料关联的知识点全部达到这个得分率，才算「已掌握」
MASTER_THRESHOLD = 0.7


def _day_start(day):
    return datetime.combine(day, time.min)


def _day_after(day):
    """右开区间上界：结束日期当天的内容也要算进去，所以取次日零点。"""
    return datetime.combine(day + timedelta(days=1), time.min)


def knowledge_stats(start=None, end=None):
    """按知识点汇总作答情况。

    score_rate = 该知识点下所有作答的得分之和 ÷ 满分之和，
    所以简答题得 0.5 分会被如实反映，而不是按「对/错」二值处理。
    """
    query = (
        db.session.query(
            Question.knowledge_point.label('knowledge_point'),
            func.count(Answer.id).label('total'),
            func.sum(case((Answer.is_correct.is_(True), 1), else_=0)).label('correct'),
            func.sum(cast(Answer.score, Float)).label('earned'),
            func.sum(cast(Question.full_score, Float)).label('full'),
        )
        .select_from(Answer)
        .join(Question, Question.id == Answer.question_id)
        .join(Quiz, Quiz.id == Answer.quiz_id)
        .filter(Quiz.status == 'submitted')
    )

    if start:
        query = query.filter(Quiz.submitted_at >= _day_start(start))
    if end:
        query = query.filter(Quiz.submitted_at < _day_after(end))

    rows = query.group_by(Question.knowledge_point).all()

    result = []
    for row in rows:
        full = float(row.full or 0)
        earned = float(row.earned or 0)
        result.append({
            'knowledge_point': row.knowledge_point,
            'total': int(row.total or 0),
            'correct': int(row.correct or 0),
            'score_rate': round(earned / full, 4) if full > 0 else 0.0,
        })

    return sorted(result, key=lambda item: (item['score_rate'], item['knowledge_point']))


def weak_points(start=None, end=None, threshold=WEAK_THRESHOLD):
    """得分率低于阈值的知识点，按低到高排序。"""
    return [item for item in knowledge_stats(start, end) if item['score_rate'] < threshold]


def material_stats():
    """按资料汇总作答情况，用于「已掌握几份」与 D2。

    「已掌握」= 该资料关联的知识点**全部**达到 MASTER_THRESHOLD。
    等价的说法是：这份资料没有薄弱知识点。
    还没被测评过的资料不出现在结果里。
    """
    rows = (
        db.session.query(
            Question.material_id.label('material_id'),
            Question.knowledge_point.label('knowledge_point'),
            func.count(Answer.id).label('total'),
            func.sum(case((Answer.is_correct.is_(True), 1), else_=0)).label('correct'),
            func.sum(cast(Answer.score, Float)).label('earned'),
            func.sum(cast(Question.full_score, Float)).label('full'),
        )
        .select_from(Answer)
        .join(Question, Question.id == Answer.question_id)
        .join(Quiz, Quiz.id == Answer.quiz_id)
        .filter(Quiz.status == 'submitted')
        .filter(Question.material_id.isnot(None))
        .group_by(Question.material_id, Question.knowledge_point)
    ).all()

    result = {}
    for row in rows:
        bucket = result.setdefault(row.material_id, {
            'answered': 0, 'correct': 0, 'earned': 0.0, 'full': 0.0, 'points': [],
        })
        bucket['answered'] += int(row.total or 0)
        bucket['correct'] += int(row.correct or 0)
        bucket['earned'] += float(row.earned or 0)
        bucket['full'] += float(row.full or 0)

        full = float(row.full or 0)
        bucket['points'].append({
            'knowledge_point': row.knowledge_point,
            'score_rate': round(float(row.earned or 0) / full, 4) if full > 0 else 0.0,
        })

    for bucket in result.values():
        bucket['score_rate'] = (
            round(bucket['earned'] / bucket['full'], 4) if bucket['full'] > 0 else 0.0)
        bucket['mastered'] = bool(bucket['points']) and all(
            point['score_rate'] >= MASTER_THRESHOLD for point in bucket['points'])

    return result


def overview():
    """D1 用的总体概览。"""
    per_material = material_stats()

    study_count = (
        ChatMessage.query.filter(ChatMessage.role == 'user').count()
        + Quiz.query.filter(Quiz.status == 'submitted').count()
    )

    quizzes = Quiz.query.filter(Quiz.status == 'submitted').all()
    earned = sum(float(quiz.score or 0) for quiz in quizzes)
    full = sum(float(quiz.full_score or 0) for quiz in quizzes)

    return {
        'materials_total': Material.query.count(),
        'materials_mastered': sum(
            1 for bucket in per_material.values() if bucket['mastered']),
        'study_count': study_count,
        'avg_score_rate': round(earned / full, 4) if full > 0 else 0.0,
    }


def report_stats(start, end):
    """区间内的学习概况。"""
    new_materials = Material.query.filter(
        Material.created_at >= _day_start(start),
        Material.created_at < _day_after(end),
    ).count()

    # 一次「对话」按学员发一条消息算
    chat_count = ChatMessage.query.filter(
        ChatMessage.role == 'user',
        ChatMessage.created_at >= _day_start(start),
        ChatMessage.created_at < _day_after(end),
    ).count()

    quizzes = Quiz.query.filter(
        Quiz.status == 'submitted',
        Quiz.submitted_at >= _day_start(start),
        Quiz.submitted_at < _day_after(end),
    ).all()

    earned = sum(float(quiz.score or 0) for quiz in quizzes)
    full = sum(float(quiz.full_score or 0) for quiz in quizzes)

    return {
        'new_materials': new_materials,
        'chat_count': chat_count,
        'quiz_count': len(quizzes),
        'avg_score_rate': round(earned / full, 4) if full > 0 else 0.0,
    }


# ---------- 给提示词用的文本化 ----------

def format_stats_text(stats):
    return '\n'.join([
        '- 新增资料：%d 份' % stats['new_materials'],
        '- 对话次数：%d 次' % stats['chat_count'],
        '- 测评次数：%d 次' % stats['quiz_count'],
        '- 平均得分率：%d%%' % round(stats['avg_score_rate'] * 100),
    ])


def format_weak_text(items):
    if not items:
        return '（本期没有得分率低于 %d%% 的知识点）' % round(WEAK_THRESHOLD * 100)

    return '\n'.join([
        '- %s：得分率 %d%%（答对 %d / %d 题）' % (
            item['knowledge_point'],
            round(item['score_rate'] * 100),
            item['correct'],
            item['total'],
        )
        for item in items
    ])


def format_knowledge_text(items):
    if not items:
        return '（本期没有测评记录）'

    return '\n'.join([
        '- %s：得分率 %d%%' % (item['knowledge_point'], round(item['score_rate'] * 100))
        for item in items
    ])
