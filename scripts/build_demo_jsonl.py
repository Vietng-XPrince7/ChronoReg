"""CLI helper to regenerate data/demo/{courses,students,grades}.jsonl (30 students x 26 courses)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.demo.class_roster import ClassRosterIndex, export_jsonl_database  # noqa: E402


if __name__ == "__main__":
    data = export_jsonl_database(ROOT / "data" / "demo", seed=42)
    idx = ClassRosterIndex(ROOT / "data" / "demo")
    print(f"Đã xuất JSONL tại data/demo/: {len(data['sinh_vien'])} SV × {len(data['danh_muc_mon_hoc'])} môn.")
    print("Top 3 môn trượt:", idx.top_failed_courses(3))
    kkht = idx.filter_scholarship_candidates()
    print(f"Xét KKHT: {len(kkht['du_dieu_kien'])} đạt, {len(kkht['truot_vi_drl'])} trượt vì ĐRL.")
