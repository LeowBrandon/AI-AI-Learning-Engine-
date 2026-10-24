"""测评接口（功能需求文档 C1~C5）。

出题：把资料交给模型，题型配比 1/2 选择 + 1/4 判断 + 1/4 简答（后端算好再给它），
      难度按简单/中等/较难大致均分。
改卷：题目与学员作答交给模型给理由，但**选择题与判断题的分数在本地精确判定** ——
      模型偶尔会把错的判成对，这种错误用户一眼就能看见，不能交给它。
"""

import json
import re
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request

import context as ctx
from api.common import error
from extensions import db
from llm import LLMError, chat_json
from models import Answer, Question, Quiz
from prompts import GRADER_SYSTEM, QUIZ_SYSTEM, grader_user, quiz_user

bp = Blueprint('quizzes', __name__)

VALID_TYPES = {'choice', 'judge', 'short'}
VALID_DIFFICULTY = {'easy', 'medium', 'hard'}
MIN_QUESTIONS = 1
MAX_QUESTIONS = 30

# 判断题的选项是固定的，不由模型生成
JUDGE_OPTIONS = {'A': '正确', 'B': '错误'}

# 选项形如 "A. 文本" / "A、文本" / "A．文本"，剥掉这个前缀
OPTION_PREFIX = re.compile(r'^([A-Za-z])\s*[.、)．:：]\s*(.+)$')


# ============================================================
# C1 生成试卷
# ============================================================

@bp.post('/quizzes')
def create_quiz():
    payload = request.get_json(silent=True) or {}

    material_ids = payload.get('material_ids') or []
    question_count = payload.get('question_count')

    if not material_ids:
        return error('BAD_REQUEST', '请求体缺少 material_ids', 400)
    if not isinstance(question_count, int) or not MIN_QUESTIONS <= question_count <= MAX_QUESTIONS:
        return error('BAD_REQUEST',
                     'question_count 必须是 %d~%d 的整数' % (MIN_QUESTIONS, MAX_QUESTIONS), 400)

    materials = ctx.load_materials(material_ids)
    if not materials:
        return error('NO_MATERIAL', '所选资料不存在或尚未解析完成', 400)

    pairs = ctx.select_for_generation(
        materials, current_app.config['MATERIAL_CONTEXT_LIMIT'])
    if not pairs:
        return error('NO_CONTENT', '所选资料还没有可用的文字内容', 400)

    counts = distribute_counts(question_count)
    # 带上【资料 N】编号，模型回填 material_id 时才能挂到具体资料上
    material_context = ctx.format_context(pairs, with_material_id=True)

    try:
        data = chat_json([
            {'role': 'system', 'content': QUIZ_SYSTEM},
            {'role': 'user', 'content': quiz_user(material_context, counts)},
        ])
    except LLMError as exc:
        return error('LLM_FAILED', str(exc), 502)

    questions = _normalize_questions(
        data.get('questions') if isinstance(data, dict) else None, materials)
    if not questions:
        return error('LLM_BAD_OUTPUT', '模型没有返回可用的题目，请重试', 502)

    quiz = Quiz(
        material_ids=[material.id for material in materials],
        question_count=len(questions),
        full_score=len(questions),      # 每题 1 分
        status='created',
    )
    db.session.add(quiz)
    db.session.flush()

    for index, item in enumerate(questions, start=1):
        db.session.add(Question(
            quiz_id=quiz.id,
            seq=index,
            type=item['type'],
            difficulty=item['difficulty'],
            material_id=item['material_id'],
            question=item['question'],
            options=item['options'],
            answer=item['answer'],
            scoring=item['scoring'],
            explanation=item['explanation'],
            knowledge_point=item['knowledge_point'],
            source=item['source'],
            full_score=1,
        ))

    db.session.commit()

    return jsonify(_serialize_paper(quiz)), 201


@bp.get('/quizzes')
def list_quizzes():
    """C5 历史测评记录。"""
    quizzes = (Quiz.query
               .filter(Quiz.status == 'submitted')
               .order_by(Quiz.submitted_at.desc(), Quiz.id.desc())
               .all())

    return jsonify({'items': [{
        'id': quiz.id,
        'question_count': quiz.question_count,
        'score': float(quiz.score or 0),
        'full_score': float(quiz.full_score or 0),
        'duration_seconds': quiz.duration_seconds,
        'submitted_at': quiz.submitted_at.isoformat() if quiz.submitted_at else None,
    } for quiz in quizzes]})


