from src.api.academic_dispatch import build_dispatch


def test_integration_with_verified_source(tmp_path):
    import hashlib, json
    doc_dir = tmp_path / "data/raw/uet/markdown/2026"
    doc_dir.mkdir(parents=True)
    raw = doc_dir / "tuition.md"
    raw.write_text("Mức học phí 2026: 123 đồng", encoding="utf-8")
    registry = tmp_path / "data/versioning"
    registry.mkdir(parents=True)
    record = {"doc_id": "tuition26", "review_status": "verified_against_source",
              "academic_year": "2026-2027", "content_sha256": hashlib.sha256(raw.read_bytes()).hexdigest()}
    (registry / "reviewed_documents.jsonl").write_text(json.dumps(record) + "\n")
    sel = build_dispatch(tmp_path, lambda _: {"predicted_answer": "123 đồng", "cited_doc_ids": ["tuition26"]})
    result = sel.answer("Mức học phí năm 2026?")
    assert result["selected_engine"] == "chrono_rag"
    assert result["answer"] == "123 đồng"
    assert not result["authoritative_regulation_answer"]  # entailment not certified


def test_missing_retrieval_fails_closed(tmp_path):
    sel = build_dispatch(tmp_path, lambda _: {"predicted_answer": "maybe", "cited_doc_ids": []})
    assert sel.answer("Học phí năm 2025?")["selected_engine"] == "abstain"
