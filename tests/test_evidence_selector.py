from src.router.evidence_selector import Candidate, HybridDispatch, classify_question, safe_select


def rag(answer="Theo văn bản chính thức", verified=True, year=True):
    return Candidate("chrono_rag", answer, "RETRIEVED",
                     ("doc-2026",), verified, year, True)


def lora(answer="Có thể lập kế hoạch ôn tập", qualified=False):
    return Candidate("continual_lora", answer, "LIVE_PEFT_GENERATION",
                     capability_qualified=qualified)


def test_fee_requires_sources():
    assert classify_question("Học phí năm 2026 bao nhiêu tiền?")["requires_evidence"]


def test_regulation_procedure_requires_sources():
    assert classify_question("Quy trình bảo lưu kết quả học tập ở UET thế nào?")["requires_evidence"]


def test_explainer_advice_low_risk():
    assert classify_question("Cho mình cách học hiệu quả hơn?")["allow_lora_advice"]


def test_regulation_cannot_fall_back_to_lora():
    ans = safe_select("Học phí năm 2026 là bao nhiêu?", rag=None,
                      lora=lora("1.500.000 đồng"))
    assert ans["selected_engine"] == "abstain"
    assert not ans["authoritative_regulation_answer"]


def test_dont_trust_unverified_rag_citations():
    ans = safe_select("Điều kiện tốt nghiệp năm 2025 là gì?", rag=rag(verified=False),
                      lora=lora())
    assert ans["selected_engine"] == "abstain"


def test_verified_rag_wins_factual():
    ans = safe_select("Mức học bổng năm 2026?", rag=rag(), lora=lora("Sai"))
    assert ans["selected_engine"] == "chrono_rag"
    assert ans["authoritative_regulation_answer"]


def test_lora_unqualified_advice_blocked():
    ans = safe_select("Mình muốn cách học hiệu quả", lora=lora())
    assert ans["selected_engine"] == "abstain"
    assert not ans["authoritative_regulation_answer"]

def test_lora_qualified_non_regulatory_advice_only():
    ans = safe_select("Mình muốn cách học hiệu quả", lora=lora(qualified=True))
    assert ans["selected_engine"] == "continual_lora"
    assert not ans["authoritative_regulation_answer"]
    factual = safe_select("Mức học phí năm 2026?", lora=lora(qualified=True))
    assert factual["selected_engine"] == "abstain"


def test_fake_lora_is_not_real_inference():
    fake = Candidate("continual_lora", "fake cached", "VERIFIED_BENCHMARK_PREDICTION")
    ans = safe_select("Mình muốn cách học hiệu quả", lora=fake)
    assert ans["selected_engine"] == "abstain"


def test_hold_never_calls_engines():
    called = []
    sel = HybridDispatch(lambda q: called.append("rag"), lambda q: called.append("lora"))
    ans = sel.answer("Xin cứu xét miễn học phí", held=True, compare=True)
    assert not called
    assert ans["selected_engine"] == "abstain"


def test_unknown_question_fails_closed():
    assert safe_select("Phân tích sự thay đổi", rag=None, lora=lora())["selected_engine"] == "abstain"


def test_comparison_keeps_both_and_flags_no_truth_oracle():
    sel = HybridDispatch(lambda q: rag(), lambda q: lora())
    ans = sel.answer("Học phí năm 2025?", compare=True)
    assert ans["selected_engine"] == "chrono_rag"
    assert ans["comparison"]["lora"]["engine_mode"] == "LIVE_PEFT_GENERATION"
    assert ans["comparison"]["winner_validated_by_benchmark"] is False


def test_rag_error_does_not_switch_to_lora_on_facts():
    def fail(_q):
        raise RuntimeError("missing RAG corpus")
    ans = HybridDispatch(fail, lambda q: lora()).answer("Học phí năm 2026 là bao nhiêu?", compare=True)
    assert ans["selected_engine"] == "abstain"


def test_unknown_no_lora_execution():
    called = []
    HybridDispatch(None, lambda q: called.append(q)).answer("Xin hỏi một điều bất kỳ")
    assert not called
