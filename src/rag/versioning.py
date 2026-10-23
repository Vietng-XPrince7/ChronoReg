"""Chọn phiên bản (năm học) theo câu hỏi.

Dữ liệu của Việt: effective_from / effective_until_exclusive hầu như còn null
(= CHƯA BIẾT), nên phiên bản được phân biệt bằng năm học (academic_year).

Thứ tự ưu tiên:
  1. Câu hỏi nêu năm học ("2023-2024") hoặc một năm ("năm 2023") -> lọc đúng năm học đó
  2. as_of_year do người gọi truyền vào                           -> lọc như trên
  3. Hỏi quy định cũ, không nêu năm                               -> không lọc, lấy mọi năm học
  4. Còn lại                                                      -> năm học mới nhất của chủ đề
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# "khóa 2022" là khóa tuyển sinh, không phải năm của quy định -> bỏ qua
RANGE = re.compile(r"(?<!khóa )(?<!khoá )(?<!\d)(20\d{2})\s*[-–/]\s*(20\d{2})(?!\d)")
YEAR = re.compile(r"(?<!khóa )(?<!khoá )(?<!\d)(20\d{2})(?!\d)")
OLD_HINTS = (
    "quy định cũ", "bản cũ", "phiên bản cũ", "trước đây", "trước kia",
    "đã bị thay thế", "bị thay thế", "không còn hiệu lực", "hết hiệu lực",
    "trước khi sửa đổi",
)


@dataclass
class VersionPlan:
    mode: str                  # "year" | "latest" | "all"
    start_year: int | None     # năm bắt đầu của năm học (2023 -> 2023-2024)
    reason: str

    def label(self) -> str:
        return f"{self.start_year}-{self.start_year + 1}" if self.start_year else ""

    def where(self) -> dict | None:
        if self.mode == "year" and self.start_year:
            return {"start_year": self.start_year}
        return None


def single_year_to_start(year: int, single_year_means: str = "start") -> int:
    return year if single_year_means == "start" else year - 1


def plan_version(question: str, as_of_year: int | None = None,
                 single_year_means: str = "start") -> VersionPlan:
    q = question.lower()
    m = RANGE.search(q)
    if m:
        s = int(m.group(1))
        return VersionPlan("year", s, f"năm học {s}-{s + 1} nêu trong câu hỏi")
    m = YEAR.search(q)
    if m:
        y = int(m.group(1))
        s = single_year_to_start(y, single_year_means)
        return VersionPlan("year", s, f"năm {y} nêu trong câu hỏi -> năm học {s}-{s + 1}")
    if as_of_year:
        s = single_year_to_start(as_of_year, single_year_means)
        return VersionPlan("year", s, f"as_of_year={as_of_year} -> năm học {s}-{s + 1}")
    if any(h in q for h in OLD_HINTS):
        return VersionPlan("all", None, "hỏi quy định cũ, không nêu năm -> lấy mọi năm học")
    return VersionPlan("latest", None, "không nêu năm -> năm học mới nhất của chủ đề")
