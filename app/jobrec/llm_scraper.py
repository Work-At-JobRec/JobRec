"""Fallback scraper for company careers pages that are not hosted on a supported job board.

Greenhouse, Lever, Ashby and Workday all expose structured job data, and each has
its own scraper. Everything else is a plain web page. This scraper fetches such a
careers page over HTTP, asks the language model which of its links are individual
job postings, fetches each posting page, and asks the model to read the listing
fields off the page's visible text (the same Responses API pattern as resume
parsing in openaiapi.py).

Four rules keep it honest and affordable:

- Verbatim only (FR-004). A value the model returns is kept only if it appears in
  the page text; anything else is dropped, so a field the page does not state
  stays empty rather than guessed. A posting whose title is not on its page is
  skipped altogether. The posting links the model picks must be links the careers
  page actually contains.
- One model call per changed page. Pages are cached by URL with a digest of their
  text; an unchanged page is served from the cache without a model call. The cache
  can be saved to a JSON file so scheduled runs do not start cold.
- A cap on model calls per run. Every scraper in one process shares one budget
  (``JOBREC_LLM_MAX_CALLS``, default 300); when it runs out the scraper keeps what it
  has and logs how many postings it skipped. Answers served from the cache are free.
- Plain HTTP only, no browser. When a careers page shows no postings in its static
  HTML (it renders them with JavaScript), the scraper tries, in order, the schema.org
  ``JobPosting`` data embedded in the page (read directly, no model call) and the
  site's ``sitemap.xml``. A page with neither is logged as unsupported.

A posting's stored description falls back to the page's main content (``<main>``,
then ``<article>``, then the page without its navigation, header, footer and
sidebars), so site menus are not stored as part of the job.

Sources hosted on a supported job board are refused by the registry (see
``structured_source_for``), so they are never routed through the model.
"""

import hashlib
import html as html_lib
import json
import logging
import os
import re
from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, NamedTuple, Optional
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
# Model calls allowed in one process (one scrape_all run), across every LLM source.
MAX_CALLS_ENV = "JOBREC_LLM_MAX_CALLS"
DEFAULT_MAX_CALLS = 300
# At most this many sitemap URLs are offered to the model as candidate postings.
MAX_SITEMAP_LINKS = 1000

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
# Regions that hold a page's own content, and the site chrome around it.
_CONTENT_TAGS = {"main", "article"}
_CHROME_TAGS = {"nav", "header", "footer", "aside"}
_BLOCK_TAGS = {
    "p", "div", "li", "ul", "ol", "br", "tr", "td", "th", "table", "section", "article", "header",
    "footer", "nav", "main", "aside", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre",
}


class _PageParser(HTMLParser):
    """Collects the visible text of a page and its links as absolute (href, anchor text) pairs.

    It also keeps the text of each ``<main>`` and ``<article>``, the text outside the
    navigation, header, footer and sidebars, and the page's JSON-LD blocks.
    """

    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.regions: list[tuple[str, list[str]]] = []  # (tag, text parts) per <main> / <article>
        self.unframed_parts: list[str] = []  # text outside nav, header, footer and aside
        self.json_ld: list[str] = []
        self._open_regions: list[int] = []
        self._chrome = 0
        self._json_ld: Optional[list[str]] = None
        self._skipping = 0
        self._href: Optional[str] = None
        self._anchor: list[str] = []

    def _emit(self, text: str) -> None:
        self.parts.append(text)
        for index in self._open_regions:
            self.regions[index][1].append(text)
        if not self._chrome:
            self.unframed_parts.append(text)

    def handle_starttag(self, tag, attrs):
        if tag == "script" and (dict(attrs).get("type") or "").strip().lower() == "application/ld+json":
            self._json_ld = []
        if tag in _SKIP_TAGS:
            self._skipping += 1
            return
        if tag in _BLOCK_TAGS:
            self._emit("\n")
        if tag in _CONTENT_TAGS:
            self.regions.append((tag, []))
            self._open_regions.append(len(self.regions) - 1)
        if tag in _CHROME_TAGS:
            self._chrome += 1
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._anchor = []

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            if tag == "script" and self._json_ld is not None:
                self.json_ld.append("".join(self._json_ld))
                self._json_ld = None
            self._skipping = max(0, self._skipping - 1)
            return
        if tag in _CONTENT_TAGS:
            for position in range(len(self._open_regions) - 1, -1, -1):
                if self.regions[self._open_regions[position]][0] == tag:
                    del self._open_regions[position]
                    break
        if tag in _CHROME_TAGS:
            self._chrome = max(0, self._chrome - 1)
        if tag in _BLOCK_TAGS:
            self._emit("\n")
        if tag == "a" and self._href is not None:
            absolute = urljoin(self.base_url, self._href.strip())
            if urlsplit(absolute).scheme in ("http", "https"):
                self.links.append((absolute, " ".join("".join(self._anchor).split())))
            self._href = None
            self._anchor = []

    def handle_data(self, data):
        if self._json_ld is not None:
            self._json_ld.append(data)
        if self._skipping:
            return
        self._emit(data)
        if self._href is not None:
            self._anchor.append(data)


