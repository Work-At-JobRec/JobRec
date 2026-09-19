import os
import sys
from datetime import datetime, timezone

# Lets this test import app/src/job_normalization.py
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

from job_listing import JobListing  # noqa: E402
from job_normalization import clean_text, normalize_listing, normalize_listings, normalize_url  # noqa: E402


def make_listing(**overrides) -> JobListing:
    fields = {
        "title": "Software Engineer",
        "company_name": "Acme",
        "source": "greenhouse",
        "application_url": "https://acme.com/jobs?gh_jid=123",
    }
    fields.update(overrides)
    return JobListing(**fields)


# --- text fields ---

# Extra whitespace inside and around the title is removed
def test_title_whitespace_collapsed_and_stripped():
    listing = normalize_listing(make_listing(title="  Senior\t Engineer \n"))

    assert listing.title == "Senior Engineer"


# Company names are tidied but their capitalisation is left alone
def test_company_name_whitespace_collapsed_case_preserved():
    listing = normalize_listing(make_listing(company_name=" ACME  corp "))

    assert listing.company_name == "ACME corp"


# A location that is only whitespace means there is no location
def test_location_whitespace_only_becomes_none():
    assert normalize_listing(make_listing(location="   ")).location is None


# A missing location stays missing
def test_location_none_stays_none():
    assert normalize_listing(make_listing(location=None)).location is None


# --- description ---

# HTML tags are removed and the words are kept
def test_description_html_tags_removed_text_kept():
    text = clean_text("<h2><strong>Who we are</strong></h2><p>Acme builds <em>payments</em> tooling.</p>")

    assert "<" not in text and ">" not in text
    assert "Who we are" in text
    assert "Acme builds payments tooling." in text


# Paragraphs end up on separate lines
def test_description_block_tags_become_line_breaks():
    assert clean_text("<p>first</p><p>second</p>") == "first\n\nsecond"


# A <br> is a single line break
def test_description_br_becomes_single_line_break():
    assert clean_text("<p>one<br>two<br/>three</p>") == "one\ntwo\nthree"


# List items become dashed lines, even when the item wraps its text in a paragraph
def test_description_list_items_prefixed():
    assert clean_text("<ul><li>Python</li><li><p>SQL</p></li></ul>") == "- Python\n- SQL"


# HTML entities and non-breaking spaces are decoded
def test_description_entities_and_nbsp_decoded():
    assert clean_text("<p>R&amp;D&nbsp;&nbsp;team</p>") == "R&D team"


# Script and style contents never reach the description
def test_description_script_and_style_dropped():
    text = clean_text("<style>p{color:red}</style><p>Hello</p><script>alert(1)</script>")

    assert text == "Hello"


# Text after the last tag is not lost
def test_description_trailing_text_without_closing_tag_kept():
    assert clean_text("<p>Intro</p>Apply today") == "Intro\nApply today"


# Plain text keeps its own line breaks
def test_plain_text_description_newlines_preserved():
    assert clean_text("Line one\nLine two\n\nLine three") == "Line one\nLine two\n\nLine three"


# Plain text that merely contains a less-than sign is not treated as HTML
def test_plain_text_with_angle_bracket_is_not_parsed_as_html():
    assert clean_text("Must have a < 5 minute response & C++") == "Must have a < 5 minute response & C++"


# Long runs of blank lines are reduced to one blank line
def test_description_excess_blank_lines_collapsed():
    assert clean_text("a\n\n\n\n\nb") == "a\n\nb"


# Missing descriptions become an empty string
def test_empty_description_stays_empty():
    assert clean_text("") == ""
    assert clean_text(None) == ""


# --- application URL ---

# Surrounding whitespace is removed and the scheme and host are lowercased; the path is untouched
def test_url_stripped_and_scheme_host_lowercased():
    assert normalize_url(" HTTPS://Acme.COM/Jobs ") == "https://acme.com/Jobs"


# URLs without a scheme are assumed to be https, including ones with a port
def test_url_missing_scheme_gets_https():
    assert normalize_url("acme.com/jobs") == "https://acme.com/jobs"
    assert normalize_url("acme.com:8080/jobs") == "https://acme.com:8080/jobs"
    assert normalize_url("//acme.com/jobs") == "https://acme.com/jobs"


# An explicit http link is not silently upgraded
def test_url_http_scheme_is_kept():
    assert normalize_url("http://acme.com/jobs") == "http://acme.com/jobs"


# Fragments do not identify a job and are removed
def test_url_fragment_removed():
    assert normalize_url("https://acme.com/jobs/1#apply") == "https://acme.com/jobs/1"


# Tracking parameters are dropped; every other parameter keeps its order and encoding
def test_url_utm_params_removed_other_params_and_order_kept():
    url = "https://acme.com/jobs?b=2&utm_source=x&gh_jid=1&UTM_Medium=y&a=%20"

    assert normalize_url(url) == "https://acme.com/jobs?b=2&gh_jid=1&a=%20"


# An empty URL stays empty so validation can reject it
def test_empty_url_stays_empty():
    assert normalize_url("") == ""
    assert normalize_url("   ") == ""


# Links that are not web addresses are left alone
def test_non_web_url_left_unchanged():
    assert normalize_url("mailto:jobs@acme.com") == "mailto:jobs@acme.com"


# A URL that cannot be parsed is returned as it was given
def test_unparseable_url_returned_unchanged():
    assert normalize_url("http://[::1") == "http://[::1"


# --- whole listing ---

# Normalizing returns a new listing and never changes the one passed in
def test_normalize_returns_copy_and_leaves_original_untouched():
    original = make_listing(title="  Engineer  ")

    normalized = normalize_listing(original)

    assert normalized is not original
    assert original.title == "  Engineer  "
    assert normalized.title == "Engineer"


# Identity and timestamps pass through unchanged
def test_normalize_preserves_source_ids_and_timestamps():
    posted = datetime(2026, 9, 3, 13, 30, tzinfo=timezone.utc)
    original = make_listing(source_job_id="8172487", posted_at=posted)

    normalized = normalize_listing(original)

    assert normalized.source == "greenhouse"
    assert normalized.source_job_id == "8172487"
    assert normalized.posted_at == posted
    assert normalized.scraped_at == original.scraped_at


# Normalizing twice gives the same result as normalizing once
def test_normalize_is_idempotent():
    original = make_listing(
        title="  Senior   Engineer ",
        location=" Dublin ",
        description="<h2>About</h2><p>R&amp;D team</p><ul><li>Python</li><li>SQL</li></ul>",
        application_url=" HTTPS://Acme.com/jobs?utm_source=x&gh_jid=1#top ",
    )

    once = normalize_listing(original)
    twice = normalize_listing(once)

    assert twice == once
    assert once.description == "About\n\nR&D team\n\n- Python\n- SQL"


# The list helper normalizes every listing and keeps their order
def test_normalize_listings_maps_all_in_order():
    result = normalize_listings([make_listing(title=" A "), make_listing(title=" B ")])

    assert [listing.title for listing in result] == ["A", "B"]
