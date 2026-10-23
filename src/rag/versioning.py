"""Chọn phiên bản văn bản theo thời điểm hỏi.

Thứ tự ưu tiên:
  1. Năm được nêu trong câu hỏi        -> lọc theo hiệu lực tại năm đó
  2. as_of_year do người gọi truyền vào -> lọc theo hiệu lực tại năm đó
  3. Câu hỏi về quy định cũ (không năm) -> không lọc, lấy cả bản cũ lẫn mới
  4. Còn lại                            -> chỉ lấy văn bản đang hiệu lực hôm nay
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

YEAR = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
OLD_HINTS = (
    "quy định cũ", "bản cũ", "phiên bản cũ", "trước đây", "trước kia",
    "đã bị thay thế", "bị thay thế", "không còn hiệu lực", "hết hiệu lực",
    "trước khi sửa đổi",
)


@dataclass
class VersionPlan:
    mode: str          # "as_of" | "current" | "all"
    t: int | None      # ngày T dạng YYYYMMDD (None nếu mode == "all")
    reason: str

    def where(self) -> dict | None:
        """Filter metadata: effective_ts <= T VÀ expired_ts > T (đúng theo docs/schema.md)."""
        if self.mode == "all" or self.t is None:
            return None
        return {"$and": [
            {"effective_ts": {"$lte": self.t}},
            {"expired_ts": {"$gt": self.t}},
        ]}


def year_to_ts(year: int, year_to_date: str = "12-31") -> int:
    return int(f"{year}{year_to_date.replace('-', '')}")


def plan_version(question: str, as_of_year: int | None = None,
                 year_to_date: str = "12-31", today: date | None = None) -> VersionPlan:
    m = YEAR.search(question)
    if m:
        y = int(m.group(1))   # "2023-2024" -> lấy năm đầu
        return VersionPlan("as_of", year_to_ts(y, year_to_date), f"năm {y} nêu trong câu hỏi")
    if as_of_year:
        return VersionPlan("as_of", year_to_ts(as_of_year, year_to_date), f"as_of_year={as_of_year}")
    if any(h in question.lower() for h in OLD_HINTS):
        return VersionPlan("all", None, "hỏi quy định cũ, không nêu năm -> lấy mọi phiên bản")
    t = int((today or date.today()).strftime("%Y%m%d"))
    return VersionPlan("current", t, "không nêu năm -> văn bản đang hiệu lực")