def _tidy(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class Page(NamedTuple):
    text: str  # all visible text
    links: list[tuple[str, str]]  # absolute (href, anchor text), in page order, without repeats
    main_text: str  # the page's own content, without site navigation (see main_content_text)
    json_ld: list[str]  # raw <script type="application/ld+json"> blocks


def read_page(html: str, base_url: str) -> Page:
    """Parse a page once into its visible text, links, main content text and JSON-LD blocks."""
    parser = _PageParser(base_url)
    parser.feed(html or "")
    parser.close()
    seen: set[str] = set()
    links = []
    for href, anchor in parser.links:
        if href not in seen:
            seen.add(href)
            links.append((href, anchor))
    text = _tidy("".join(parser.parts))

    def longest(tag: str) -> str:
        texts = [_tidy("".join(parts)) for region_tag, parts in parser.regions if region_tag == tag]
        return max(texts, key=len, default="")

    main_text = longest("main") or longest("article") or _tidy("".join(parser.unframed_parts)) or text
    return Page(text, links, main_text, parser.json_ld)


def page_text_and_links(html: str, base_url: str) -> tuple[str, list[tuple[str, str]]]:
    """Visible text of a page (scripts and styles removed) and its links, absolute and in page order, without repeats."""
    page = read_page(html, base_url)
    return page.text, page.links


def main_content_text(html: str, base_url: str) -> str:
    """The text of a page's own content: its <main>, else its longest <article>, else the page
    without nav, header, footer and aside, else all of it."""
    return read_page(html, base_url).main_text


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


# --- structured data embedded in the page (schema.org JobPosting) ---


def _is_job_posting(node: dict) -> bool:
    kind = node.get("@type")
    kinds = kind if isinstance(kind, list) else [kind]
    return "JobPosting" in kinds


def job_postings_from_json_ld(blocks: list[str]) -> list[dict]:
    """Every schema.org JobPosting object in the page's JSON-LD blocks (including @graph and item lists)."""
    found: list[dict] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            if _is_job_posting(node):
                found.append(node)
                return
            for key in ("@graph", "itemListElement", "item"):
                if key in node:
                    walk(node[key])

    for block in blocks:
        try:
            walk(json.loads(block))
        except ValueError:
            logger.debug("Ignoring a JSON-LD block that is not valid JSON")
    return found


def _text(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _posting_location(posting: dict) -> Optional[str]:
    places = posting.get("jobLocation")
    places = places if isinstance(places, list) else [places]
    names = []
    for place in places:
        address = place.get("address") if isinstance(place, dict) else None
        if isinstance(address, dict):
            parts = [_text(address.get(key)) for key in ("addressLocality", "addressRegion", "addressCountry")]
            name = ", ".join(part for part in parts if part)
        else:
            name = _text(address) or ""
        if name and name not in names:
            names.append(name)
    if str(posting.get("jobLocationType") or "").upper() == "TELECOMMUTE":
        names.append("Remote")
    return "; ".join(names) or None


def _posting_pay(posting: dict) -> Optional[str]:
    salary = posting.get("baseSalary")
    if not isinstance(salary, dict):
        return None
    value = salary.get("value")
    if isinstance(value, dict):
        low, high, unit = value.get("minValue"), value.get("maxValue"), _text(value.get("unitText"))
        amounts = [
            f"{amount:,}" if isinstance(amount, (int, float)) else str(amount) for amount in (low, high) if amount is not None
        ]
        if not amounts and value.get("value") is not None:
            amounts = [str(value["value"])]
    else:
        unit = None
        amounts = [str(value)] if value is not None else []
    if not amounts:
        return None
    line = f"{_text(salary.get('currency')) or ''} {'-'.join(amounts)}".strip()
    return f"{line} ({unit.lower()})" if unit else line


def _posting_date(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _sitemap_urls(xml: str) -> list[str]:
    return [html_lib.unescape(url.strip()) for url in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", xml or "")]


# --- model call budget ---


class ModelCallLimitReached(Exception):
    """The run's model call budget is spent."""


class ModelCallBudget:
    """How many model calls the LLM scrapers in one process may still make."""

    def __init__(self, limit: int):
        self.limit = limit
        self.used = 0

    @classmethod
    def from_env(cls) -> "ModelCallBudget":
        raw = os.environ.get(MAX_CALLS_ENV, "")
        try:
            limit = int(raw) if raw.strip() else DEFAULT_MAX_CALLS
        except ValueError:
            logger.warning("Ignoring %s=%r: not a whole number; using %d", MAX_CALLS_ENV, raw, DEFAULT_MAX_CALLS)
            limit = DEFAULT_MAX_CALLS
        return cls(max(0, limit))

    def spend(self) -> None:
        if self.used >= self.limit:
            raise ModelCallLimitReached(f"model call cap of {self.limit} reached")
        self.used += 1


# Shared by every LlmPageScraper in this process, so the cap covers the whole scrape_all run.
RUN_BUDGET = ModelCallBudget.from_env()


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
        budget: Optional[ModelCallBudget] = None,
    ):
        super().__init__(session=session)
        self.careers_url = careers_url
        self.company_name = company_name or (urlsplit(careers_url).hostname or careers_url)
        # The OpenAI client is created on first use so tests can inject a stand-in and the
        # scraper can be built without an API key.
        self._client = client
        self.model = model or os.environ.get(MODEL_ENV, DEFAULT_MODEL)
        self.cache = cache if cache is not None else PageCache()
        self.budget = budget if budget is not None else RUN_BUDGET

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI()
        return self._client

    def fetch_jobs(self) -> list[JobListing]:
        page = read_page(self._get_html(self.careers_url), self.careers_url)
        try:
            posting_urls = self._posting_links(page.text, page.links) if page.links else []
            if not posting_urls:
                # The postings may be rendered with JavaScript: try the page's own structured data, then the sitemap.
                embedded = self._listings_from_json_ld(page.json_ld)
                if embedded:
                    logger.info("Read %d posting(s) from the structured data on %s", len(embedded), self.careers_url)
                    return embedded
                sitemap_links = self._sitemap_links()
                if sitemap_links:
                    posting_urls = self._posting_links(page.text, sitemap_links, cache_key=self.careers_url + "#sitemap")
        except ModelCallLimitReached:
            logger.warning("Model call cap of %d reached; %s was not read", self.budget.limit, self.careers_url)
            return []
        if not posting_urls:
            if page.links:
                logger.info("No job postings identified on %s", self.careers_url)
            else:
                logger.warning(
                    "Unsupported careers page %s: its static HTML has no links, structured data or sitemap postings, "
                    "so its listings are rendered with JavaScript",
                    self.careers_url,
                )
            return []
        if len(posting_urls) > MAX_POSTINGS:
            logger.warning("%s lists %d postings; only the first %d are read", self.careers_url, len(posting_urls), MAX_POSTINGS)
            posting_urls = posting_urls[:MAX_POSTINGS]

        listings = []
        for index, url in enumerate(posting_urls):
            try:
                posting = read_page(self._get_html(url), url)
            except ScraperRequestError as exc:
                logger.warning("Skipping posting %s: %s", url, exc)
                continue
            try:
                extracted = self._extract(url, posting.text)
            except ModelCallLimitReached:
                logger.warning(
                    "Model call cap of %d reached after %d call(s); %d posting(s) on %s skipped",
                    self.budget.limit,
                    self.budget.used,
                    len(posting_urls) - index,
                    self.careers_url,
                )
                break
            listing = self._to_listing(url, posting.text, extracted, main_text=posting.main_text)
            if listing is not None:
                listings.append(listing)
        logger.info(
            "%s: %d model call(s) used so far this run (cap %d)", self.careers_url, self.budget.used, self.budget.limit
        )
        return listings

    def _listings_from_json_ld(self, blocks: list[str]) -> list[JobListing]:
        """Listings built straight from the schema.org JobPosting data a page embeds (no model call).

        The values are the page's own published data, so they are verbatim by construction.
        Postings without their own URL are used only when the page holds a single posting.
        """
        postings = job_postings_from_json_ld(blocks)
        now = datetime.now(timezone.utc)
        listings = []
        for posting in postings[:MAX_POSTINGS]:
            url = _text(posting.get("url"))
            url = urljoin(self.careers_url, url) if url else (self.careers_url if len(postings) == 1 else None)
            title = _text(posting.get("title"))
            if not url or not title:
                continue
            closes = _posting_date(posting.get("validThrough"))
            identifier = posting.get("identifier")
            job_id = identifier.get("value") if isinstance(identifier, dict) else identifier
            try:
                listings.append(
                    JobListing(
                        title=title,
                        company_name=self.company_name,
                        location=_posting_location(posting),
                        description=_text(posting.get("description")) or "",
                        source=self.source_name,
                        application_url=url,
                        posted_at=_posting_date(posting.get("datePosted")),
                        source_job_id=str(job_id) if job_id not in (None, "") else None,
                        pay=_posting_pay(posting),
                        status="closed" if closes is not None and closes < now else "open",
                    )
                )
            except ValueError as exc:
                logger.warning("Skipping a structured-data posting on %s: %s", self.careers_url, exc)
        return listings

    def _sitemap_links(self) -> list[tuple[str, str]]:
        """Same-site URLs from /sitemap.xml that look like postings, as (url, "") link pairs."""
        parts = urlsplit(self.careers_url)
        try:
            xml = self._get_html(f"{parts.scheme}://{parts.netloc}/sitemap.xml")
        except ScraperRequestError:
            return []
        careers_path = parts.path.rstrip("/") + "/"
        links = []
        for url in _sitemap_urls(xml):
            candidate = urlsplit(url)
            path = candidate.path.lower()
            if candidate.netloc != parts.netloc or url.rstrip("/") == self.careers_url.rstrip("/"):
                continue
            if candidate.path.startswith(careers_path) or any(word in path for word in ("job", "career", "position")):
                links.append((url, ""))
        return links[:MAX_SITEMAP_LINKS]

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
        self.budget.spend()
        response = self.client.responses.parse(
            model=self.model,
            instructions=instructions,
            input=[{"role": "user", "content": [{"type": "input_text", "text": text[:MAX_PAGE_CHARS]}]}],
            text_format=text_format,
        )
        return response.output_parsed

    def _posting_links(self, text: str, links: list[tuple[str, str]], cache_key: Optional[str] = None) -> list[str]:
        """The careers page's links that lead to individual postings, as the model picks them (cached per page)."""
        cache_key = cache_key or self.careers_url
        digest = _digest(text + "\n" + "\n".join(href for href, _ in links))
        urls = self.cache.get(cache_key, digest)
        if urls is None:
            link_lines = "\n".join(f"{href} | {anchor}" for href, anchor in links)
            prompt = f"Careers page: {self.careers_url}\n\nLinks (URL | link text):\n{link_lines}\n\nPage text:\n{text}"
            answer = self._ask(prompt, PostingLinks, LINKS_INSTRUCTIONS)
            urls = list(answer.urls) if answer is not None else []
            self.cache.put(cache_key, digest, urls)

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

    def _to_listing(
        self, url: str, page_text: str, extracted: ExtractedListing, main_text: Optional[str] = None
    ) -> Optional[JobListing]:
        """A JobListing holding only the extracted values that appear on the page; None when the title does not."""
        title = _verbatim(extracted.title, page_text)
        if title is None:
            logger.warning("Skipping %s: the extracted title %r is not on the page", url, extracted.title)
            return None
        # A description the model rewrote is replaced by the page's own main content (without the site's
        # navigation, header and footer), which is verbatim by construction.
        description = _verbatim(extracted.description, page_text) or main_text or page_text
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
