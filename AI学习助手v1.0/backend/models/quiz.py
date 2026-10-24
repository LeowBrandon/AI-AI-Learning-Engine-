"""测评相关表：quizzes / questions / answers。"""

from datetime import datetime

from extensions import db
from models.base import BigIntPK


class Quiz(db.Model):
    """一次测评。"""

    __tablename__ = 'quizzes'

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    material_ids = db.Column(db.JSON, nullable=False)
    question_count = db.Column(db.Integer, nullable=False, default=0)
    full_score = db.Column(db.Numeric(5, 1), nullable=False, default=0)
    score = db.Column(db.Numeric(5, 1))
    status = db.Column(db.String(16), nullable=False, default='created')   # created / submitted
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    submitted_at = db.Column(db.DateTime)
    duration_seconds = db.Column(db.Integer)

    questions = db.relationship(
        'Question',
        back_populates='quiz',
        cascade='all, delete-orphan',
        order_by='Question.seq'
    )
    answers = db.relationship(
        'Answer',
        back_populates='quiz',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return '<Quiz %s %s>' % (self.id, self.status)


class Question(db.Model):
    """题目。

    answer 用 JSON 而不是 TEXT：选择题答案是字符串，判断题答案是布尔，
    用 TEXT 存会把 True 变成 'True'，判卷时要再猜一次类型。
    """

    __tablename__ = 'questions'

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    quiz_id = db.Column(
        db.BigInteger,
        db.ForeignKey('quizzes.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    seq = db.Column(db.Integer, nullable=False)
    type = db.Column(db.String(16), nullable=False)          # choice / judge / short
    difficulty = db.Column(db.String(16), nullable=False, default='medium')  # easy / medium / hard
    # 题目取自哪份资料。用 SET NULL 而不是 CASCADE：
    # 删掉资料不该把往期测评的题目一起抹掉，历史记录要保持完整。
    material_id = db.Column(
        db.BigInteger,
        db.ForeignKey('materials.id', ondelete='SET NULL'),
        index=True
    )
    question = db.Column(db.Text, nullable=False)
    options = db.Column(db.JSON)                             # 仅选择题，4 个
    answer = db.Column(db.JSON, nullable=False)
    scoring = db.Column(db.JSON)                             # 仅简答题的评分要点
    explanation = db.Column(db.Text, nullable=False, default='')
    knowledge_point = db.Column(db.String(128), nullable=False, index=True)
    source = db.Column(db.String(255), nullable=False, default='')
    full_score = db.Column(db.Numeric(4, 1), nullable=False, default=1)

    quiz = db.relationship('Quiz', back_populates='questions')

    __table_args__ = (
        db.Index('ix_questions_quiz_seq', 'quiz_id', 'seq'),
    )

    def __repr__(self):
        return '<Question %s %s>' % (self.id, self.type)


class Answer(db.Model):
    """学员作答与判分结果。

    user_answer 同样用 JSON：判断题要保住布尔类型，未作答要保住 None。
    """

    __tablename__ = 'answers'

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    quiz_id = db.Column(
        db.BigInteger,
        db.ForeignKey('quizzes.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    question_id = db.Column(
        db.BigInteger,
        db.ForeignKey('questions.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    user_answer = db.Column(db.JSON)
    score = db.Column(db.Numeric(4, 1), nullable=False, default=0)
    is_correct = db.Column(db.Boolean, nullable=False, default=False)
    hit_points = db.Column(db.JSON)
    miss_points = db.Column(db.JSON)
    reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    quiz = db.relationship('Quiz', back_populates='answers')

    def __repr__(self):
        return '<Answer %s q%s>' % (self.id, self.question_id)