@bp.get('/quizzes/<int:quiz_id>')
def get_quiz(quiz_id):
    """C2 获取试卷题目。**不含答案与解析**，避免前端泄露。"""
    quiz = db.session.get(Quiz, quiz_id)
    if quiz is None:
        return error('NOT_FOUND', '测评不存在', 404)

    return jsonify(_serialize_paper(quiz))


# ============================================================
# C3 提交判卷
# ============================================================

@bp.post('/quizzes/<int:quiz_id>/submit')
def submit_quiz(quiz_id):
    quiz = db.session.get(Quiz, quiz_id)
    if quiz is None:
        return error('NOT_FOUND', '测评不存在', 404)
    if quiz.status == 'submitted':
        return error('ALREADY_SUBMITTED', '该测评已提交过', 400)

    payload = request.get_json(silent=True) or {}
    submitted = payload.get('answers')
    if not isinstance(submitted, list) or not submitted:
        return error('BAD_REQUEST', '请求体缺少 answers', 400)

    questions = quiz.questions
    if not questions:
        return error('NO_QUESTIONS', '该测评没有题目', 400)

    user_answers = {}
    for item in submitted:
        if isinstance(item, dict) and item.get('question_id') is not None:
            try:
                user_answers[int(item['question_id'])] = item.get('user_answer')
            except (TypeError, ValueError):
                continue

    # 只给选择题带 options：判断题的标准答案是布尔，再把 A/B 选项塞给它容易混淆
    questions_payload = json.dumps([{
        'question_id': question.id,
        'type': question.type,
        'question': question.question,
        'options': question.options if question.type == 'choice' else None,
        'correct_answer': question.answer,
        'scoring': question.scoring,
        'full_score': float(question.full_score or 1),
    } for question in questions], ensure_ascii=False, indent=2)

    answers_payload = json.dumps([{
        'question_id': question.id,
        'user_answer': user_answers.get(question.id),
    } for question in questions], ensure_ascii=False, indent=2)

    try:
        graded = chat_json([
            {'role': 'system', 'content': GRADER_SYSTEM},
            {'role': 'user', 'content': grader_user(questions_payload, answers_payload)},
        ])
    except LLMError as exc:
        return error('LLM_FAILED', str(exc), 502)

    verdicts = _match_verdicts(questions, graded.get('results') if isinstance(graded, dict) else None)

    total = 0.0
    for question in questions:
        verdict = verdicts.get(question.id, {})
        user_answer = user_answers.get(question.id)
        full = float(question.full_score or 1)

        if question.type == 'short':
            score = _clamp_short_score(verdict.get('score'), full)
            is_correct = score >= full
        else:
            # 选择/判断本地判定，不依赖模型
            is_correct = _is_exact_match(question, user_answer)
            score = full if is_correct else 0.0

        total += score

        db.session.add(Answer(
            quiz_id=quiz.id,
            question_id=question.id,
            user_answer=user_answer,
            score=score,
            is_correct=is_correct,
            hit_points=_as_list(verdict.get('hit_points')),
            miss_points=_as_list(verdict.get('miss_points')),
            reason=str(verdict.get('reason') or '').strip() or None,
        ))

    quiz.score = round(total, 1)
    quiz.status = 'submitted'
    quiz.submitted_at = datetime.now()

    duration = payload.get('duration_seconds')
    quiz.duration_seconds = int(duration) if isinstance(duration, (int, float)) else None

    db.session.commit()

    return jsonify(_serialize_result(quiz))


@bp.get('/quizzes/<int:quiz_id>/result')
def get_quiz_result(quiz_id):
    """C4 查看测评结果。"""
    quiz = db.session.get(Quiz, quiz_id)
    if quiz is None:
        return error('NOT_FOUND', '测评不存在', 404)
    if quiz.status != 'submitted':
        return error('NOT_SUBMITTED', '该测评尚未提交', 400)

    return jsonify(_serialize_result(quiz))


# ============================================================
# 题型与难度配比
# ============================================================

