"""学习报告表：reports。"""

from datetime import datetime

from extensions import db
from models.base import BigIntPK


class Report(db.Model):
    """一份生成过的学习报告。

    存的是生成当时的快照，不随底层数据变化重算 ——
    这样历史报告点开看到的是当时的样子。
    """

    __tablename__ = 'reports'

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    # {new_materials, chat_count, quiz_count, avg_score_rate}
    stats = db.Column(db.JSON, nullable=False)
    # [{knowledge_point, score_rate}]
    weak_points = db.Column(db.JSON, nullable=False)
    content = db.Column(db.Text, nullable=False)             # AI 生成的 Markdown 正文
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now, index=True)

    def __repr__(self):
        return '<Report %s %s~%s>' % (self.id, self.start_date, self.end_date)
