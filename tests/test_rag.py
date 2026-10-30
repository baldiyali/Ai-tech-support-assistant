"""Document upload, chunking, retrieval and grounded (cited) answers."""
from pathlib import Path

import pytest

from app.kb import KnowledgeBase
from app.rag import DocumentIndex, UploadError, chunk_text, extract_text

FIXTURE_PDF = Path(__file__).parent / "fixtures" / "acme-laserpro-400-manual.pdf"
MANUAL_MD = b"""# Contoso Door Badge Reader Guide

## Badge not accepted
If the badge reader blinks red three times, the badge has expired. Ask the office manager to re-enable
the badge in the Contoso Access portal under People > Badges.

## Reader offline
If the reader display shows OFFLINE, check the PoE switch port labelled DOOR-1 in the comms cupboard.
"""


@pytest.fixture
def index():
    return DocumentIndex(KnowledgeBase())


def test_seeded_kb_is_indexed_as_approved(index):
    docs = index.list_documents()
    assert len(docs) == len(index.kb.articles)
    assert all(d["status"] == "approved" and d["origin"] == "seed" for d in docs)
    assert all(c["status"] == "approved" for c in index.chunks)


def test_chunking_tracks_headings_and_size():
    text = "# Title\n\n## Section A\n\n" + "\n\n".join(f"Paragraph {i} " + "word " * 40 for i in range(6))
    chunks = chunk_text(text, "p. 2", size=500)
    assert len(chunks) > 1
    assert all(len(c) <= 600 for c, _ in chunks)
    assert chunks[0][1] == "p. 2 · Section A"


def test_extract_rejects_bad_files():
    with pytest.raises(UploadError):
        extract_text("virus.exe", b"MZ...")
    with pytest.raises(UploadError):
        extract_text("empty.txt", b"")
    with pytest.raises(UploadError):
        extract_text("broken.pdf", b"not really a pdf")


def test_pdf_extraction_keeps_page_numbers():
    segments = extract_text("manual.pdf", FIXTURE_PDF.read_bytes())
    assert segments[0][1] == "p. 1" and "E-49" in segments[0][0]


def test_uploaded_markdown_is_retrieved_and_cited(index):
    doc = index.add_document("badge-reader.md", MANUAL_MD)
    assert doc["status"] == "uploaded" and doc["n_chunks"] >= 2
    hits = index.search("badge reader blinks red")
    assert hits[0]["doc_id"] == doc["id"] and hits[0]["status"] == "uploaded"
    ans = index.answer("my badge reader blinks red three times")
    assert ans["mode"] == "extractive" and "[1]" in ans["answer"] and "expired" in ans["answer"]
    assert ans["sources"][0]["title"] == "Badge Reader" and ans["sources"][0]["section"] == "Badge not accepted"


def test_approve_and_delete(index):
    doc = index.add_document("badge.txt", MANUAL_MD.replace(b"#", b""), title="Badge guide")
    assert index.set_status(doc["id"], "approved")["status"] == "approved"
    assert index.search("badge reader offline")[0]["status"] == "approved"
    assert index.delete_document(doc["id"]) is True
    assert all(c["doc_id"] != doc["id"] for c in index.chunks)
    assert index.delete_document(doc["id"]) is False


def test_error_code_query_finds_uploaded_pdf(index):
    index.add_document("acme.pdf", FIXTURE_PDF.read_bytes(), title="Acme LaserPro 400 manual")
    ans = index.answer("printer shows error E-49")
    assert ans["sources"][0]["title"] == "Acme LaserPro 400 manual"
    assert ans["sources"][0]["section"] == "p. 1"
    assert "fuser" in ans["answer"].lower()


def test_upload_api_and_grounded_chat(client, chat):
    with FIXTURE_PDF.open("rb") as f:
        r = client.post("/api/documents", files={"file": ("acme.pdf", f, "application/pdf")},
                        data={"title": "Acme LaserPro 400 manual"})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["status"] == "uploaded" and doc["n_chunks"] >= 1
    docs = client.get("/api/documents").json()
    assert docs[0]["id"] == doc["id"] and any(d["status"] == "approved" for d in docs)

    # standalone "ask the docs"
    a = client.post("/api/ask", json={"question": "What does error E-49 mean?"}).json()
    assert a["sources"][0]["doc_id"] == doc["id"] and "fuser" in a["answer"].lower()

    # free-form question during troubleshooting is answered from the uploaded manual
    for m in ["printer shows error E-49 and won't print", "Only me", "An error code or warning light",
              "Nothing prints at all", "Desktop", "Windows 11", "I can work around it"]:
        r = chat(m)
    assert r["state"]["phase"] == "steps"
    assert any(s["doc_id"] == doc["id"] for s in r["sources"])
    r = chat("What does E-49 mean?")
    assert r["state"]["phase"] == "steps" and r["state"]["step"] == 1
    assert r["sources"][0]["doc_id"] == doc["id"] and r["sources"][0]["status"] == "uploaded"
    assert "fuser" in r["reply"].lower() and "Back to **step 1" in r["reply"]

    # escalated ticket records which documents were cited
    run_to_ticket = ["escalate", "I don't know"]
    for m in run_to_ticket:
        r = chat(m)
    assert any(s["doc_id"] == doc["id"] for s in r["ticket"]["sources"])

    # approve, then delete
    assert client.patch(f"/api/documents/{doc['id']}", json={"status": "approved"}).json()["status"] == "approved"
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 404


def test_upload_api_rejects_unsupported_type(client):
    r = client.post("/api/documents", files={"file": ("setup.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 400 and "Unsupported" in r.json()["detail"]