def distribute_counts(total):
    """选择 1/2、判断 1/4、简答 1/4；难度三种大致均分。

    由后端算好再告诉模型，而不是让模型自己分 —— 它算不准，
    分配错了前端看到的题型比例就不对。
    """
    choice = int(total / 2 + 0.5)
    judge = int(total / 4 + 0.5)
    short = total - choice - judge

    if short < 0:
        judge = max(0, total - choice)
        short = total - choice - judge

    easy = total // 3
    hard = total // 3
    medium = total - easy - hard

    return {
        'total': total,
        'choice': choice,
        'judge': judge,
        'short': short,
        'easy': easy,
        'medium': medium,
        'hard': hard,
    }


# ============================================================
# 模型输出的清洗与校验
# ============================================================

def _normalize_questions(raw, materials):
    """把模型返回的题目逐条校验，不合规的丢掉。"""
    if not isinstance(raw, list):
        return []

    allowed_ids = {material.id for material in materials}
    name_to_id = {material.name: material.id for material in materials}
    only_material = materials[0].id if len(materials) == 1 else None

    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue

        qtype = str(item.get('type') or '').strip().lower()
        question = str(item.get('question') or '').strip()
        if qtype not in VALID_TYPES or not question:
            continue

        answer = item.get('answer')
        options = None
        scoring = None

        if qtype == 'choice':
            options = normalize_choice_options(item.get('options'))
            if options is None:
                continue
            if not isinstance(answer, str) or not answer.strip():
                continue
            answer = answer.strip().upper()[:1]
            if answer not in options:
                continue

        elif qtype == 'judge':
            # 判断题的选项固定，不采信模型给的
            options = dict(JUDGE_OPTIONS)
            if isinstance(answer, str):
                answer = answer.strip().lower() in ('true', '对', '正确', 'yes', 't', '是')
            elif not isinstance(answer, bool):
                continue

        else:
            answer = str(answer or '').strip()
            if not answer:
                continue
            scoring = item.get('scoring')
            if not isinstance(scoring, list) or not scoring:
                scoring = ['答出核心要点即得满分']
            scoring = [str(point).strip() for point in scoring]

        difficulty = str(item.get('difficulty') or '').strip().lower()
        if difficulty not in VALID_DIFFICULTY:
            difficulty = 'medium'

        source = str(item.get('source') or '').strip()[:255]

        result.append({
            'type': qtype,
            'difficulty': difficulty,
            'material_id': _resolve_material_id(
                item.get('material_id'), source, allowed_ids, name_to_id, only_material),
            'question': question,
            'options': options,
            'answer': answer,
            'scoring': scoring,
            'explanation': str(item.get('explanation') or '').strip(),
            'knowledge_point': (str(item.get('knowledge_point') or '').strip() or '未分类')[:128],
            'source': source,
        })

    return result


