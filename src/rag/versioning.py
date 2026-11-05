"""Chọn phiên bản (năm học) theo câu hỏi.

Dữ liệu của Việt: effective_from / effective_until_exclusive hầu như còn null
(= CHƯA BIẾT), nên phiên bản được phân biệt bằng năm học (academic_year).

Thứ tự ưu tiên:
  1. Câu hỏi nêu năm học ("2023-2024") hoặc "năm 2023" -> lọc đúng năm học đó.
     Nếu nêu NHIỀU năm (vd "trước năm học 2026-2027 ... năm học 2025-2026") -> lấy cả hai.
  2. as_of_year do người gọi truyền vào                 -> lọc như trên
  3. Hỏi quy định cũ, không nêu năm                     -> không lọc, lấy mọi năm học
  4. Còn lại                                            -> năm học mới nhất của chủ đề

Không coi năm của KHÓA TUYỂN SINH là năm quy định ("khóa QH-2021", "khóa tuyển sinh từ 2021",
"tuyển sinh năm 2021").
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Khoảng năm học liên tiếp: 2025-2026 (không lấy "QH-2021-...", không lấy số dính liền với số khác)
_RANGE = re.compile(r"(?<![\d-])(?<!qh)(20\d{2})[ \t]*[-–/][ \t]*(20\d{2})(?!\d)", re.IGNORECASE)
# Một năm đơn lẻ phải đi sau "năm" / "năm học"; bỏ "tuyển sinh năm 2021", "khóa năm 2021";
# không lấy nếu nó là vế đầu của một khoảng (2022-2023).
_SINGLE = re.compile(
    r"(?<!sinh )(?<!khóa )(?<!khoá )(?<!tuyển )(?:năm học|năm)[ \t]+(20\d{2})(?![ \t]*[-–/][ \t]*20\d{2})(?!\d)",
    re.IGNORECASE,
)
OLD_HINTS = (
    "quy định cũ", "bản cũ", "phiên bản cũ", "trước đây", "trước kia",
    "đã bị thay thế", "bị thay thế", "không còn hiệu lực", "hết hiệu lực",
    "trước khi sửa đổi",
)


_ARTICLE = re.compile(r"\bĐiều[ \t]+(\d+)\b", re.IGNORECASE)


def extract_article(question: str) -> str | None:
    """Câu hỏi nêu rõ một Điều ("Theo Điều 17 của ...") -> "Điều 17"; không có -> None."""
    m = _ARTICLE.search(question)
    return f"Điều {int(m.group(1))}" if m else None


def single_year_to_start(year: int, single_year_means: str = "start") -> int:
    return year if single_year_means == "start" else year - 1


def extract_years(question: str, single_year_means: str = "start") -> list[int]:
    """Các năm bắt đầu của năm học được nêu trong câu hỏi, theo thứ tự xuất hiện, không trùng."""
    q = question.lower()
    found: list[tuple[int, int]] = []
    for m in _RANGE.finditer(q):
        a, b = int(m.group(1)), int(m.group(2))
        if b == a + 1:                      # khoảng không liên tiếp là khóa học, không phải năm học
            found.append((m.start(), a))
    for m in _SINGLE.finditer(q):
        found.append((m.start(), single_year_to_start(int(m.group(1)), single_year_means)))
    out: list[int] = []
    for _, y in sorted(found):
        if y not in out:
            out.append(y)
    return out


@dataclass
class VersionPlan:
    mode: str                  # "year" | "latest" | "all"
    start_year: int | None     # năm bắt đầu của năm học (2023 -> 2023-2024); với nhiều năm: năm đầu tiên
    reason: str
    years: tuple = ()          # tất cả năm bắt đầu (chế độ "year")

    def all_years(self) -> list[int]:
        return list(self.years) or ([self.start_year] if self.start_year else [])

    def label(self) -> str:
        return " và ".join(f"{y}-{y + 1}" for y in self.all_years())

    @staticmethod
    def where_for(year: int) -> dict:
        return {"start_year": year}

    def where(self) -> dict | None:
        ys = self.all_years()
        return self.where_for(ys[0]) if self.mode == "year" and ys else None


def plan_version(question: str, as_of_year: int | None = None,
                 single_year_means: str = "start") -> VersionPlan:
    years = extract_years(question, single_year_means)
    if years:
        lab = ", ".join(f"{y}-{y + 1}" for y in years)
        return VersionPlan("year", years[0], f"năm học {lab} nêu trong câu hỏi", tuple(years))
    if as_of_year:
        s = single_year_to_start(as_of_year, single_year_means)
        return VersionPlan("year", s, f"as_of_year={as_of_year} -> năm học {s}-{s + 1}", (s,))
    if any(h in question.lower() for h in OLD_HINTS):
        return VersionPlan("all", None, "hỏi quy định cũ, không nêu năm -> lấy mọi năm học")
    return VersionPlan("latest", None, "không nêu năm -> năm học mới nhất của chủ đề")
