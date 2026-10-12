"""Versioned ingestion; activation is atomic, historical files are retained."""
import asyncio
import contextlib
import hashlib
from pathlib import Path
import threading
from fastapi import HTTPException
from sqlalchemy import func, select
from backend.models import DocumentVersion, KnowledgeDocument, new_id


class KnowledgeService:
    def __init__(self, database, settings, embedding=None, collection_name='knowledge_v1'):
        self.database, self.settings = database, settings
        self.embedding, self.collection_name = embedding, collection_name
        self._store = None
        self._lock = threading.RLock()
        self.worker = None

    @property
    def store(self):
        if self._store is None:
            from langchain_chroma import Chroma
            from model.factory import build_embedding_model
            self._store = Chroma(collection_name=self.collection_name,
                embedding_function=self.embedding or build_embedding_model(),
                persist_directory=str(self.settings.runtime_dir / 'vectors'))
        return self._store

    def owned_document(self, db, document_id):
        row = db.get(KnowledgeDocument, document_id)
        if not row:
            raise HTTPException(404, '文档不存在')
        return row

    def upload(self, filename, content, user_id, document_id=None):
        suffix = Path(filename or '').suffix.lower()
        if suffix not in {'.txt', '.pdf'}:
            raise HTTPException(422, '仅支持 TXT 或 PDF')
        if not content or len(content) > 10 * 1024 * 1024:
            raise HTTPException(413, '文件为空或超过 10 MiB')
        digest = hashlib.sha256(content).hexdigest()
        with self._lock, self.database.session() as db:
            if document_id:
                document = self.owned_document(db, document_id)
                existing = db.scalar(select(DocumentVersion).where(
                    DocumentVersion.document_id == document.id, DocumentVersion.content_hash == digest))
                if existing:
                    return document.id, existing.id, True
                if db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == document.id,
                        DocumentVersion.status.in_(['queued', 'processing']))):
                    raise HTTPException(409, '文档正在处理，请稍后更新')
            else:
                document = KnowledgeDocument(title=Path(filename.replace('\\', '/')).name[:200], uploaded_by=user_id)
                db.add(document)
                db.flush()
            number = (db.scalar(select(func.max(DocumentVersion.number)).where(
                DocumentVersion.document_id == document.id)) or 0) + 1
            version_id = new_id()
            directory = self.settings.runtime_dir / 'files'
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f'{version_id}{suffix}'
            path.write_bytes(content)
            db.add(DocumentVersion(id=version_id, document_id=document.id, number=number,
                                   content_hash=digest, path=str(path)))
            db.commit()
            return document.id, version_id, False

    def process_queued(self):
        with self._lock:
            with self.database.session() as db:
                ids = list(db.scalars(select(DocumentVersion.id).where(DocumentVersion.status == 'queued')))
            for version_id in ids:
                self._process(version_id)

    def _process(self, version_id):
        with self.database.session() as db:
            version = db.get(DocumentVersion, version_id)
            if not version or version.status != 'queued':
                return
            version.status, version.error_code = 'processing', None
            db.commit()
            path, document_id = Path(version.path), version.document_id
        try:
            from langchain_core.documents import Document
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            if path.suffix == '.txt':
                pages = [Document(page_content=path.read_text(encoding='utf-8'), metadata={'page': -1})]
            else:
                from pypdf import PdfReader
                pages = [Document(page_content=page.extract_text() or '', metadata={'page': i + 1})
                         for i, page in enumerate(PdfReader(str(path)).pages)]
            if not any(page.page_content.strip() for page in pages):
                raise ValueError('EMPTY_TEXT')
            from utils.config_handler import chroma_conf
            splitter = RecursiveCharacterTextSplitter(chunk_size=chroma_conf['chunk_size'],
                chunk_overlap=chroma_conf['chunk_overlap'], separators=chroma_conf['separators'])
            chunks = splitter.split_documents(pages)
            if not chunks:
                raise ValueError('EMPTY_TEXT')
            ids = []
            for index, chunk in enumerate(chunks):
                chunk_id = f'{version_id}-{index}'
                ids.append(chunk_id)
                chunk.metadata.update(document_id=document_id, version_id=version_id,
                                      chunk_id=chunk_id, visibility='employees')
            self.store.add_documents(chunks, ids=ids)
            from rag.hybrid_retriever import tokenize_zh
            from rank_bm25 import BM25Okapi
            BM25Okapi([tokenize_zh(chunk.page_content) for chunk in chunks])
            with self.database.session() as db:
                version = db.get(DocumentVersion, version_id)
                version.status = 'ready'
                self.owned_document(db, document_id).active_version_id = version_id
                db.commit()
        except Exception as exc:
            with self.database.session() as db:
                version = db.get(DocumentVersion, version_id)
                version.status = 'failed'
                version.error_code = ('INVALID_UTF8' if isinstance(exc, UnicodeDecodeError) else
                    'EMPTY_TEXT' if str(exc) == 'EMPTY_TEXT' else 'INGEST_FAILED')
                db.commit()
            import logging
            logging.getLogger('agent').warning('ingest_failed version=%s code=%s', version_id, version.error_code)

    def retrieve(self, query, k=3):
        with self._lock, self.database.session() as db:
            rows = db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.enabled.is_(True),
                                      KnowledgeDocument.active_version_id.is_not(None))).all()
            active = [row.active_version_id for row in rows]
            if not active:
                return []
            titles = {row.id: row.title for row in rows}
            where = {'version_id': {'$in': active}}
            raw = self.store.get(where=where, include=['documents', 'metadatas'])
            from rag.vector_store import build_retriever
            class SnapshotStore:
                def get(_self, **kwargs):
                    return raw
                def similarity_search_with_score(_self, text, k):
                    return self.store.similarity_search_with_score(text, k=k, filter=where)
            docs = build_retriever(SnapshotStore(), k, 'hybrid').invoke(query)
            return [{'document_id': d.metadata['document_id'], 'version_id': d.metadata['version_id'],
                     'chunk_id': d.metadata['chunk_id'], 'title': titles[d.metadata['document_id']],
                     'page': None if d.metadata.get('page', -1) < 0 else d.metadata['page'],
                     'excerpt': d.page_content[:520]} for d in docs]

    def source(self, version_id, chunk_id):
        with self._lock, self.database.session() as db:
            version = db.get(DocumentVersion, version_id)
            if not version or version.status != 'ready':
                raise HTTPException(404, '引用不存在')
            document = self.owned_document(db, version.document_id)
            raw = self.store.get(ids=[chunk_id], include=['documents', 'metadatas'])
            if not raw['ids'] or raw['metadatas'][0].get('version_id') != version_id:
                raise HTTPException(404, '引用不存在')
            return {'title': document.title, 'content': raw['documents'][0], 'version': version.number,
                    'historical': version_id != document.active_version_id or not document.enabled}

    async def start(self):
        async def loop():
            while True:
                await asyncio.to_thread(self.process_queued)
                await asyncio.sleep(1)
        self.worker = asyncio.create_task(loop())

    async def close(self):
        if self.worker:
            self.worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.worker
