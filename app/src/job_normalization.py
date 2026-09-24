"""Normalization for scraped job listings.

Different job sources format the same information differently. This module
produces consistent values (tidy whitespace, plain-text descriptions, canonical
application URLs) so that storage, duplicate detection, and recommendation
logic can compare listings reliably. The meaning of the data is never changed,
and normalizing an already-normalized listing is a no-op.
"""

import html
import re
from html.parser import HTMLParser
from typing import Iterable, Optional
from urllib.parse import urlsplit, urlunsplit

from job_listing import JobListing

# Tags that start a new line in the plain-text version of a description.
_BLOCK_TAGS = {
    "p", "div", "br", "hr", "ul", "ol", "tr", "table", "section", "article",
    "blockquote", "pre", "h1", "h2", "h3", "h4", "h5", "h6",
}
# Tags whose contents are code or styling, never job information.
_SKIPPED_TAGS = {"script", "style"}
# Only run the HTML parser on text that actually contains a tag, so plain text keeps its line breaks.
_LOOKS_LIKE_HTML = re.compile(r"</?[a-zA-Z][^>]*>")
_HAS_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
_NON_WEB_SCHEMES = ("mailto:", "tel:", "javascript:")
_TRACKING_PARAM_PREFIX = "utm_"


class _TextExtractor(HTMLParser):
    """Collects the readable text of an HTML fragment, turning block structure into line breaks."""

    def __init__(self):
        super().__init__(convert_charrefs=True)  # entities such as &amp; arrive already decoded
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIPPED_TAGS:
            self._skip_depth += 1
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIPPED_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _BLOCK_TAGS and tag != "br":
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            # Line breaks inside HTML source are only whitespace, not structure.
            self.parts.append(re.sub(r"\s+", " ", data))


def _collapse_whitespace(value: str) -> str:
    """Replace every run of whitespace with a single space and trim the ends."""
    return re.sub(r"\s+", " ", value).strip()


def clean_text(value: Optional[str]) -> str:
    """Convert a scraped description to tidy plain text.

    HTML tags are removed (paragraphs and headings become line breaks, list items
    become "- " lines, link text is kept), entities are decoded, and runs of
    spaces or blank lines are collapsed.
    """
    value = value or ""
    if _LOOKS_LIKE_HTML.search(value):
        parser = _TextExtractor()
        parser.feed(value)
        parser.close()  # flushes any text still buffered after the last tag
        text = "".join(parser.parts)
    else:
        text = html.unescape(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("​", "")
    text = re.sub(r"[^\S\n]+", " ", text)          # runs of spaces, tabs, non-breaking spaces
    text = re.sub(r" ?\n ?", "\n", text)           # no spaces hugging a line break
    text = re.sub(r"(?m)^-\n+", "- ", text)        # <li><p>text</p></li> keeps its dash on the same line
    text = re.sub(r"\n{3,}", "\n\n", text)         # at most one blank line in a row
    return text.strip()


def normalize_url(url: Optional[str]) -> str:
    """Return a canonical form of an application URL.

    Trims whitespace, assumes https when no scheme is given, lowercases the scheme
    and host, and removes the fragment and utm_* tracking parameters. Everything
    that identifies the job (path, other query parameters and their order) is
    preserved. An empty URL stays empty so that validation can reject it.
    """
    url = (url or "").strip()
    if not url or url.lower().startswith(_NON_WEB_SCHEMES):
        return url
    candidate = url
    if candidate.startswith("//"):
        candidate = "https:" + candidate
    elif not _HAS_SCHEME.match(candidate):
        candidate = "https://" + candidate
    try:
        parts = urlsplit(candidate)
        host = (parts.hostname or "").lower()
        if ":" in host:  # IPv6 literal: hostname drops the brackets
            host = f"[{host}]"
        netloc = host + (f":{parts.port}" if parts.port else "")
    except ValueError:
        return url
    if "@" in parts.netloc:  # keep any user info exactly as given
        netloc = parts.netloc.rsplit("@", 1)[0] + "@" + netloc
    # Filter the raw pieces rather than re-encoding, so order and escaping stay byte-identical.
    query = "&".join(
        piece for piece in parts.query.split("&")
        if piece and not piece.split("=", 1)[0].lower().startswith(_TRACKING_PARAM_PREFIX)
    )
    return urlunsplit((parts.scheme.lower(), netloc, parts.path, query, ""))


def normalize_listing(listing: JobListing) -> JobListing:
    """Return a normalized copy of a listing. The listing passed in is not modified."""
    location = _collapse_whitespace(listing.location) if listing.location else ""
    return listing.model_copy(update={
        "title": _collapse_whitespace(listing.title),
        "company_name": _collapse_whitespace(listing.company_name),
        "location": location or None,
        "description": clean_text(listing.description),
        "application_url": normalize_url(listing.application_url),
    })


def normalize_listings(listings: Iterable[JobListing]) -> list[JobListing]:
    """Normalize every listing, keeping their order."""
    return [normalize_listing(listing) for listing in listings]
