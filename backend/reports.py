from fastapi import HTTPException
from backend.models import WeeklyReport


def owned_report(db, report_id, user_id):
    report = db.get(WeeklyReport, report_id)
    if not report or report.user_id != user_id:
        raise HTTPException(404, '周报不存在')
    return report


def serialize_report(row):
    return {key: getattr(row, key) for key in ('id', 'title', 'content', 'created_at', 'updated_at')}
