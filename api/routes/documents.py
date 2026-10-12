from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File
import asyncio
from sqlalchemy import func, select
from api.dependencies import AdminUser, CurrentUser, pagination, require_csrf
from api.schemas import DocumentPatch
from backend.models import DocumentVersion, KnowledgeDocument

router = APIRouter(tags=['知识库'])


@router.get('/documents')
def list_documents(request: Request, user: AdminUser, page=Depends(pagination)):
    limit, offset = page
    with request.app.state.database.session() as db:
        query = select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())
        rows = db.scalars(query.limit(limit).offset(offset)).all()
        def document(row):
            versions = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == row.id)
                                  .order_by(DocumentVersion.number)).all()
            return {'id': row.id, 'title': row.title, 'enabled': row.enabled,
                    'active_version_id': row.active_version_id,
                    'versions': [{'id': v.id, 'number': v.number, 'status': v.status,
                                  'error_code': v.error_code} for v in versions]}
        return {'items': [document(row) for row in rows],
                'total': db.scalar(select(func.count()).select_from(KnowledgeDocument))}


async def upload_version(request, response, user, file, document_id=None):
    content = await file.read(10 * 1024 * 1024 + 1)
    service = request.app.state.knowledge
    document_id, version_id, duplicate = await asyncio.to_thread(
        service.upload, file.filename, content, user.id, document_id)
    response.status_code = 200 if duplicate else 201
    return {'id': document_id, 'version_id': version_id, 'duplicate': duplicate}


@router.post('/documents', dependencies=[Depends(require_csrf)])
async def upload(request: Request, response: Response, user: AdminUser, file: UploadFile = File(...)):
    return await upload_version(request, response, user, file)


@router.post('/documents/{document_id}/versions', dependencies=[Depends(require_csrf)])
async def update(document_id: str, request: Request, response: Response, user: AdminUser, file: UploadFile = File(...)):
    return await upload_version(request, response, user, file, document_id)


@router.patch('/documents/{document_id}', dependencies=[Depends(require_csrf)])
def toggle(document_id: str, body: DocumentPatch, request: Request, user: AdminUser):
    service = request.app.state.knowledge
    with service._lock, service.database.session() as db:
        row = service.owned_document(db, document_id)
        row.enabled = body.enabled
        db.commit()
    return {'ok': True}


@router.post('/documents/{document_id}/retry', dependencies=[Depends(require_csrf)])
def retry(document_id: str, request: Request, user: AdminUser):
    service = request.app.state.knowledge
    with service._lock, service.database.session() as db:
        service.owned_document(db, document_id)
        row = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == document_id)
                        .order_by(DocumentVersion.number.desc()).limit(1))
        if not row or row.status != 'failed':
            raise HTTPException(409, '只有失败版本可以重试')
        row.status, row.error_code = 'queued', None
        db.commit()
    return {'ok': True}


@router.get('/sources/{version_id}/{chunk_id}')
def source(version_id: str, chunk_id: str, request: Request, user: CurrentUser):
    return request.app.state.knowledge.source(version_id, chunk_id)
