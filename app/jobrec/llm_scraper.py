"""Fallback scraper for company careers pages that are not hosted on a supported job board.

Greenhouse, Lever, Ashby and Workday all expose structured job data, and each has
its own scraper. Everything else is a plain web page. This scraper fetches such a
careers page over HTTP, asks the language model which of its links are individual
job postings, fetches each posting page, and asks the model to read the listing
fields off the page's visible text (the same Responses API pattern as resume
parsing in openaiapi.py).

Three rules keep it honest and affordable:

- Verbatim only (FR-004). A value the model returns is kept only if it appears in
  the page text; anything else is dropped, so a field the page does not state
  stays empty rather than guessed. A posting whose title is not on its page is
  skipped altogether. The posting links the model picks must be links the careers
  page actually contains.
- One model call per changed page. Pages are cached by URL with a digest of their
  text; an unchanged page is served from the cache without a model call. The cache
  can be saved to a JSON file so scheduled runs do not start cold.
- Plain HTTP only. A careers page whose static HTML contains no links renders its
  listings with JavaScript; it is logged as unsupported and yields nothing.

Sources hosted on a supported job board are refused by the registry (see
``structured_source_for``), so they are never routed through the model.
"""

import hashlib
import json
import logging
import os
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlsplit

import requests
from pydantic import BaseModel, Field

from jobrec.job_listing import JobListing
from jobrec.link_check import _CLOSED_MARKERS  # the phrases careers sites show for a filled or expired job
from jobrec.scraper_base import DEFAULT_TIMEOUT, BaseScraper, ScraperRequestError

logger = logging.getLogger(__name__)

# The model is configurable because accounts differ in which models they may use.
MODEL_ENV = "JOBREC_LLM_MODEL"
DEFAULT_MODEL = "gpt-5.2"
USER_AGENT = "Mozilla/5.0 (compatible; JobRecScraper/1.0; +https://github.com/Work-At-JobRec/JobRec)"
# At most this much page text is sent to the model per call.
MAX_PAGE_CHARS = 40_000
# A careers page listing more postings than this is cut off; each posting costs a model call.
MAX_POSTINGS = 200

# Hosts of the job boards that have their own scraper, and that scraper's registry name.
STRUCTURED_HOSTS = (
    ("greenhouse.io", "greenhouse"),
    ("lever.co", "lever"),
    ("ashbyhq.com", "ashby"),
    ("myworkdayjobs.com", "workday"),
)

LINKS_INSTRUCTIONS = (
    "You are given the visible text of a company careers page and the list of links on it. "
    "Return the URLs of the links that each lead to one individual job posting. "
    "Do not include links to the careers page itself, to departments, categories, locations, "
    "the company's other pages, or external sites. Return only URLs that appear in the list."
)
EXTRACT_INSTRUCTIONS = (
    "You are given the visible text of one job posting page. Read the listing's fields off it. "
    "Copy every value exactly as it appears in the text, character for character: the job title, "
    "the location, the pay or salary line, and the description paragraphs. If the page does not "
    "state a value, leave it null; never infer or summarize. Set status to \"closed\" only if the "
    "page says the job is no longer open, filled, or expired; otherwise \"open\"."
)


def structured_source_for(url: str) -> Optional[str]:
    """The registry name of the scraper that handles this URL's job board, or None for an ordinary site."""
    host = (urlsplit(url).hostname or "").lower()
    for suffix, name in STRUCTURED_HOSTS:
        if host == suffix or host.endswith("." + suffix):
            return name
    return None


class PostingLinks(BaseModel):
    urls: list[str] = Field(..., description="URLs from the given list that each lead to one individual job posting")


class ExtractedListing(BaseModel):
    title: Optional[str] = Field(None, description="Job title exactly as written on the page")
    location: Optional[str] = Field(None, description="Location exactly as written on the page, if stated")
    description: Optional[str] = Field(None, description="The description text exactly as written on the page")
    pay: Optional[str] = Field(None, description="Pay or salary line exactly as written on the page, if stated")
    status: Optional[str] = Field(None, description='"open", or "closed" if the page says the job is no longer open')


