"""FastAPI application: chat API, tickets API, KB search and static UI."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import llm
from .db import TicketStore, ticket_to_text
from .engine import TroubleshootingEngine
from .flows import CATEGORY_LABELS
from .kb import KnowledgeBase
from .rag import MAX_UPLOAD_BYTES, DocumentIndex, UploadError

STATIC = Path(__file__).resolve().parent / "static"


class ChatIn(BaseModel):
    message: str = Field(..., max_length=2000)
    session_id: str | None = None
    user: str | None = None


class StatusIn(BaseModel):
    status: str


class AskIn(BaseModel):
    question: str = Field(..., min_length=2, max_length=1000)
    k: int = Field(3, ge=1, le=8)


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(title="AI Tech Support Assistant", version="1.0.0",
                  description="Guided IT troubleshooting with KB retrieval and ticket escalation.")
    kb = KnowledgeBase()
    store = TicketStore(db_path)
    docs = DocumentIndex(kb, store.path)
    engine = TroubleshootingEngine(kb, store, docs)
    app.state.engine, app.state.store, app.state.kb, app.state.docs = engine, store, kb, docs

    @app.get("/api/health")
    def health():
        return {"status": "ok", "articles": len(kb.articles), "documents": len(docs.list_documents()),
                "chunks": len(docs.chunks), "llm_enabled": llm.llm_enabled()}

    @app.post("/api/chat")
    def chat(body: ChatIn):
        return engine.handle(body.message, body.session_id, body.user)

    @app.get("/api/categories")
    def categories():
        return CATEGORY_LABELS

    @app.get("/api/kb")
    def kb_list():
        return [a.summary() for a in kb.articles]

    @app.get("/api/kb/search")
    def kb_search(q: str, k: int = 3):
        return [{**a.summary(), "score": round(s, 3)} for a, s in kb.search(q, k=k)]

    @app.get("/api/kb/{article_id}")
    def kb_get(article_id: str):
        a = kb.by_id.get(article_id)
        if not a:
            raise HTTPException(404, "Article not found")
        return {**a.summary(), "body": a.body, "steps": a.steps}

    # ---------------------------------------------------------------- RAG documents
    @app.get("/api/documents")
    def documents():
        return docs.list_documents()

    @app.post("/api/documents", status_code=201)
    async def upload_document(file: UploadFile = File(...), title: str | None = Form(None)):
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        try:
            return docs.add_document(file.filename or "document.txt", data, title)
        except UploadError as e:
            raise HTTPException(400, str(e))

    @app.patch("/api/documents/{doc_id}")
    def document_status(doc_id: str, body: StatusIn):
        if not docs.get_document(doc_id):
            raise HTTPException(404, "Uploaded document not found")
        try:
            return docs.set_status(doc_id, body.status)
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.delete("/api/documents/{doc_id}", status_code=204)
    def delete_document(doc_id: str):
        if not docs.delete_document(doc_id):
            raise HTTPException(404, "Uploaded document not found")

    @app.post("/api/ask")
    def ask(body: AskIn):
        """Ask the documentation directly: retrieve top chunks and return a cited answer."""
        result = docs.answer(body.question, k=body.k)
        if not result["answer"]:
            result["answer"] = "I couldn't find anything relevant in the approved or uploaded documentation."
        return result

    @app.get("/api/tickets")
    def tickets(status: str | None = None):
        return store.list(status)

    @app.get("/api/tickets/{ticket_id}")
    def ticket(ticket_id: str):
        t = store.get(ticket_id)
        if not t:
            raise HTTPException(404, "Ticket not found")
        return t

    @app.get("/api/tickets/{ticket_id}/text", response_class=PlainTextResponse)
    def ticket_text(ticket_id: str):
        t = store.get(ticket_id)
        if not t:
            raise HTTPException(404, "Ticket not found")
        return ticket_to_text(t)

    @app.patch("/api/tickets/{ticket_id}")
    def ticket_status(ticket_id: str, body: StatusIn):
        if not store.get(ticket_id):
            raise HTTPException(404, "Ticket not found")
        try:
            return store.update_status(ticket_id, body.status)
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/tickets", include_in_schema=False)
    def tickets_page():
        return FileResponse(STATIC / "tickets.html")

    @app.get("/knowledge", include_in_schema=False)
    def knowledge_page():
        return FileResponse(STATIC / "knowledge.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
