"""后台任务：上传后异步跑完整流程，不让用户等着。

用线程而不是 Celery/RQ：这是单机单用户的小工具，起消息队列的复杂度不划算。
代价是进程重启会丢掉正在跑的任务 —— 重启后状态卡在 pending/processing 的资料，
用 POST /api/materials/<id>/retry 重新排队即可。
"""

import logging
import threading

from flask import current_app

from extensions import db
from extractor import ExtractError, extract_text, split_chunks
from models import Material, MaterialChunk

logger = logging.getLogger(__name__)


def run_in_background(app, func, *args):
    """把 func 丢进后台线程执行。

    线程里必须自己 push app context，否则拿不到 current_app 和 db.session。
    app 要传真实对象（current_app._get_current_object()），不能传代理。
    """

    def worker():
        with app.app_context():
            try:
                func(*args)
            except Exception:
                logger.exception('后台任务 %s 未捕获异常', func.__name__)

    thread = threading.Thread(target=worker, name='study-task', daemon=True)
    thread.start()
    return thread


def process_material(material_id):
    """一份资料的完整流程：读文字 → 切片 → 入库。状态自己维护。"""
    material = db.session.get(Material, material_id)
    if material is None:
        logger.warning('资料 %s 已不存在，跳过处理', material_id)
        return

    _set_status(material_id, 'processing')

    try:
        text = extract_text(material.file_path, material.file_type)
    except ExtractError as exc:
        # 可预期的失败，消息直接给用户看
        _set_status(material_id, 'failed', str(exc))
        return
    except Exception as exc:
        logger.exception('解析资料 %s 时出错', material_id)
        _set_status(material_id, 'failed', '解析失败：%s' % exc)
        return

    if not text.strip():
        _set_status(material_id, 'failed', '没有读到任何文字，可能是扫描件或纯图片文档')
        return

    chunks = split_chunks(text, current_app.config['CHUNK_SIZE'])

    try:
        # 重试时先清掉上一次的切片，避免重复堆积
        (MaterialChunk.query
         .filter_by(material_id=material_id)
         .delete(synchronize_session=False))

        db.session.add_all([
            MaterialChunk(material_id=material_id, chunk_index=index, content=content)
            for index, content in enumerate(chunks)
        ])

        _set_status(material_id, 'ready', chunk_count=len(chunks))
    except Exception as exc:
        db.session.rollback()
        logger.exception('写入资料 %s 的切片失败', material_id)
        _set_status(material_id, 'failed', '写入数据库失败：%s' % exc)


def _set_status(material_id, status, error_msg=None, chunk_count=None):
    material = db.session.get(Material, material_id)
    if material is None:
        return

    material.status = status
    material.error_msg = error_msg

    if chunk_count is not None:
        material.chunk_count = chunk_count

    db.session.commit()
