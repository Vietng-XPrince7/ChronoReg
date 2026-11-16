"""Select regulation version (academic year) based on temporal signals in the question."""
from __future__ import annotations

import re
from dataclasses import dataclass

_RANGE = re.compile(
    r"(?<![\d-])(?<!qh)(20\d{2})[ \t]*[-–—/][ \t]*(20\d{2})(?!\d)",
    re.IGNORECASE,
)
_SINGLE = re.compile(
    r"(?<!sinh )(?<!khóa )(?<!khoá )(?<!tuyển )(?:năm học|năm)[ \t]+(20\d{2})(?![ \t]*[-–—/][ \t]*20\d{2})(?!\d)",
    re.IGNORECASE,
)
_PRIOR_YEAR = re.compile(
    r"trước[ \t]+(?:năm học|năm|khi)[ \t]*(20\d{2})(?:[ \t]*[-–—/][ \t]*20\d{2})?",
    re.IGNORECASE,
)

OLD_HINTS = (
    "quy định cũ", "bản cũ", "phiên bản cũ", "trước đây", "trước kia",
    "đã bị thay thế", "bị thay thế", "không còn hiệu lực", "hết hiệu lực",
    "trước khi sửa đổi", "trước năm", "trước đó", "thay đổi", "sửa đổi",
)

_ARTICLE = re.compile(r"\bĐiều[ \t]+(\d+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class VersionPlan:
    mode: str                     # "year" | "latest" | "all"
    start_year: int | None
    reason: str
    years: tuple[int, ...] = ()
    is_historical: bool = False

    def all_years(self) -> tuple[int, ...]:
        if self.years:
            return self.years
        return (self.start_year,) if self.start_year else ()

    def label(self) -> str:
        return ", ".join(f"{y}-{y + 1}" for y in self.all_years())

    def where_for(self, year: int | None = None) -> dict | None:
        y = year if year is not None else self.start_year
        return {"start_year": y} if y else None


def extract_article(question: str) -> str | None:
    m = _ARTICLE.search(question)
    return f"Điều {int(m.group(1))}" if m else None


def single_year_to_start(year: int, single_year_means: str = "start") -> int:
    return year if single_year_means == "start" else year - 1


def extract_years(question: str, single_year_means: str = "start") -> list[int]:
    q = question.lower()
    found: list[tuple[int, int]] = []

    # Handle "trước năm học YYYY-YYYY" by shifting start year back by 1
    for m in _PRIOR_YEAR.finditer(q):
        y = int(m.group(1))
        found.append((m.start(), y - 1))

    for m in _RANGE.finditer(q):
        a, b = int(m.group(1)), int(m.group(2))
        if b == a + 1:
            found.append((m.start(), a))
    for m in _SINGLE.finditer(q):
        found.append((m.start(), single_year_to_start(int(m.group(1)), single_year_means)))

    out: list[int] = []
    for _, y in sorted(found):
        if y not in out:
            out.append(y)
    return out


def plan_version(
    question: str,
    as_of_year: int | None = None,
    single_year_means: str = "start",
) -> VersionPlan:
    ql = question.lower()
    is_old = any(h in ql for h in OLD_HINTS)
    years = extract_years(question, single_year_means)

    if years:
        lab = ", ".join(f"{y}-{y + 1}" for y in years)
        return VersionPlan(
            "year",
            years[0],
            f"năm học {lab} nêu trong câu hỏi",
            tuple(years),
            is_historical=is_old,
        )
    if as_of_year:
        s = single_year_to_start(as_of_year, single_year_means)
        return VersionPlan(
            "year",
            s,
            f"as_of_year={as_of_year} -> năm học {s}-{s + 1}",
            (s,),
            is_historical=is_old,
        )
    if is_old:
        return VersionPlan(
            "all",
            None,
            "hỏi quy định cũ, không nêu năm -> lấy mọi năm học",
            is_historical=True,
        )
    return VersionPlan("latest", None, "không nêu năm -> năm học mới nhất của chủ đề")