# --- reading a page ---

_SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "head"}
_BLOCK_TAGS = {
    "p", "div", "li", "ul", "ol", "br", "tr", "td", "th", "table", "section", "article", "header",
    "footer", "nav", "main", "aside", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre",
}


class _PageParser(HTMLParser):
    """Collects the visible text of a page and its links as absolute (href, anchor text) pairs."""

    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._skipping = 0
        self._href: Optional[str] = None
        self._anchor: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skipping += 1
            return
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._anchor = []

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skipping = max(0, self._skipping - 1)
            return
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "a" and self._href is not None:
            absolute = urljoin(self.base_url, self._href.strip())
            if urlsplit(absolute).scheme in ("http", "https"):
                self.links.append((absolute, " ".join("".join(self._anchor).split())))
            self._href = None
            self._anchor = []

    def handle_data(self, data):
        if self._skipping:
            return
        self.parts.append(data)
        if self._href is not None:
            self._anchor.append(data)


def _tidy(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def page_text_and_links(html: str, base_url: str) -> tuple[str, list[tuple[str, str]]]:
    """Visible text of a page (scripts and styles removed) and its links, absolute and in page order, without repeats."""
    parser = _PageParser(base_url)
    parser.feed(html or "")
    parser.close()
    seen: set[str] = set()
    links = []
    for href, anchor in parser.links:
        if href not in seen:
            seen.add(href)
            links.append((href, anchor))
    return _tidy("".join(parser.parts)), links


def _squash(value: str) -> str:
    return " ".join(value.split()).lower()


def _verbatim(value: Optional[str], text: str) -> Optional[str]:
    """The value itself when it appears in the text (ignoring case and spacing), else None."""
    if value is None or not value.strip():
        return None
    return value if _squash(value) in _squash(text) else None


def _page_says_closed(text: str) -> bool:
    lowered = _squash(text)
    return any(marker in lowered for marker in _CLOSED_MARKERS)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- cache ---


class PageCache:
    """What the model said about each page, keyed by URL and valid while the page's text digest is unchanged."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else None
        self.entries: dict[str, dict[str, Any]] = {}
        if self.path and self.path.exists():
            try:
                self.entries = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                logger.warning("Ignoring unreadable page cache %s: %s", self.path, exc)
                self.entries = {}

    def get(self, url: str, digest: str) -> Any:
        entry = self.entries.get(url)
        return entry["value"] if entry and entry.get("digest") == digest else None

    def put(self, url: str, digest: str, value: Any) -> None:
        self.entries[url] = {"digest": digest, "value": value}

    def save(self) -> None:
        if self.path:
            self.path.write_text(json.dumps(self.entries, indent=1), encoding="utf-8")


# --- the scraper ---


class LlmPageScraper(BaseScraper):
    source_name = "llm"

    def __init__(
        self,
        careers_url: str,
        company_name: Optional[str] = None,
        session: Optional[requests.Session] = None,
        client=None,
        model: Optional[str] = None,
        cache: Optional[PageCache] = None,
    ):
        super().__init__(session=session)
        self.careers_url = careers_url
        self.company_name = company_name or (urlsplit(careers_url).hostname or careers_url)
        # The OpenAI client is created on first use so tests can inject a stand-in and the
        # scraper can be built without an API key.
        self._client = client
        self.model = model or os.environ.get(MODEL_ENV, DEFAULT_MODEL)
        self.cache = cache if cache is not None else PageCache()

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI()
        return self._client

    def fetch_jobs(self) -> list[JobListing]:
        html = self._get_html(self.careers_url)
        text, links = page_text_and_links(html, self.careers_url)
        if not links:
            logger.warning(
                "Unsupported careers page %s: its static HTML has no links, so its listings are rendered with JavaScript",
                self.careers_url,
            )
            return []

        posting_urls = self._posting_links(text, links)
        if not posting_urls:
            logger.info("No job postings identified on %s", self.careers_url)
            return []
        if len(posting_urls) > MAX_POSTINGS:
            logger.warning("%s lists %d postings; only the first %d are read", self.careers_url, len(posting_urls), MAX_POSTINGS)
            posting_urls = posting_urls[:MAX_POSTINGS]

        listings = []
        for url in posting_urls:
            try:
                page_html = self._get_html(url)
            except ScraperRequestError as exc:
                logger.warning("Skipping posting %s: %s", url, exc)
                continue
            page_text, _ = page_text_and_links(page_html, url)
            listing = self._to_listing(url, page_text, self._extract(url, page_text))
            if listing is not None:
                listings.append(listing)
        return listings

    def _get_html(self, url: str) -> str:
        try:
            response = self.session.get(url, timeout=DEFAULT_TIMEOUT, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            failed_response = getattr(exc, "response", None)
            status = getattr(failed_response, "status_code", None)
            detail = f"HTTP {status}: {exc}" if status is not None else str(exc)
            logger.error("Request failed (source=%s, url=%s): %s", self.source_name, url, detail)
            raise ScraperRequestError(self.source_name, url, detail) from exc

    def _ask(self, text: str, text_format: type[BaseModel], instructions: str):
        response = self.client.responses.parse(
            model=self.model,
            instructions=instructions,
            input=[{"role": "user", "content": [{"type": "input_text", "text": text[:MAX_PAGE_CHARS]}]}],
            text_format=text_format,
        )
        return response.output_parsed

    def _posting_links(self, text: str, links: list[tuple[str, str]]) -> list[str]:
        """The careers page's links that lead to individual postings, as the model picks them (cached per page)."""
        digest = _digest(text + "\n" + "\n".join(href for href, _ in links))
        urls = self.cache.get(self.careers_url, digest)
        if urls is None:
            link_lines = "\n".join(f"{href} | {anchor}" for href, anchor in links)
            prompt = f"Careers page: {self.careers_url}\n\nLinks (URL | link text):\n{link_lines}\n\nPage text:\n{text}"
            answer = self._ask(prompt, PostingLinks, LINKS_INSTRUCTIONS)
            urls = list(answer.urls) if answer is not None else []
            self.cache.put(self.careers_url, digest, urls)

        known = {href for href, _ in links}
        kept: list[str] = []
        for url in urls:
            if url not in known:
                logger.warning("Ignoring posting link %s: it is not on %s", url, self.careers_url)
            elif url not in kept:
                kept.append(url)
        return kept

    def _extract(self, url: str, page_text: str) -> ExtractedListing:
        """What the model reads off a posting page (cached while the page is unchanged)."""
        digest = _digest(page_text)
        cached = self.cache.get(url, digest)
        if cached is not None:
            return ExtractedListing.model_validate(cached)
        extracted = self._ask(f"Posting page: {url}\n\n{page_text}", ExtractedListing, EXTRACT_INSTRUCTIONS) or ExtractedListing()
        self.cache.put(url, digest, extracted.model_dump())
        return extracted

    def _to_listing(self, url: str, page_text: str, extracted: ExtractedListing) -> Optional[JobListing]:
        """A JobListing holding only the extracted values that appear on the page; None when the title does not."""
        title = _verbatim(extracted.title, page_text)
        if title is None:
            logger.warning("Skipping %s: the extracted title %r is not on the page", url, extracted.title)
            return None
        # A description the model rewrote is replaced by the page's own text, which is verbatim by construction.
        description = _verbatim(extracted.description, page_text) or page_text
        status = "closed" if (extracted.status or "").strip().lower() == "closed" and _page_says_closed(page_text) else "open"
        return JobListing(
            title=title,
            company_name=self.company_name,
            location=_verbatim(extracted.location, page_text),
            description=description,
            source=self.source_name,
            application_url=url,
            pay=_verbatim(extracted.pay, page_text),
            status=status,
        )
