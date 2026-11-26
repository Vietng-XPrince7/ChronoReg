"""30-student x 26-course JSONL class roster, ClassRosterIndex, and deterministic pre-check."""
from __future__ import annotations

import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEMO_DIR = REPO_ROOT / "data" / "demo"

CLASS_METADATA = {
    "class_id": "QH-2024-I/CQ-C-CLC1",
    "class_short": "K69-CNTT1",
    "cohort": "QH-2024 (K69)",
    "major": "Công nghệ Thông tin",
    "program": "Công nghệ Thông tin - CTĐT Chuẩn (QH-2024)",
    "faculty": "Khoa Công nghệ Thông tin",
    "advisor": "Ths. Phạm Thị Quỳnh Trang",
    "semester": "Học kỳ 2025.1 (Năm học 2025-2026)",
    "current_hoc_ky": "2025.1",
    "total_program_credits": 136,
}

# 1. Danh mục 26 môn học chuẩn ngành CNTT - UET (lưu 1 lần duy nhất)
DANH_MUC_MON_HOC: list[dict[str, Any]] = [
    # Học kỳ 2023.1
    {"ma_mon": "MAT1093", "ten_mon": "Đại số", "so_tin_chi": 4, "hoc_ky_chuan": "2023.1"},
    {"ma_mon": "MAT1041", "ten_mon": "Giải tích 1", "so_tin_chi": 4, "hoc_ky_chuan": "2023.1"},
    {"ma_mon": "INT1008", "ten_mon": "Nhập môn lập trình", "so_tin_chi": 3, "hoc_ky_chuan": "2023.1"},
    {"ma_mon": "ELT2035", "ten_mon": "Tín hiệu và hệ thống", "so_tin_chi": 3, "hoc_ky_chuan": "2023.1"},
    {"ma_mon": "PHI1006", "ten_mon": "Triết học Mác - Lênin", "so_tin_chi": 3, "hoc_ky_chuan": "2023.1"},
    # Học kỳ 2023.2
    {"ma_mon": "MAT1042", "ten_mon": "Giải tích 2", "so_tin_chi": 4, "hoc_ky_chuan": "2023.2"},
    {"ma_mon": "EPN1095", "ten_mon": "Vật lý đại cương 1", "so_tin_chi": 3, "hoc_ky_chuan": "2023.2"},
    {"ma_mon": "INT2215", "ten_mon": "Lập trình nâng cao", "so_tin_chi": 4, "hoc_ky_chuan": "2023.2"},
    {"ma_mon": "INT1050", "ten_mon": "Toán học rời rạc", "so_tin_chi": 4, "hoc_ky_chuan": "2023.2"},
    {"ma_mon": "PEC1008", "ten_mon": "Kinh tế chính trị Mác - Lênin", "so_tin_chi": 2, "hoc_ky_chuan": "2023.2"},
    # Học kỳ 2024.1
    {"ma_mon": "INT2204", "ten_mon": "Lập trình hướng đối tượng", "so_tin_chi": 3, "hoc_ky_chuan": "2024.1"},
    {"ma_mon": "INT2210", "ten_mon": "Cấu trúc dữ liệu và giải thuật", "so_tin_chi": 4, "hoc_ky_chuan": "2024.1"},
    {"ma_mon": "INT2212", "ten_mon": "Kiến trúc máy tính", "so_tin_chi": 4, "hoc_ky_chuan": "2024.1"},
    {"ma_mon": "MAT1101", "ten_mon": "Xác suất thống kê", "so_tin_chi": 3, "hoc_ky_chuan": "2024.1"},
    {"ma_mon": "POL1001", "ten_mon": "Tư tưởng Hồ Chí Minh", "so_tin_chi": 2, "hoc_ky_chuan": "2024.1"},
    # Học kỳ 2024.2
    {"ma_mon": "INT2214", "ten_mon": "Nguyên lý hệ điều hành", "so_tin_chi": 4, "hoc_ky_chuan": "2024.2"},
    {"ma_mon": "INT2211", "ten_mon": "Cơ sở dữ liệu", "so_tin_chi": 4, "hoc_ky_chuan": "2024.2"},
    {"ma_mon": "INT2213", "ten_mon": "Mạng máy tính", "so_tin_chi": 4, "hoc_ky_chuan": "2024.2"},
    {"ma_mon": "INT2208", "ten_mon": "Công nghệ phần mềm", "so_tin_chi": 3, "hoc_ky_chuan": "2024.2"},
    {"ma_mon": "HIS1001", "ten_mon": "Lịch sử Đảng Cộng sản Việt Nam", "so_tin_chi": 2, "hoc_ky_chuan": "2024.2"},
    # Học kỳ 2025.1
    {"ma_mon": "INT3401", "ten_mon": "Trí tuệ nhân tạo", "so_tin_chi": 3, "hoc_ky_chuan": "2025.1"},
    {"ma_mon": "INT3306", "ten_mon": "Phát triển ứng dụng Web", "so_tin_chi": 3, "hoc_ky_chuan": "2025.1"},
    {"ma_mon": "INT3110", "ten_mon": "Phân tích và thiết kế giải thuật", "so_tin_chi": 3, "hoc_ky_chuan": "2025.1"},
    {"ma_mon": "INT3202", "ten_mon": "An toàn và an ninh mạng", "so_tin_chi": 3, "hoc_ky_chuan": "2025.1"},
    {"ma_mon": "INT3405", "ten_mon": "Học máy", "so_tin_chi": 3, "hoc_ky_chuan": "2025.1"},
    {"ma_mon": "LAW1050", "ten_mon": "Nhà nước và pháp luật đại cương", "so_tin_chi": 2, "hoc_ky_chuan": "2025.1"},
]

