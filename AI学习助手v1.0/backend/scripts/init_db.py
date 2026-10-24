"""建表脚本。

    cd backend
    python scripts/init_db.py           # 建表（已存在的表不动）
    python scripts/init_db.py --drop    # 先删光再建，开发期重置用

表结构由 models/ 下的模型定义，与《功能需求文档.md》第三节一一对应。
"""

import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import models  # noqa: F401  导入即注册所有模型
from app import create_app
from extensions import db

# 连接串里可能带数据库密码（如 postgresql://user:pass@host/db），打印前抹掉
PASSWORD_IN_URL = re.compile(r'(://[^:/@]+:)[^@]+(@)')


def safe_database_url(url):
    return PASSWORD_IN_URL.sub(r'\1****\2', url)


def main():
    drop_first = '--drop' in sys.argv

    app = create_app()

    with app.app_context():
        if drop_first:
            db.drop_all()
            print('已删除全部旧表')

        db.create_all()

        names = sorted(db.metadata.tables.keys())
        print('数据库：%s' % safe_database_url(app.config['SQLALCHEMY_DATABASE_URI']))
        print('已建表 %d 张：' % len(names))
        for name in names:
            columns = db.metadata.tables[name].columns
            print('  - %-18s %d 个字段' % (name, len(columns)))


if __name__ == '__main__':
    main()
