"""Idempotent seed; passwords must be provided through the environment."""
import csv
import os
from pathlib import Path
from sqlalchemy import select
from backend.auth import hasher
from backend.models import EmployeeRecord, User


def seed_database(database, password):
    if len(password) < 12:
        raise ValueError('DEMO_PASSWORD must contain at least 12 characters')
    path = Path(__file__).resolve().parents[1] / 'data/enterprise_external/employee_records.csv'
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    with database.session() as db:
        for row in rows:
            employee_id = row['employee_id']
            if not db.get(EmployeeRecord, employee_id):
                db.add(EmployeeRecord(employee_id=employee_id, data=row))
            if not db.scalar(select(User).where(User.username == employee_id)):
                db.add(User(username=employee_id, name=row['employee_name'], role='employee',
                            employee_id=employee_id, password_hash=hasher.hash(password)))
        if not db.scalar(select(User).where(User.username == 'admin')):
            db.add(User(username='admin', name='知识库管理员', role='admin',
                        employee_id=None, password_hash=hasher.hash(password)))
        db.commit()


if __name__ == '__main__':
    from backend.db import Database
    from backend.settings import Settings
    settings = Settings.from_env()
    seed_database(Database(settings.database_url), os.environ['DEMO_PASSWORD'])
    print('演示账号及模拟记录已初始化；已有账号密码保持不变。')
