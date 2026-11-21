import hashlib
import json
from pathlib import Path
from src.router.source_verifier import SourceVerifier, explicit_year


def _repo(root):
    data = root / "data/raw/uet/markdown/2026"
    data.mkdir(parents=True)
    sample = data / "quyche.md"
    sample.write_text("Quy định học phí riêng 2026", encoding="utf-8")
    digest = hashlib.sha256(sample.read_bytes()).hexdigest()
    vers = root / "data/versioning"
    vers.mkdir()
    rec = {"doc_id": "doc2026", "content_sha256": digest,
           "academic_year": "2026-2027", "review_status": "verified_against_source"}
    (vers / "reviewed_documents.jsonl").write_text(json.dumps(rec) + "\n")
    (vers / "publication_holds.jsonl").write_text("")
    return root


def test_explicit_year_unambiguous():
    assert explicit_year("Quy định năm 2026?") == 2026
    assert explicit_year("So sánh 2023 và 2026") is None
    assert explicit_year("mới nhất") is None
    assert explicit_year("học phí QH-2022 năm 2026") == 2026
    assert explicit_year("Học phí năm học 2025-2026") == 2025
    assert explicit_year("Học phí QH-2022") is None


def test_approved_source_sha_year(tmp_path):
    v = SourceVerifier(_repo(tmp_path / "repo"))
    r = v.check(["doc2026"], "Mức học phí năm 2026?")
    assert r["sha_verified"] and r["year_verified"]


def test_wrong_year_is_not_valid(tmp_path):
    v = SourceVerifier(_repo(tmp_path / "repo"))
    assert not v.check(["doc2026"], "Mức học phí năm 2023?")["year_verified"]


def test_implicit_current_cannot_certify_year(tmp_path):
    v = SourceVerifier(_repo(tmp_path / "repo"))
    assert not v.check(["doc2026"], "Học phí mới nhất?")["year_verified"]


def test_source_changed_must_fail(tmp_path):
    root = _repo(tmp_path / "repo")
    (root / "data/raw/uet/markdown/2026/quyche.md").write_text("Thay đổi", encoding="utf-8")
    assert not SourceVerifier(root).check(["doc2026"], "Học phí 2026?")["sha_verified"]


def test_hold_blocks(tmp_path):
    root = _repo(tmp_path / "repo")
    (root / "data/versioning/publication_holds.jsonl").write_text(json.dumps({"doc_id": "doc2026"}))
    result = SourceVerifier(root).check(["doc2026"], "Học phí năm 2026?")
    assert result["has_hold"]
    assert not result["sha_verified"]
