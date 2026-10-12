import time
from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from api.dependencies import CurrentUser, pagination, require_csrf
from api.schemas import ReportPatch, ReportRequest
from backend.models import WeeklyReport
from backend.reports import owned_report, serialize_report

router = APIRouter(prefix='/weekly-reports', tags=['周报'])


@router.get('')
def list_reports(request: Request, user: CurrentUser, page=Depends(pagination)):
    limit, offset = page
    with request.app.state.database.session() as db:
        query = select(WeeklyReport).where(WeeklyReport.user_id == user.id)
        rows = db.scalars(query.order_by(WeeklyReport.updated_at.desc()).limit(limit).offset(offset)).all()
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        return {'items': [serialize_report(row) for row in rows], 'total': total}


@router.post('', status_code=201, dependencies=[Depends(require_csrf)])
def create_report(body: ReportRequest, request: Request, user: CurrentUser):
    with request.app.state.database.session() as db:
        row = WeeklyReport(user_id=user.id, **body.model_dump())
        db.add(row)
        db.commit()
        return serialize_report(row)


@router.get('/{report_id}')
def get_report(report_id: str, request: Request, user: CurrentUser):
    with request.app.state.database.session() as db:
        return serialize_report(owned_report(db, report_id, user.id))


@router.patch('/{report_id}', dependencies=[Depends(require_csrf)])
def update_report(report_id: str, body: ReportPatch, request: Request, user: CurrentUser):
    with request.app.state.database.session() as db:
        row = owned_report(db, report_id, user.id)
        for key, value in body.model_dump(exclude_none=True).items():
            setattr(row, key, value)
        row.updated_at = time.time()
        db.commit()
        return serialize_report(row)


@router.delete('/{report_id}', dependencies=[Depends(require_csrf)])
def delete_report(report_id: str, request: Request, user: CurrentUser):
    with request.app.state.database.session() as db:
        db.delete(owned_report(db, report_id, user.id))
        db.commit()
    return {'ok': True}
