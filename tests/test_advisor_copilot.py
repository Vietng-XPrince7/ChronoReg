"""Unit & integration tests for UET Academic Advisor Copilot (30-student x 26-course JSONL)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.demo.class_roster import (
    CLASS_METADATA,
    ClassRosterIndex,
    analyze_class_roster,
    format_roster_facts_text,
    generate_class_roster,
)
from src.scraper.uet_latest import UETLatestNewsScraper


class TestClassRosterJSONL:
    def test_generate_roster_writes_3_jsonl_files_for_30_students(self, tmp_path):
        roster = generate_class_roster(seed=42, save_dir=tmp_path)
        assert (tmp_path / "courses.jsonl").is_file()
        assert (tmp_path / "students.jsonl").is_file()
        assert (tmp_path / "grades.jsonl").is_file()

        courses_lines = [l for l in (tmp_path / "courses.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        students_lines = [l for l in (tmp_path / "students.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        grades_lines = [l for l in (tmp_path / "grades.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

        assert len(courses_lines) == 26
        assert len(students_lines) == 30
        assert len(grades_lines) == 30 * 26  # 780

        assert roster["class_id"] == "QH-2024-I/CQ-C-CLC1"
        assert roster["advisor"] == "Ths. Phạm Thị Quỳnh Trang"
        assert len(roster["students"]) == 30
        for s in roster["students"]:
            assert s["class_id"] == CLASS_METADATA["class_id"]
            assert s["cohort"] == CLASS_METADATA["cohort"]
            assert s["major"] == CLASS_METADATA["major"]

    def test_class_roster_index_queries_and_default_scenarios(self, tmp_path):
        roster = generate_class_roster(seed=42, save_dir=tmp_path)
        idx = ClassRosterIndex(tmp_path)

        st1 = idx.get_student("24020001")
        assert st1 is not None and st1["ho_ten"] == "Sơn Tùng MTP"
        assert len(st1["bang_diem"]) == 26

        kkht = idx.filter_scholarship_candidates(min_gpa=3.2, min_drl=80, hoc_ky="2025.1")
        assert len(kkht["du_dieu_kien"]) == 6
        assert len(kkht["truot_vi_drl"]) == 2
        trapped_names = {s["ho_ten"] for s in kkht["truot_vi_drl"]}
        assert trapped_names == {"Phan Mạnh Quỳnh", "Nguyễn Trúc Nhân"}

        top_failed = idx.top_failed_courses(3)
        assert len(top_failed) == 3
        assert top_failed[0]["so_luot_truot"] >= top_failed[1]["so_luot_truot"]

        a = roster["analysis"]
        assert a["total_students"] == 30
        assert a["scholarship_priority_count"] == 6
        assert a["scholarship_trapped_count"] == 2
        assert a["warning_risk_count"] == 4
        assert a["overload_applicants_count"] == 2

    def test_regenerate_randomizes_scores_keeping_30_student_identities(self, tmp_path):
        r1 = generate_class_roster(seed=101, save_dir=tmp_path / "d1")
        r2 = generate_class_roster(seed=202, save_dir=tmp_path / "d2")
        ids1 = [s["student_id"] for s in r1["students"]]
        ids2 = [s["student_id"] for s in r2["students"]]
        assert ids1 == ids2 and len(ids1) == 30
        assert [s["gpa_semester"] for s in r1["students"]] != [s["gpa_semester"] for s in r2["students"]]
        for r in (r1, r2):
            a = analyze_class_roster(r)
            assert a["total_students"] == 30
            assert a["warning_risk_count"] >= 4

    def test_format_roster_facts_text_includes_artists_and_failed_courses(self, tmp_path):
        roster = generate_class_roster(seed=42, save_dir=tmp_path)
        txt = format_roster_facts_text(roster, "xét học bổng KKHT và trượt vì điểm rèn luyện")
        assert "Sơn Tùng MTP" in txt
        assert "Phan Mạnh Quỳnh" in txt
        txt_fail = format_roster_facts_text(roster, "Lớp trượt nhiều môn nào nhất?")
        assert "lượt trượt" in txt_fail


class TestUETLatestScraper:
    def test_scrape_latest_parses_page1_html_and_caches(self, tmp_path):
        html_student = """
        <html><body><main>
          <article class="post">
            <h2 class="entry-title"><a href="https://uet.edu.vn/hb-1">Thông báo xét học bổng KKHT kỳ I 2026</a></h2>
            <time class="entry-date">25/11/2026</time>
            <div class="entry-summary"><p>Sinh viên cần đạt GPA và ĐRL từ loại Khá trở lên.</p></div>
          </article>
          <article class="post">
            <h2 class="entry-title"><a href="/hb-2">Học bổng tài trợ doanh nghiệp CNTT K68</a></h2>
            <time class="entry-date">24/11/2026</time>
            <div class="entry-summary"><p>Hạn nộp hồ sơ trực tuyến trước ngày 05/12/2026.</p></div>
          </article>
        </main></body></html>
        """
        html_edu = """
        <html><body><main>
          <article class="post">
            <h2 class="entry-title"><a href="https://uet.edu.vn/dt-1">Kế hoạch đăng ký học vượt 24 tín chỉ</a></h2>
            <time class="entry-date">23/11/2026</time>
            <div class="entry-summary"><p>Sinh viên có CPA >= 2.50 không nợ môn được đăng ký tối đa 24 TC.</p></div>
          </article>
        </main></body></html>
        """

        def handler(request: httpx.Request) -> httpx.Response:
            u = str(request.url)
            if "tin-sinh-vien" in u:
                return httpx.Response(200, text=html_student)
            if "dao-tao" in u:
                return httpx.Response(200, text=html_edu)
            return httpx.Response(404)

        cache_file = tmp_path / "news_cache.json"
        scraper = UETLatestNewsScraper(
            cache_path=cache_file,
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        res = scraper.scrape_latest(limit=10)
        assert res["source"] == "live_scrape"
        assert res["count"] == 3
        assert res["articles"][0]["date"] == "25/11/2026"
        assert res["articles"][1]["url"] == "https://uet.edu.vn/hb-2"
        assert cache_file.is_file()

    def test_scrape_latest_falls_back_to_cache_when_offline(self, tmp_path):
        cache_file = tmp_path / "news_cache.json"
        cached_payload = {
            "fetched_at": "2026-11-25T10:00:00+07:00",
            "source": "live_scrape",
            "articles": [
                {
                    "title": "Tin cached offline UET",
                    "date": "25/11/2026",
                    "url": "https://uet.edu.vn/cached-1",
                    "summary": "Nội dung đã lưu từ lần cào trước.",
                    "category": "Tin sinh viên",
                }
            ],
        }
        cache_file.write_text(json.dumps(cached_payload, ensure_ascii=False), encoding="utf-8")

        def fail_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("No internet", request=request)

        scraper = UETLatestNewsScraper(
            cache_path=cache_file,
            http_client=httpx.Client(transport=httpx.MockTransport(fail_handler)),
        )
        res = scraper.scrape_latest(limit=10)
        assert res["source"] == "cache_fallback"
        assert res["count"] == 1
        assert res["articles"][0]["title"] == "Tin cached offline UET"


class TestAdvisorEndpointsAndPreCheck:
    def test_roster_endpoints_and_regenerate(self, monkeypatch, tmp_path):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from src.api import studenthub_server as server

        monkeypatch.setattr("src.demo.class_roster.DEFAULT_DEMO_DIR", tmp_path)
        generate_class_roster(seed=42, save_dir=tmp_path)

        with TestClient(server.app) as client:
            r1 = client.get("/api/class-roster")
            assert r1.status_code == 200
            d1 = r1.json()
            assert len(d1["students"]) == 30
            assert d1["class_id"] == "QH-2024-I/CQ-C-CLC1"
            assert len(d1["top_failed_courses"]) > 0

            r2 = client.post("/api/class-roster/regenerate", json={"seed": 777})
            assert r2.status_code == 200
            d2 = r2.json()
            assert len(d2["students"]) == 30
            assert d2["seed"] == 777
            assert [s["gpa_semester"] for s in d2["students"]] != [s["gpa_semester"] for s in d1["students"]]

    def test_scrape_latest_endpoint(self, monkeypatch, tmp_path):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from src.api import studenthub_server as server

        html = """<html><body><article><h2 class="entry-title"><a href="https://uet.edu.vn/x1">Thông báo UET mới nhất 2026</a></h2><time>26/11/2026</time><p>Chi tiết thông báo.</p></article></body></html>"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=html)

        mock_scraper = UETLatestNewsScraper(
            cache_path=tmp_path / "cache.json",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        monkeypatch.setattr(server, "_news_scraper", mock_scraper)

        with TestClient(server.app) as client:
            r_get = client.get("/api/latest-news")
            assert r_get.status_code == 200
            assert len(r_get.json()["articles"]) >= 1

            r_post = client.post("/api/scrape-latest")
            assert r_post.status_code == 200
            payload = r_post.json()
            assert payload["source"] == "live_scrape"
            assert payload["fetched_at"]
            assert payload["articles"][0]["title"] == "Thông báo UET mới nhất 2026"

    def test_advisor_6_sample_questions_and_deterministic_precheck(self):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from src.api import studenthub_server as server

        with TestClient(server.app) as client:
            samples = client.get("/api/sample-questions").json()
            assert len(samples) == 6

            # Q1: KKHT + low DRL trap
            r1 = client.post("/api/chat", json={"question": samples[0]["question"]}).json()
            assert "Sơn Tùng MTP" in r1["answer"]
            assert "Phan Mạnh Quỳnh" in r1["answer"]

            # Q2: Academic warning risk
            r2 = client.post("/api/chat", json={"question": samples[1]["question"]}).json()
            assert "Nguyễn Quốc Thiên" in r2["answer"]
            assert "BTS" in r2["answer"]

            # Q3: Procedural LoRA guidance (never empty / never "Không tìm thấy")
            r3 = client.post("/api/chat", json={"question": samples[2]["question"]}).json()
            assert "Không tìm thấy thông tin" not in r3["answer"]
            assert len(r3["answer"]) > 50

            # Q4: Overload 24 credits
            r4 = client.post("/api/chat", json={"question": samples[3]["question"]}).json()
            assert "Nguyễn Thúc Thùy Tiên" in r4["answer"]
            assert "Trần Thành Đạt" in r4["answer"]

            # Q5: Latest news + class check
            r5 = client.post("/api/chat", json={"question": samples[4]["question"]}).json()
            assert "Tin tức Trang 1 UET" in r5["routing"]["detected_signals"]
            assert "Sơn Tùng MTP" in r5["answer"] or "24020" in r5["answer"]

            # Q6: Fee comparison + exception -> Safety Gate RED
            r6 = client.post("/api/chat", json={"question": samples[5]["question"]}).json()
            assert r6["routing"]["risk_tier"] == "RED"
            assert r6["routing"]["actual_engine_used"] == "safety_gate_red"

            # Compare endpoint also works with advisor roster questions
            cmp_res = client.post("/api/compare", json={"question": samples[0]["question"]}).json()
            assert "Sơn Tùng MTP" in cmp_res["chrono_rag"]["answer"]
            assert "Sơn Tùng MTP" in cmp_res["continual_lora"]["answer"]

    def test_ask_ai_single_student_scoping_three_mssvs(self):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from src.api import studenthub_server as server
        from src.demo.class_roster import NGHE_SI_30

        id_to_name = {sid: sname for sid, sname, _ in NGHE_SI_30}
        targets = [
            ("24020001", "Sơn Tùng MTP"),
            ("24020007", "Phan Mạnh Quỳnh"),
            ("24020027", "Nguyễn Quốc Thiên"),
        ]

        with TestClient(server.app) as client:
            for mssv, name in targets:
                res = client.post(
                    "/api/chat",
                    json={
                        "question": f"Kiểm tra tình trạng học tập và điều kiện xét học bổng, học vượt của sinh viên {name} ({mssv})?",
                        "mssv": mssv,
                    },
                )
                assert res.status_code == 200
                data = res.json()
                ans = data["answer"]
                assert mssv in ans
                assert name in ans
                for other_id, other_name, _ in NGHE_SI_30:
                    if other_id != mssv:
                        assert other_id not in ans, f"Leaked {other_id} in single-student reply for {mssv}"
                        assert other_name not in ans, f"Leaked {other_name} in single-student reply for {mssv}"

            # Name-only query without explicit mssv field should also isolate single student
            res_name = client.post(
                "/api/chat",
                json={"question": "Em Nguyễn Hà Anh Tuấn học thế nào?"},
            )
            assert res_name.status_code == 200
            data_name = res_name.json()
            assert data_name["metadata"]["advisor_category"] == "STUDENT_STATUS"
            assert "24020004" in data_name["answer"]
            assert "Nguyễn Hà Anh Tuấn" in data_name["answer"]
            for other_id, other_name, _ in NGHE_SI_30:
                if other_id != "24020004":
                    assert other_id not in data_name["answer"]
                    assert other_name not in data_name["answer"]

            assert id_to_name["24020004"] == "Nguyễn Hà Anh Tuấn"

    def test_advisor_name_updates_live_without_server_restart(self, monkeypatch, tmp_path):
        pytest.importorskip("fastapi")
        import os
        import time
        from fastapi.testclient import TestClient
        from src.api import studenthub_server as server
        from src.demo.class_roster import invalidate_roster_cache

        monkeypatch.setattr("src.demo.class_roster.DEFAULT_DEMO_DIR", tmp_path)
        invalidate_roster_cache()
        generate_class_roster(seed=42, save_dir=tmp_path)

        with TestClient(server.app) as client:
            r1 = client.get("/api/class-roster")
            assert r1.status_code == 200
            assert r1.json()["advisor"] == "Ths. Phạm Thị Quỳnh Trang"

            # Modify co_van_hoc_tap directly in students.jsonl while server stays running
            students_path = tmp_path / "students.jsonl"
            rows = [json.loads(line) for line in students_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            for row in rows:
                row["co_van_hoc_tap"] = "TS. Trần Minh Hiếu"
            students_path.write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                encoding="utf-8",
            )
            # Ensure filesystem mtime advances even on fast test runs
            stat = students_path.stat()
            os.utime(students_path, (stat.st_atime + 2, stat.st_mtime + 2))

            r2 = client.get("/api/class-roster")
            assert r2.status_code == 200
            assert r2.json()["advisor"] == "TS. Trần Minh Hiếu"

            chat_res = client.post(
                "/api/chat",
                json={"question": "Tóm tắt lớp có mấy sinh viên đủ học bổng KKHT?"},
            )
            assert chat_res.status_code == 200
            assert "Phạm Thị Quỳnh Trang" not in chat_res.json()["answer"]
            assert "Nguyễn Thị Lan" not in chat_res.json()["answer"]
