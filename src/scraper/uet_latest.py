"""UET Latest News Scraper (Page 1 only, timeout=4.0s, automatic local JSON cache).

Cào duy nhất trang 1 từ 2 chuyên mục chính thức của Trường ĐH Công nghệ - ĐHQGHN:
- https://uet.edu.vn/category/tin-tuc/tin-sinh-vien/
- https://uet.edu.vn/category/dao-tao/

Lấy tối đa 8–10 bài viết mới nhất (`title`, `date`, `url`, `summary`), tự động lưu cache ra
`data/demo/uet_latest_news_cache.json`. Khi mất mạng hoặc trang không phản hồi trong 4.0s,
tự động đọc lại từ bản cache gần nhất để không bao giờ gây lỗi khi demo trên lớp.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore[assignment]

from html.parser import HTMLParser

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_PATH = REPO_ROOT / "data" / "demo" / "uet_latest_news_cache.json"

UET_PAGE1_URLS: list[tuple[str, str]] = [
    ("Tin sinh viên", "https://uet.edu.vn/category/tin-tuc/tin-sinh-vien/"),
    ("Đào tạo", "https://uet.edu.vn/category/dao-tao/"),
]

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8",
}


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


class _FallbackArticleParser(HTMLParser):
    """Lightweight stdlib HTMLParser fallback when BeautifulSoup4 is not installed."""

    def __init__(self) -> None:
        super().__init__()
        self.articles: list[dict[str, str]] = []
        self._in_article = False
        self._article_depth = 0
        self._cur: dict[str, Any] = {}
        self._capture_tag: Optional[str] = None
        self._capture_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        attr_map = dict(attrs)
        cls = (attr_map.get("class") or "").lower()
        if tag == "article" or (tag in ("div", "li") and any(c in cls for c in ("post", "td_module_wrap", "entry-item", "news-item"))):
            if not self._in_article:
                self._in_article = True
                self._article_depth = 1
                self._cur = {"title": "", "url": "", "date": "", "summary": "", "raw_text": []}
                return
        if self._in_article:
            self._article_depth += 1
            if tag == "a" and not self._cur.get("url"):
                href = _clean_text(attr_map.get("href") or "")
                if href and not href.startswith("#"):
                    self._cur["url"] = href
                    self._capture_tag = "a"
                    self._capture_buf = []
            elif tag == "time" or any(c in cls for c in ("entry-date", "published", "post-date", "td-post-date")):
                self._capture_tag = "date"
                self._capture_buf = []
            elif tag == "p" or any(c in cls for c in ("entry-summary", "td-excerpt", "post-excerpt", "excerpt")):
                if not self._cur.get("summary"):
                    self._capture_tag = "summary"
                    self._capture_buf = []

    def handle_data(self, data: str) -> None:
        if self._in_article:
            self._cur["raw_text"].append(data)
            if self._capture_tag:
                self._capture_buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._in_article:
            return
        if self._capture_tag == "a" and tag == "a":
            title = _clean_text("".join(self._capture_buf))
            if len(title) >= 8:
                self._cur["title"] = title
            else:
                self._cur["url"] = ""
            self._capture_tag = None
        elif self._capture_tag == "date" and tag in ("time", "span", "div"):
            d = _clean_text("".join(self._capture_buf))
            if d and not self._cur.get("date"):
                self._cur["date"] = d
            self._capture_tag = None
        elif self._capture_tag == "summary" and tag in ("p", "div", "span"):
            s = _clean_text("".join(self._capture_buf))
            if s and s != self._cur.get("title"):
                self._cur["summary"] = s
            self._capture_tag = None

        self._article_depth -= 1
        if self._article_depth <= 0:
            self._in_article = False
            if self._cur.get("title") and self._cur.get("url"):
                if not self._cur.get("date"):
                    m = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b", " ".join(self._cur["raw_text"]))
                    if m:
                        self._cur["date"] = m.group(1)
                self.articles.append(self._cur)


def _parse_articles_from_html(html: str, category: str, base_url: str) -> list[dict[str, str]]:
    """Extract articles (title, date, url, summary) from a WordPress category page-1 HTML."""
    if BeautifulSoup is None:
        parser = _FallbackArticleParser()
        parser.feed(html)
        out: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in parser.articles:
            href = item["url"]
            if href.startswith("/"):
                href = "https://uet.edu.vn" + href
            if href in seen:
                continue
            seen.add(href)
            summary = item.get("summary") or f"Thông báo thuộc chuyên mục {category} từ cổng thông tin UET ({base_url})."
            if len(summary) > 260:
                summary = summary[:257].rstrip() + "..."
            out.append({
                "title": item["title"],
                "date": item.get("date") or "Mới cập nhật",
                "url": href,
                "summary": summary,
                "category": category,
            })
        return out

    soup = BeautifulSoup(html, "html.parser")
    articles: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    # Common WordPress / UET article container selectors
    containers = soup.select(
        "article, .post, .td_module_wrap, .entry-item, .news-item, .blog-post, .type-post"
    )
    if not containers:
        # Fallback: look inside main content area headings with links
        containers = soup.select("main .entry, #main .post, .site-main > div, .archive-list li")

    for block in containers:
        link_el = (
            block.select_one("h1 a, h2 a, h3 a, h4 a, .entry-title a, .td-module-title a, a.post-title")
            or block.select_one("a[href]")
        )
        if not link_el:
            continue

        title = _clean_text(link_el.get_text(" "))
        href = _clean_text(str(link_el.get("href") or ""))
        if not title or len(title) < 8 or not href or href.startswith("#"):
            continue
        if href.startswith("/"):
            href = "https://uet.edu.vn" + href
        if href in seen_urls:
            continue

        # Date extraction
        date_el = block.select_one(
            "time, .entry-date, .published, .td-post-date, .post-date, .date, .meta-date"
        )
        date_str = ""
        if date_el:
            date_str = _clean_text(date_el.get_text(" ")) or _clean_text(str(date_el.get("datetime") or ""))
        if not date_str:
            m_date = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b", block.get_text(" "))
            if m_date:
                date_str = m_date.group(1)

        # Summary extraction
        sum_el = block.select_one(
            ".entry-summary, .entry-content p, .td-excerpt, .post-excerpt, .excerpt, p"
        )
        summary = _clean_text(sum_el.get_text(" ")) if sum_el else ""
        if summary == title:
            summary = ""
        if len(summary) > 260:
            summary = summary[:257].rstrip() + "..."

        seen_urls.add(href)
        articles.append({
            "title": title,
            "date": date_str or "Mới cập nhật",
            "url": href,
            "summary": summary or f"Thông báo thuộc chuyên mục {category} từ cổng thông tin UET ({base_url}).",
            "category": category,
        })

    return articles


class UETLatestNewsScraper:
    """Scrapes page 1 of UET Student News & Academic Training pages with offline cache fallback."""

    def __init__(
        self,
        cache_path: Path | str | None = DEFAULT_CACHE_PATH,
        urls: list[tuple[str, str]] | None = None,
        timeout: float = 4.0,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self.cache_path = Path(cache_path) if cache_path else DEFAULT_CACHE_PATH
        self.urls = urls if urls is not None else list(UET_PAGE1_URLS)
        self.timeout = timeout
        self._http_client = http_client

    def load_cache(self) -> dict[str, Any]:
        """Read cached articles from disk; return empty payload if missing or unreadable."""
        if self.cache_path.is_file():
            try:
                data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("articles"), list):
                    return data
            except Exception as exc:
                log.warning("Failed to read UET news cache %s: %s", self.cache_path, exc)
        return {
            "fetched_at": None,
            "source": "cache_empty",
            "sources_checked": [u for _, u in self.urls],
            "articles": [],
        }

    def save_cache(self, payload: dict[str, Any]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def scrape_latest(self, limit: int = 10) -> dict[str, Any]:
        """Fetch page 1 of each UET category URL, keep up to `limit` newest items, and cache.

        If network access fails or yields 0 parsed articles, transparently falls back to cached data.
        """
        max_items = max(1, min(int(limit), 10))
        collected: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        errors: list[str] = []

        should_close = False
        client = self._http_client
        if client is None:
            client = httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers=_DEFAULT_HEADERS,
            )
            should_close = True

        try:
            for category, url in self.urls:
                try:
                    resp = client.get(url, timeout=self.timeout)
                    resp.raise_for_status()
                    parsed = _parse_articles_from_html(resp.text, category=category, base_url=url)
                    for art in parsed:
                        if art["url"] not in seen_urls:
                            seen_urls.add(art["url"])
                            collected.append(art)
                except Exception as exc:
                    errors.append(f"{category}: {exc}")
                    log.info("UET scrape failed for %s: %s", url, exc)
        finally:
            if should_close:
                client.close()

        if collected:
            articles = collected[:max_items]
            payload: dict[str, Any] = {
                "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                "source": "live_scrape",
                "sources_checked": [u for _, u in self.urls],
                "count": len(articles),
                "articles": articles,
            }
            if errors:
                payload["partial_errors"] = errors
            self.save_cache(payload)
            return payload

        # Offline / error fallback -> read cached snapshot
        cached = self.load_cache()
        articles = list(cached.get("articles") or [])[:max_items]
        return {
            "fetched_at": cached.get("fetched_at"),
            "source": "cache_fallback" if articles else "cache_empty",
            "sources_checked": [u for _, u in self.urls],
            "count": len(articles),
            "articles": articles,
            "fallback_reason": "; ".join(errors) if errors else "Không cào được bài viết mới — đang dùng dữ liệu cache.",
        }

    def get_latest_or_cached(self, limit: int = 10) -> dict[str, Any]:
        """Return cached news immediately if present, otherwise perform a scrape attempt."""
        cached = self.load_cache()
        if cached.get("articles"):
            articles = list(cached["articles"])[:limit]
            return {
                "fetched_at": cached.get("fetched_at"),
                "source": cached.get("source") or "cache",
                "sources_checked": cached.get("sources_checked") or [u for _, u in self.urls],
                "count": len(articles),
                "articles": articles,
            }
        return self.scrape_latest(limit=limit)

