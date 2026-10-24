"""资料接口（功能需求文档 A1~A7）。

上传后立刻返回，抽取文字与切片在后台线程里跑，用户不用等。
"""

import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from api.common import error
from extensions import db
from models import Material, MaterialChunk
from tasks import process_material, run_in_background

bp = Blueprint('materials', __name__)

# 旧版 Office 二进制格式，Python 生态里没有可靠的开源解析器。
# 在上传这一步就直接拒绝并给出可操作的话术，而不是收下、后台跑一遍再失败。
LEGACY_HINTS = {
    'doc': '旧版 .doc 无法解析，请用 Word 另存为 .docx 后重新上传',
    'ppt': '旧版 .ppt 无法解析，请用 PowerPoint 另存为 .pptx 后重新上传',
}


def _serialize(material):
    return {
        'id': material.id,
        'name': material.name,
        'file_type': material.file_type,
        'file_size': material.file_size,
        'status': material.status,
        'error_msg': material.error_msg,
        'chunk_count': material.chunk_count,
        'note': material.note or '',
        'created_at': material.created_at.isoformat() if material.created_at else None,
    }


@bp.post('/materials')
def upload_material():
    """A1 上传资料。

    存文件 → 建记录（status=pending）→ 立刻返回 → 后台线程跑抽取与切片。
    """
    file = request.files.get('file')
    if file is None or not file.filename:
        return error('NO_FILE', '没有收到文件，表单字段名应为 file', 400)

    # 只取文件名部分，防止 ../ 之类的东西混进来
    display_name = Path(file.filename).name
    extension = Path(display_name).suffix.lower().lstrip('.')

    # 旧格式先拦，给的话术比「格式不支持」有用
    if extension in LEGACY_HINTS:
        return error('LEGACY_FORMAT', LEGACY_HINTS[extension], 400)

    if not extension or extension not in current_app.config['ALLOWED_EXTENSIONS']:
        return error('BAD_FILE_TYPE', '不支持的文件格式：.%s' % extension, 400)

    # 存储名自己生成，不用原始文件名，避免重名覆盖与路径穿越
    upload_dir = Path(current_app.config['UPLOAD_FOLDER'])
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_path = upload_dir / (uuid.uuid4().hex + '.' + extension)

    try:
        file.save(str(stored_path))
    except OSError as exc:
        current_app.logger.exception('保存上传文件失败')
        return error('SAVE_FAILED', '文件保存失败：%s' % exc, 500)

    material = Material(
        name=display_name[:255],
        file_type=extension,
        file_size=stored_path.stat().st_size,
        file_path=str(stored_path),
        status='pending',
    )
    db.session.add(material)
    db.session.commit()

    run_in_background(current_app._get_current_object(), process_material, material.id)

    return jsonify(_serialize(material)), 201


@bp.get('/materials')
def list_materials():
    """A2 资料列表。带出 note，供进度页直接渲染。"""
    materials = Material.query.order_by(Material.created_at.desc(), Material.id.desc()).all()
    return jsonify({'items': [_serialize(m) for m in materials]})


@bp.get('/materials/<int:material_id>')
def get_material(material_id):
    """A4 资料详情，附前几段文字便于确认抽取是否正常。"""
    material = db.session.get(Material, material_id)
    if material is None:
        return error('NOT_FOUND', '资料不存在', 404)

    preview = (MaterialChunk.query
               .filter_by(material_id=material_id)
               .order_by(MaterialChunk.chunk_index)
               .limit(3)
               .all())

    data = _serialize(material)
    data['chunks_preview'] = [
        {'chunk_index': chunk.chunk_index, 'content': chunk.content[:200]}
        for chunk in preview
    ]
    return jsonify(data)


@bp.get('/materials/<int:material_id>/status')
def get_material_status(material_id):
    """A3 资料处理状态。"""
    material = db.session.get(Material, material_id)
    if material is None:
        return error('NOT_FOUND', '资料不存在', 404)

    return jsonify({
        'id': material.id,
        'status': material.status,
        'chunk_count': material.chunk_count,
        'error_msg': material.error_msg,
    })


@bp.post('/materials/<int:material_id>/retry')
def retry_material(material_id):
    """A5 失败重试。重新排入队列并立刻返回。"""
    material = db.session.get(Material, material_id)
    if material is None:
        return error('NOT_FOUND', '资料不存在', 404)

    if material.status == 'ready':
        return error('ALREADY_READY', '该资料已解析完成，无需重试', 400)

    material.status = 'pending'
    material.error_msg = None
    db.session.commit()

    run_in_background(current_app._get_current_object(), process_material, material_id)

    return jsonify({'id': material.id, 'status': material.status})


@bp.delete('/materials/<int:material_id>')
def delete_material(material_id):
    """A6 删除资料：数据库记录（含切片）与磁盘文件一起清掉。"""
    material = db.session.get(Material, material_id)
    if material is None:
        return error('NOT_FOUND', '资料不存在', 404)

    file_path = material.file_path

    # 先删数据库再删文件。反过来的话，万一提交失败就会留下一份
    # 「文件已经没了」的记录，连重试都救不回来。
    db.session.delete(material)
    db.session.commit()

    _remove_file(file_path)

    return jsonify({'deleted': True, 'id': material_id})


@bp.put('/materials/<int:material_id>/note')
def save_material_note(material_id):
    """A7 保存资料笔记。前端停笔后自动调用。"""
    material = db.session.get(Material, material_id)
    if material is None:
        return error('NOT_FOUND', '资料不存在', 404)

    payload = request.get_json(silent=True) or {}
    if 'note' not in payload:
        return error('BAD_REQUEST', '请求体缺少 note 字段', 400)

    material.note = str(payload['note'])
    db.session.commit()

    return jsonify({'id': material.id, 'updated_at': datetime.now().isoformat()})


def _remove_file(file_path):
    """删磁盘文件。文件已经不在了不算错，其它失败只记日志不打断删除。"""
    if not file_path:
        return

    try:
        Path(file_path).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        current_app.logger.warning('删除文件失败，需手工清理：%s', file_path)