HOC_KY_LIST = ["2023.1", "2023.2", "2024.1", "2024.2", "2025.1"]

# 30 sinh viên cùng lớp QH-2024-I/CQ-C-CLC1 (tên các nghệ sĩ Việt Nam)
NGHE_SI_30: list[tuple[str, str, str]] = [
    ("24020001", "Sơn Tùng MTP", "xuat_sac"),
    ("24020002", "Phan Thị Mỹ Tâm", "xuat_sac"),
    ("24020003", "Vũ Cát Tường", "xuat_sac"),
    ("24020004", "Nguyễn Hà Anh Tuấn", "gioi"),
    ("24020005", "Hoàng Thùy Linh", "gioi"),
    ("24020006", "Bích Phương", "gioi"),
    ("24020007", "Phan Mạnh Quỳnh", "gioi_drl_thap"),
    ("24020008", "Nguyễn Trúc Nhân", "gioi_drl_thap"),
    ("24020009", "Nguyễn Đức Phúc", "kha"),
    ("24020010", "Quân AP", "kha"),
    ("24020011", "Nguyễn Tóc Tiên", "kha"),
    ("24020012", "Đăng Răng To", "kha"),
    ("24020013", "Phạm Hương Giang", "kha"),
    ("24020014", "MCK", "kha"),
    ("24020015", "Trịnh Trần Phương Tuấn", "trung_binh"),
    ("24020016", "K-ICM", "trung_binh"),
    ("24020017", "Trần Thu Hà", "trung_binh"),
    ("24020018", "Lê Hồng Nhung", "trung_binh"),
    ("24020019", "Phạm Thanh Lam", "trung_binh"),
    ("24020020", "Nguyễn Bằng Kiều", "trung_binh"),
    ("24020021", "Huỳnh Minh Hưng", "trung_binh"),
    ("24020022", "Hồ Ngọc Hà", "trung_binh"),
    ("24020023", "Mai Hồng Ngọc", "trung_binh"),
    ("24020024", "Ông Cao Thắng", "trung_binh"),
    ("24020025", "Nguyễn Thúc Thùy Tiên", "hoc_vuot"),
    ("24020026", "Trần Thành Đạt", "hoc_vuot"),
    ("24020027", "Nguyễn Quốc Thiên", "canh_bao"),
    ("24020028", "Lê Cát Trọng Lý", "canh_bao"),
    ("24020029", "Phạm Hoàng Dũng", "canh_bao_nang"),
    ("24020030", "BTS", "canh_bao_nang"),
]

