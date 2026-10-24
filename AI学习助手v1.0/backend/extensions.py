"""Flask 扩展实例。

单独放一个模块，避免 app.py 与 models 之间循环引用。
"""

import sqlite3

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()


@event.listens_for(Engine, 'connect')
def _sqlite_pragmas(dbapi_connection, _connection_record):
    """SQLite 上的三项必要设置，缺一个都会出问题：

    - foreign_keys=ON：SQLite 默认**不校验外键**，不打开的话建表时写的
      ON DELETE CASCADE 形同虚设，删资料会留下一堆孤儿切片。
    - journal_mode=WAL：允许读写并发。切片是在后台线程里写的，
      不开 WAL 的话前台查询会被写事务锁住。
    - busy_timeout：遇到锁时等一会儿再报错，而不是立刻抛 database is locked。
    """
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return

    cursor = dbapi_connection.cursor()
    cursor.execute('PRAGMA foreign_keys=ON')
    cursor.execute('PRAGMA journal_mode=WAL')
    cursor.execute('PRAGMA busy_timeout=5000')
    cursor.close()
