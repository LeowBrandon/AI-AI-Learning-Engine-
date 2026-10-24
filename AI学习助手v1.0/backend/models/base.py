"""模型公共部分。"""

from extensions import db

# SQLite 只有当列类型正好是 INTEGER 时才会自增，写成 BIGINT 不会。
# 用 with_variant 让同一份模型在 SQLite 上退化成 INTEGER，在 PostgreSQL/MySQL 上仍是 BIGINT。
BigIntPK = db.BigInteger().with_variant(db.Integer, 'sqlite')