def normalize_choice_options(raw):
    """把选项统一成 {"A": "文本", "B": "文本", ...}。

    模型给的形式不固定，三种都要能吃下：
    1. 数组 ["A. 文本", "B. 文本"]（最常见，提示词里要的就是这个）
    2. 对象 {"A": "文本", "B": "文本"}
    3. 一个 JSON 字符串 '["A. 文本", ...]'

    统一成对象之后，前端拿到的形状就固定了，不用再猜。
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return None

    if isinstance(raw, dict):
        result = {}
        for key, value in raw.items():
            letter = str(key).strip().upper()[:1]
            text = str(value).strip()
            if letter and text:
                result[letter] = text
        return result if len(result) >= 2 else None

    if isinstance(raw, list):
        result = {}
        for index, value in enumerate(raw):
            text = str(value).strip()
            if not text:
                continue
            matched = OPTION_PREFIX.match(text)
            if matched:
                result[matched.group(1).upper()] = matched.group(2).strip()
            else:
                # 没有 "A." 这种前缀，按位置补字母
                result[chr(65 + index)] = text
        return result if len(result) >= 2 else None

    return None


def _resolve_material_id(raw_id, source, allowed_ids, name_to_id, only_material):
    """把题目挂到具体资料上。

    模型可能写错或漏掉 material_id，依次用三种办法兜：
    1. 直接用模型给的编号（必须在本次送出去的资料范围内）
    2. 从 source 文本里找资料名
    3. 本次只送了一份资料，那必然是它
    """
    try:
        candidate = int(raw_id)
        if candidate in allowed_ids:
            return candidate
    except (TypeError, ValueError):
        pass

    for name, material_id in name_to_id.items():
        if name and name in source:
            return material_id

    return only_material


def _match_verdicts(questions, raw_results):
    """把模型的判卷结果对应回题目。

    模型偶尔会漏 id 或写错 id，这里按顺序兜底，避免整份卷子因为一个 id 就判不了。
    """
    by_id = {question.id: question for question in questions}
    verdicts = {}

    if not isinstance(raw_results, list):
        return verdicts

    for index, item in enumerate(raw_results):
        if not isinstance(item, dict):
            continue

        try:
            question_id = int(item.get('question_id'))
        except (TypeError, ValueError):
            question_id = None

        question = by_id.get(question_id)
        if question is None or question.id in verdicts:
            question = questions[index] if index < len(questions) else None
        if question is None or question.id in verdicts:
            continue

        verdicts[question.id] = item

    return verdicts


def _is_exact_match(question, user_answer):
    """选择题与判断题的精确判定。"""
    if user_answer is None:
        return False

    correct = question.answer

    if question.type == 'judge':
        if isinstance(user_answer, str):
            user_answer = user_answer.strip().lower() in ('true', '对', '正确', 'yes', 't', '是')
        return bool(user_answer) == bool(correct)

    if isinstance(user_answer, str) and isinstance(correct, str):
        # 容忍 "b" / "B." / " B " 这类写法
        return user_answer.strip().upper()[:1] == correct.strip().upper()[:1]

    return str(user_answer).strip() == str(correct).strip()


def _clamp_short_score(score, full):
    """简答题只允许 0 / 0.5 / 1 三档，模型给了中间值也要归到档位上。"""
    try:
        value = float(score)
    except (TypeError, ValueError):
        return 0.0

    if value >= full * 0.75:
        return full
    if value >= full * 0.25:
        return round(full * 0.5, 1)
    return 0.0


def _as_list(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return None


# ============================================================
# 序列化
# ============================================================

def _serialize_paper(quiz):
    """给答题用的卷面。刻意不含 answer / explanation / scoring。"""
    return {
        'quiz_id': quiz.id,
        'question_count': quiz.question_count,
        'total_score': float(quiz.full_score or 0),
        'questions': [{
            'id': question.id,
            'seq': question.seq,
            'type': question.type,
            'difficulty': question.difficulty,
            'question': question.question,
            'options': question.options,
            'full_score': float(question.full_score or 1),
        } for question in quiz.questions],
    }


def _serialize_result(quiz):
    rows = (db.session.query(Question, Answer)
            .join(Answer, Answer.question_id == Question.id)
            .filter(Answer.quiz_id == quiz.id)
            .order_by(Question.seq)
            .all())

    details = []
    for question, answer in rows:
        details.append({
            'question_id': question.id,
            'type': question.type,
            'user_answer': answer.user_answer,
            'correct_answer': question.answer,
            'score': float(answer.score or 0),
            'full_score': float(question.full_score or 1),
            'is_correct': bool(answer.is_correct),
            'reason': answer.reason or '',
            'knowledge_point': question.knowledge_point,
        })

    return {
        'quiz_id': quiz.id,
        'total_score': float(quiz.score or 0),
        'full_score': float(quiz.full_score or 0),
        'duration_seconds': quiz.duration_seconds,
        'details': details,
        'weak_points': _weak_points(details),
    }


def _weak_points(details):
    """本次测评里得分率不满 100% 的知识点，按低到高排序，最多 5 个。

    在本地算而不是用模型的 summary，保证与逐题结果一致。
    """
    buckets = {}
    for item in details:
        bucket = buckets.setdefault(item['knowledge_point'], {'earned': 0.0, 'full': 0.0})
        bucket['earned'] += item['score']
        bucket['full'] += item['full_score']

    weak = []
    for name, bucket in buckets.items():
        if bucket['full'] <= 0:
            continue
        rate = bucket['earned'] / bucket['full']
        if rate < 1:
            weak.append({'knowledge_point': name, 'score_rate': round(rate, 4)})

    weak.sort(key=lambda item: item['score_rate'])
    return weak[:5]
