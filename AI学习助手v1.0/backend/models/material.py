"""资料相关表：materials / material_chunks。"""

from datetime import datetime

from extensions import db
from models.base import BigIntPK


class Material(db.Model):
    """上传的学习资料。"""

    __tablename__ = 'materials'

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(16), nullable=False)
    file_size = db.Column(db.BigInteger, nullable=False, default=0)
    file_path = db.Column(db.String(512), nullable=False)
    # pending 排队中 / processing 处理中 / ready 可用 / failed 失败
    status = db.Column(db.String(16), nullable=False, default='pending', index=True)
    error_msg = db.Column(db.String(512))
    chunk_count = db.Column(db.Integer, nullable=False, default=0)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    chunks = db.relationship(
        'MaterialChunk',
        back_populates='material',
        cascade='all, delete-orphan',
        order_by='MaterialChunk.chunk_index'
    )

    def __repr__(self):
        return '<Material %s %s>' % (self.id, self.name)


class MaterialChunk(db.Model):
    """资料切片。

    不用向量检索，这里不做 embedding。切片只用于两件事：
    1. 长文档分块存储，拼接提示词时便于按上限截断；
    2. 回答时告诉前端「依据来自哪几份资料的哪几段」。
    """

    __tablename__ = 'material_chunks'

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    material_id = db.Column(
        db.BigInteger,
        db.ForeignKey('materials.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    chunk_index = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    material = db.relationship('Material', back_populates='chunks')

    def __repr__(self):
        return '<MaterialChunk %s#%s>' % (self.material_id, self.chunk_index)