THANG_DIEM = [
    (9.0, "A+", 4.0, True),
    (8.5, "A", 3.7, True),
    (8.0, "B+", 3.5, True),
    (7.0, "B", 3.0, True),
    (6.5, "C+", 2.5, True),
    (5.5, "C", 2.0, True),
    (5.0, "D+", 1.5, True),
    (4.0, "D", 1.0, True),
    (0.0, "F", 0.0, False),
]


def quy_doi_diem(diem_10: float) -> tuple[str, float, bool]:
    for nguong, chu, he_4, dat in THANG_DIEM:
        if diem_10 >= nguong:
            return chu, he_4, dat
    return "F", 0.0, False


def sinh_diem_theo_nhom(rng: random.Random, nhom: str, ma_mon: str) -> float:
    kho = -0.7 if ma_mon in {"INT2210", "MAT1093", "INT2214"} else 0.0
    if nhom == "xuat_sac":
        raw = rng.uniform(8.3, 9.8) + kho * 0.3
    elif nhom in {"gioi", "gioi_drl_thap"}:
        raw = rng.uniform(7.6, 9.2) + kho * 0.4
    elif nhom in {"kha", "hoc_vuot"}:
        raw = rng.uniform(6.5, 8.4) + kho * 0.6
    elif nhom == "trung_binh":
        raw = rng.uniform(5.0, 7.4) + kho * 1.1
    elif nhom == "canh_bao":
        raw = rng.uniform(3.4, 6.2) + kho * 1.0
    else:  # canh_bao_nang
        raw = rng.uniform(2.2, 5.4) + kho * 1.0
    return round(max(1.5, min(10.0, raw)), 1)


