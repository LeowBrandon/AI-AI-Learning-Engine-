"""报告接口（功能需求文档 E1~E3）。

把区间内的统计与薄弱点交给模型，让它写一份四节结构的 Markdown 周报。
报告存的是生成当时的快照，之后数据变化不影响已生成的报告。
"""

from datetime import date
from urllib.parse import quote

from flask import Blueprint, jsonify, make_response, request

import stats
from api.common import error
from extensions import db
from llm import LLMError, chat
from models import Report
from prompts import ANALYST_SYSTEM, analyst_user

bp = Blueprint('reports', __name__)

# 写报告需要一点组织语言的余地，温度略高于默认
REPORT_TEMPERATURE = 0.4


@bp.post('/reports')
def create_report():
    """E1 生成周报。"""
    payload = request.get_json(silent=True) or {}

    start = _parse_date(payload.get('start_date'))
    end = _parse_date(payload.get('end_date'))

    if start is None or end is None:
        return error('BAD_REQUEST', 'start_date 与 end_date 必须是 YYYY-MM-DD 格式', 400)
    if start > end:
        return error('BAD_REQUEST', 'start_date 不能晚于 end_date', 400)

    overview = stats.report_stats(start, end)
    weak = stats.weak_points(start, end)
    knowledge = stats.knowledge_stats(start, end)

    # 把知识点清单并进「统计数据」，模型才写得出「学了什么」这一节
    stats_text = '%s\n\n本期知识点掌握情况：\n%s' % (
        stats.format_stats_text(overview),
        stats.format_knowledge_text(knowledge),
    )

    try:
        content = chat([
            {'role': 'system', 'content': ANALYST_SYSTEM},
            {'role': 'user', 'content': analyst_user(
                start.isoformat(), end.isoformat(),
                stats_text, stats.format_weak_text(weak),
            )},
        ], temperature=REPORT_TEMPERATURE)
    except LLMError as exc:
        return error('LLM_FAILED', str(exc), 502)

    report = Report(
        start_date=start,
        end_date=end,
        stats=overview,
        weak_points=[{
            'knowledge_point': item['knowledge_point'],
            'score_rate': item['score_rate'],
        } for item in weak],
        content=content.strip(),
    )
    db.session.add(report)
    db.session.commit()

    return jsonify(_serialize(report)), 201


@bp.get('/reports')
def list_reports():
    """E2 历史报告列表。不带 content，避免响应过大。"""
    reports = Report.query.order_by(Report.created_at.desc(), Report.id.desc()).all()
    return jsonify({'items': [_serialize(report, with_content=False) for report in reports]})


@bp.get('/reports/<int:report_id>')
def get_report(report_id):
    """E3 查看某份报告。"""
    report = db.session.get(Report, report_id)
    if report is None:
        return error('NOT_FOUND', '报告不存在', 404)

    return jsonify(_serialize(report))


@bp.get('/reports/<int:report_id>/download')
def download_report(report_id):
    """E4 下载报告，直接返回 Markdown 文件。

    前端也有一份等价实现（用 Blob 在浏览器里拼，省一次往返）。
    这个接口是给「直接拿 URL 下载」的场景用的，两边格式保持一致。
    """
    report = db.session.get(Report, report_id)
    if report is None:
        return error('NOT_FOUND', '报告不存在', 404)

    filename = '学习周报_%s_%s.md' % (
        report.start_date.isoformat(), report.end_date.isoformat())

    response = make_response(build_report_file(report))
    response.headers['Content-Type'] = 'text/markdown; charset=utf-8'
    # 文件名有中文，用 RFC 5987 的 filename*；同时给一个纯 ASCII 的兜底
    response.headers['Content-Disposition'] = (
        "attachment; filename=report_%d.md; filename*=UTF-8''%s"
        % (report.id, quote(filename))
    )
    return response


def build_report_file(report):
    """报告文件的正文结构。与前端 buildReportFile() 保持一致。"""
    overview = report.stats or {}
    rate = overview.get('avg_score_rate')
    rate_text = '%d%%' % round(rate * 100) if isinstance(rate, (int, float)) else '—'

    return '\n'.join([
        '# 学习周报（%s ~ %s）' % (
            report.start_date.isoformat(), report.end_date.isoformat()),
        '',
        '- 新增资料：%d 份' % overview.get('new_materials', 0),
        '- 对话次数：%d 次' % overview.get('chat_count', 0),
        '- 测评次数：%d 次' % overview.get('quiz_count', 0),
        '- 平均得分率：%s' % rate_text,
        '',
        '---',
        '',
        report.content or '',
    ])


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _serialize(report, with_content=True):
    data = {
        'id': report.id,
        'start_date': report.start_date.isoformat(),
        'end_date': report.end_date.isoformat(),
        'created_at': report.created_at.isoformat() if report.created_at else None,
    }

    if with_content:
        data['stats'] = report.stats or {}
        data['weak_points'] = report.weak_points or []
        data['content'] = report.content

    return data