def generate_dataset(seed: int | None = 42) -> dict[str, Any]:
    rng = random.Random(seed)
    tin_chi_map = {m["ma_mon"]: m["so_tin_chi"] for m in DANH_MUC_MON_HOC}
    sinh_vien_list = []

    for mssv, ho_ten, nhom in NGHE_SI_30:
        bang_diem = []
        tong_diem_4_dat = 0.0
        tin_chi_tich_luy = 0
        tin_chi_no = 0

        for mon in DANH_MUC_MON_HOC:
            d10 = sinh_diem_theo_nhom(rng, nhom, mon["ma_mon"])
            chu, d4, dat = quy_doi_diem(d10)
            tc = tin_chi_map[mon["ma_mon"]]
            if dat:
                tin_chi_tich_luy += tc
                tong_diem_4_dat += d4 * tc
            else:
                tin_chi_no += tc

            bang_diem.append({
                "ma_mon": mon["ma_mon"],
                "hoc_ky": mon["hoc_ky_chuan"],
                "diem_10": d10,
                "diem_chu": chu,
                "diem_4": d4,
                "dat": dat,
            })

        gpa = round(tong_diem_4_dat / tin_chi_tich_luy, 2) if tin_chi_tich_luy > 0 else 0.0

        drl_theo_ky = []
        for hk in HOC_KY_LIST:
            if nhom == "xuat_sac":
                drl = rng.randint(88, 98)
            elif nhom in {"gioi", "hoc_vuot"}:
                drl = rng.randint(80, 92)
            elif nhom == "gioi_drl_thap":
                drl = rng.randint(62, 69)
            elif nhom in {"kha", "trung_binh"}:
                drl = rng.randint(70, 84)
            else:
                drl = rng.randint(52, 68)
            drl_theo_ky.append({"hoc_ky": hk, "diem_drl": drl})

        sinh_vien_list.append({
            "mssv": mssv,
            "ho_ten": ho_ten,
            "nhom": nhom,
            "lop": CLASS_METADATA["class_id"],
            "khoa_tuyen_sinh": CLASS_METADATA["cohort"],
            "nganh": CLASS_METADATA["major"],
            "co_van_hoc_tap": CLASS_METADATA["advisor"],
            "gpa": gpa,
            "tin_chi_tich_luy": tin_chi_tich_luy,
            "tin_chi_no": tin_chi_no,
            "drl_theo_ky": drl_theo_ky,
            "bang_diem": bang_diem,
        })

    return {
        "thong_tin_lop": {
            "lop": CLASS_METADATA["class_id"],
            "khoa_tuyen_sinh": CLASS_METADATA["cohort"],
            "nganh": CLASS_METADATA["major"],
            "co_van_hoc_tap": CLASS_METADATA["advisor"],
            "si_so": len(sinh_vien_list),
            "so_mon_danh_muc": len(DANH_MUC_MON_HOC),
        },
        "danh_muc_mon_hoc": DANH_MUC_MON_HOC,
        "sinh_vien": sinh_vien_list,
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def export_jsonl_database(out_dir: str | Path | None = None, seed: int | None = 42) -> dict[str, Any]:
    """Generate and persist courses.jsonl, students.jsonl, and grades.jsonl."""
    base = Path(out_dir) if out_dir is not None else DEFAULT_DEMO_DIR
    data = generate_dataset(seed=seed)

    write_jsonl(base / "courses.jsonl", data["danh_muc_mon_hoc"])

    student_rows: list[dict[str, Any]] = []
    grade_rows: list[dict[str, Any]] = []
    for sv in data["sinh_vien"]:
        student_rows.append({k: v for k, v in sv.items() if k != "bang_diem"})
        for g in sv["bang_diem"]:
            grade_rows.append({"mssv": sv["mssv"], **g})

    write_jsonl(base / "students.jsonl", student_rows)
    write_jsonl(base / "grades.jsonl", grade_rows)
    return data


class ClassRosterIndex:
    """Fast O(1) lookup index over courses.jsonl, students.jsonl, and grades.jsonl."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        base = Path(data_dir) if data_dir is not None else DEFAULT_DEMO_DIR
        courses = read_jsonl(base / "courses.jsonl")
        students = read_jsonl(base / "students.jsonl")
        grades = read_jsonl(base / "grades.jsonl")

        self.mon_by_ma: dict[str, dict[str, Any]] = {m["ma_mon"]: m for m in courses}
        self.sv_by_mssv: dict[str, dict[str, Any]] = {
            sv["mssv"]: {**sv, "bang_diem": []} for sv in students
        }
        self.diem_by_mon: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for g in grades:
            sv = self.sv_by_mssv[g["mssv"]]
            sv["bang_diem"].append(g)
            self.diem_by_mon[g["ma_mon"]].append({
                "mssv": sv["mssv"],
                "ho_ten": sv["ho_ten"],
                "hoc_ky": g["hoc_ky"],
                "diem_10": g["diem_10"],
                "diem_chu": g["diem_chu"],
                "dat": g["dat"],
            })

    def get_student(self, mssv: str) -> dict[str, Any] | None:
        return self.sv_by_mssv.get(mssv)

    def top_failed_courses(self, top_k: int = 5) -> list[dict[str, Any]]:
        stats = []
        for ma_mon, records in self.diem_by_mon.items():
            failed = [r for r in records if not r["dat"]]
            meta = self.mon_by_ma[ma_mon]
            stats.append({
                "ma_mon": ma_mon,
                "ten_mon": meta["ten_mon"],
                "so_tin_chi": meta["so_tin_chi"],
                "so_luot_truot": len(failed),
                "ty_le_truot": round(len(failed) / len(records) * 100, 1) if records else 0.0,
                "ds_truot": [f"{r['ho_ten']} ({r['diem_10']})" for r in failed],
            })
        stats.sort(key=lambda x: (-x["so_luot_truot"], x["ma_mon"]))
        return stats[:top_k]

    def filter_scholarship_candidates(
        self,
        min_gpa: float = 3.2,
        min_drl: int = 80,
        hoc_ky: str = "2025.1",
    ) -> dict[str, list[dict[str, Any]]]:
        du_dieu_kien, truot_vi_drl = [], []
        for sv in self.sv_by_mssv.values():
            drl_ky = next((d["diem_drl"] for d in sv["drl_theo_ky"] if d["hoc_ky"] == hoc_ky), 0)
            if sv["gpa"] >= min_gpa and sv["tin_chi_no"] == 0:
                item = {"mssv": sv["mssv"], "ho_ten": sv["ho_ten"], "gpa": sv["gpa"], "drl": drl_ky}
                if drl_ky >= min_drl:
                    du_dieu_kien.append(item)
                else:
                    truot_vi_drl.append(item)
        return {"du_dieu_kien": du_dieu_kien, "truot_vi_drl": truot_vi_drl}


def _evaluate_student_status(sv: dict[str, Any]) -> dict[str, Any]:
    """Deterministic per-student academic eligibility assessment based on UET regulations."""
    gpa = float(sv["gpa"])
    owed = int(sv["tin_chi_no"])
    nhom = sv.get("nhom", "")
    drl = int(
        next(
            (d["diem_drl"] for d in sv.get("drl_theo_ky", []) if d["hoc_ky"] == CLASS_METADATA["current_hoc_ky"]),
            75,
        )
    )

    # 1. Cảnh báo học vụ (CPA/GPA < 1.8 hoặc nợ nhiều tín chỉ hoặc thuộc nhóm cảnh báo)
    warning_reasons: list[str] = []
    if gpa < 1.8:
        warning_reasons.append(f"GPA {gpa:.2f} < 1.80")
    if owed >= 12:
        warning_reasons.append(f"nợ {owed} tín chỉ")
    elif owed > 0 and nhom in ("canh_bao", "canh_bao_nang"):
        warning_reasons.append(f"nợ {owed} tín chỉ, nhóm {nhom}")
    is_warning_risk = len(warning_reasons) > 0 or nhom in ("canh_bao", "canh_bao_nang")
    if is_warning_risk and not warning_reasons:
        warning_reasons.append(f"GPA thấp ({gpa:.2f}) / có môn trượt")

    # 2. Học bổng KKHT (GPA >= 3.2, không nợ môn, ĐRL >= 80)
    scholarship_tier: Optional[str] = None
    scholarship_trap_reason: Optional[str] = None
    if owed == 0 and gpa >= 3.2:
        if drl < 70:
            scholarship_trap_reason = f"GPA {gpa:.2f} đạt chuẩn nhưng ĐRL = {drl} (< 70, dưới mức Khá)"
        elif gpa >= 3.6 and drl >= 90:
            scholarship_tier = "Xuất sắc"
        elif gpa >= 3.6 and drl >= 80:
            scholarship_tier = "Giỏi (hạ từ Xuất sắc do ĐRL 80-89)"
        elif drl >= 80:
            scholarship_tier = "Giỏi"
        else:
            scholarship_trap_reason = f"GPA {gpa:.2f} nhưng ĐRL = {drl} (< 80)"

    is_scholarship_priority = (owed == 0 and gpa >= 3.2 and drl >= 80)

    # 3. Học vượt 24 tín chỉ (GPA >= 2.5, không nợ môn, không bị cảnh báo)
    is_overload_eligible = (gpa >= 2.5 and owed == 0 and not is_warning_risk)

    return {
        "scholarship_eligible": scholarship_tier is not None,
        "scholarship_priority": is_scholarship_priority,
        "scholarship_tier": scholarship_tier,
        "scholarship_trap_low_drl": scholarship_trap_reason is not None,
        "scholarship_trap_reason": scholarship_trap_reason,
        "overload_eligible": is_overload_eligible,
        "warning_risk": is_warning_risk,
        "warning_reasons": warning_reasons,
        "severe_expulsion_risk": nhom == "canh_bao_nang" or owed >= 20,
    }


def _normalize_student_record(sv: dict[str, Any]) -> dict[str, Any]:
    """Provide unified UI/API fields alongside the original JSONL schema."""
    drl_cur = int(
        next(
            (d["diem_drl"] for d in sv.get("drl_theo_ky", []) if d["hoc_ky"] == CLASS_METADATA["current_hoc_ky"]),
            75,
        )
    )
    assessment = _evaluate_student_status(sv)
    return {
        **sv,
        "student_id": sv["mssv"],
        "full_name": sv["ho_ten"],
        "class_id": CLASS_METADATA["class_id"],
        "class_short": CLASS_METADATA["class_short"],
        "cohort": CLASS_METADATA["cohort"],
        "major": CLASS_METADATA["major"],
        "program": CLASS_METADATA["program"],
        "gpa_semester": sv["gpa"],
        "cpa": sv["gpa"],
        "drl": drl_cur,
        "accumulated_credits": sv["tin_chi_tich_luy"],
        "owed_credits": sv["tin_chi_no"],
        "requested_overload_credits": 24 if sv.get("nhom") == "hoc_vuot" and assessment["overload_eligible"] else None,
        "assessment": assessment,
    }


def analyze_class_roster(roster: dict[str, Any]) -> dict[str, Any]:
    """Run deterministic arithmetic & threshold checks across all 30 students."""
    students = roster.get("students", [])
    scholarship_priority: list[dict[str, Any]] = []
    scholarship_trapped_low_drl: list[dict[str, Any]] = []
    overload_eligible: list[dict[str, Any]] = []
    overload_applicants: list[dict[str, Any]] = []
    warning_risk: list[dict[str, Any]] = []

    for st in students:
        ev = st.get("assessment") or _evaluate_student_status(st)
        entry = {
            "student_id": st["student_id"],
            "full_name": st["full_name"],
            "gpa_semester": st["gpa_semester"],
            "cpa": st["cpa"],
            "drl": st["drl"],
            "accumulated_credits": st["accumulated_credits"],
            "owed_credits": st["owed_credits"],
            "requested_overload_credits": st.get("requested_overload_credits"),
            "nhom": st.get("nhom"),
            **ev,
        }
        if ev["scholarship_priority"]:
            scholarship_priority.append(entry)
        if ev["scholarship_trap_low_drl"]:
            scholarship_trapped_low_drl.append(entry)
        if ev["overload_eligible"]:
            overload_eligible.append(entry)
            if st.get("requested_overload_credits"):
                overload_applicants.append(entry)
        if ev["warning_risk"]:
            warning_risk.append(entry)

    return {
        "total_students": len(students),
        "total_courses": len(DANH_MUC_MON_HOC),
        "scholarship_eligible_count": len(scholarship_priority),
        "scholarship_priority_count": len(scholarship_priority),
        "scholarship_trapped_count": len(scholarship_trapped_low_drl),
        "overload_eligible_count": len(overload_eligible),
        "overload_applicants_count": len(overload_applicants),
        "warning_risk_count": len(warning_risk),
        "scholarship_priority": scholarship_priority,
        "scholarship_trapped_low_drl": scholarship_trapped_low_drl,
        "overload_eligible": overload_eligible,
        "overload_applicants": overload_applicants,
        "warning_risk": warning_risk,
    }


_ROSTER_CACHE: dict[str, tuple[tuple[int, int, int], dict[str, Any]]] = {}


def invalidate_roster_cache(data_dir: Path | str | None = None) -> None:
    """Clear cached roster for a directory (or all directories)."""
    if data_dir is None:
        _ROSTER_CACHE.clear()
    else:
        key = str(Path(data_dir).resolve())
        _ROSTER_CACHE.pop(key, None)


def _files_mtime_stamp(target_dir: Path) -> Optional[tuple[int, int, int]]:
    files = [target_dir / f for f in ("courses.jsonl", "students.jsonl", "grades.jsonl")]
    if not all(p.is_file() for p in files):
        return None
    return (
        files[0].stat().st_mtime_ns,
        files[1].stat().st_mtime_ns,
        files[2].stat().st_mtime_ns,
    )


def _build_roster_payload(data_dir: Path, *, seed: int | None = None) -> dict[str, Any]:
    idx = ClassRosterIndex(data_dir)
    raw_students = list(idx.sv_by_mssv.values())
    first_sv = raw_students[0] if raw_students else {}

    # Single source of truth: read class & advisor identity from the persisted roster JSONL
    dynamic_meta = {
        **CLASS_METADATA,
        "class_id": first_sv.get("lop") or CLASS_METADATA["class_id"],
        "cohort": first_sv.get("khoa_tuyen_sinh") or CLASS_METADATA["cohort"],
        "major": first_sv.get("nganh") or CLASS_METADATA["major"],
        "advisor": first_sv.get("co_van_hoc_tap") or CLASS_METADATA["advisor"],
    }
    if "QH-2024" in str(dynamic_meta["cohort"]) or "K69" in str(dynamic_meta["cohort"]):
        dynamic_meta["class_short"] = "K69-CNTT1"
    elif "QH-2023" in str(dynamic_meta["cohort"]) or "K68" in str(dynamic_meta["cohort"]):
        dynamic_meta["class_short"] = "K68-CNTT1"

    students = [_normalize_student_record(sv) for sv in raw_students]
    for st in students:
        st["class_id"] = dynamic_meta["class_id"]
        st["class_short"] = dynamic_meta["class_short"]
        st["cohort"] = dynamic_meta["cohort"]
        st["major"] = dynamic_meta["major"]

    roster: dict[str, Any] = {
        **dynamic_meta,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "seed": seed,
        "data_dir": str(data_dir),
        "courses": list(idx.mon_by_ma.values()),
        "students": students,
        "top_failed_courses": idx.top_failed_courses(5),
    }
    roster["analysis"] = analyze_class_roster(roster)
    return roster


def generate_class_roster(
    seed: int | None = None,
    *,
    save_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Generate 30-student x 26-course JSONL database and return full analyzed roster."""
    target_dir = Path(save_dir) if save_dir is not None else DEFAULT_DEMO_DIR
    invalidate_roster_cache(target_dir)
    export_jsonl_database(out_dir=target_dir, seed=seed)
    payload = _build_roster_payload(target_dir, seed=seed)
    stamp = _files_mtime_stamp(target_dir)
    if stamp is not None:
        _ROSTER_CACHE[str(target_dir.resolve())] = (stamp, payload)
    return payload


def load_class_roster(data_dir: Path | str | None = None) -> dict[str, Any]:
    """Load persisted 3-file JSONL class roster with mtime-based cache invalidation."""
    target_dir = Path(data_dir) if data_dir is not None else DEFAULT_DEMO_DIR
    cache_key = str(target_dir.resolve())
    stamp = _files_mtime_stamp(target_dir)
    if stamp is not None:
        cached = _ROSTER_CACHE.get(cache_key)
        if cached is not None and cached[0] == stamp:
            return cached[1]
        try:
            payload = _build_roster_payload(target_dir)
            if len(payload.get("students", [])) == 30:
                _ROSTER_CACHE[cache_key] = (stamp, payload)
                return payload
        except Exception:
            pass
    return generate_class_roster(seed=42, save_dir=target_dir)


def format_roster_facts_text(roster: dict[str, Any], question: str = "") -> str:
    """Build deterministic pre-checked facts summary from the 30-student JSONL database."""
    analysis = roster.get("analysis") or analyze_class_roster(roster)
    top_failed = roster.get("top_failed_courses") or []
    ql = (question or "").lower()

    asks_scholarship = any(k in ql for k in ("học bổng", "kkht", "rèn luyện", "đrl", "trượt vì"))
    asks_warning = any(k in ql for k in ("cảnh báo", "buộc thôi học", "nợ", "yếu", "nguy cơ"))
    asks_overload = any(k in ql for k in ("học vượt", "24 tín chỉ", "vượt tín chỉ", "đăng ký tối đa"))
    asks_failed_courses = any(k in ql for k in ("trượt nhiều", "môn nào", "tỷ lệ trượt", "thống kê môn"))

    lines = [
        f"Lớp {roster.get('class_id')} ({roster.get('class_short')}) | Ngành {roster.get('major')} | "
        f"Sĩ số: {analysis['total_students']} sinh viên × {analysis.get('total_courses', 26)} môn học | Cố vấn: {roster.get('advisor')}:",
    ]

    if asks_scholarship or not (asks_warning or asks_overload or asks_failed_courses):
        p_list = analysis["scholarship_priority"]
        t_list = analysis["scholarship_trapped_low_drl"]
        lines.append(
            f"- Đủ điều kiện xét học bổng KKHT (GPA >= 3.20, không nợ môn, ĐRL kỳ 2025.1 >= 80): {len(p_list)} sinh viên:"
        )
        for st in p_list:
            lines.append(
                f"  + {st['full_name']} ({st['student_id']}): GPA {st['gpa_semester']:.2f}, ĐRL {st['drl']}, tích lũy {st['accumulated_credits']} TC → Đạt mức {st['scholarship_tier']}."
            )
        lines.append(
            f"- Trượt xét học bổng KKHT dù GPA >= 3.20 do ĐRL < 70 (bẫy ĐRL thấp): {len(t_list)} sinh viên:"
        )
        for st in t_list:
            lines.append(
                f"  + {st['full_name']} ({st['student_id']}): GPA {st['gpa_semester']:.2f}, ĐRL {st['drl']} (< 70) → KHÔNG đủ điều kiện."
            )

    if asks_warning or not (asks_scholarship or asks_overload or asks_failed_courses):
        w_list = analysis["warning_risk"]
        lines.append(f"- Nguy cơ bị cảnh báo học vụ: {len(w_list)} sinh viên:")
        for st in w_list:
            reasons = "; ".join(st["warning_reasons"])
            severe = " [CẢNH BÁO NẶNG]" if st.get("severe_expulsion_risk") else ""
            lines.append(
                f"  + {st['full_name']} ({st['student_id']}): GPA {st['gpa_semester']:.2f}, tích lũy {st['accumulated_credits']} TC, nợ {st['owed_credits']} TC → {reasons}{severe}."
            )

    if asks_overload or not (asks_scholarship or asks_warning or asks_failed_courses):
        ov_all = analysis["overload_eligible"]
        ov_app = analysis["overload_applicants"]
        lines.append(
            f"- Đủ điều kiện đăng ký học vượt lên 24 tín chỉ (GPA >= 2.50, nợ 0 TC, không cảnh báo): {len(ov_all)} sinh viên "
            f"(trong đó {len(ov_app)} em nhóm học vượt đang đề nghị đăng ký 24 TC):"
        )
        for st in ov_app or ov_all[:6]:
            tag = " [Đang xin ĐK 24 TC]" if st.get("requested_overload_credits") else ""
            lines.append(
                f"  + {st['full_name']} ({st['student_id']}): GPA {st['gpa_semester']:.2f}, ĐRL {st['drl']}, nợ 0 TC{tag}."
            )

    if asks_failed_courses and top_failed:
        lines.append("- Top môn học có tỷ lệ trượt cao nhất của lớp:")
        for c in top_failed:
            ds = ", ".join(c["ds_truot"]) if c["ds_truot"] else "Không có"
            lines.append(
                f"  + {c['ma_mon']} ({c['ten_mon']}, {c['so_tin_chi']} TC): {c['so_luot_truot']} lượt trượt ({c['ty_le_truot']}%) — DS: {ds}."
            )

    return "\n".join(lines)
