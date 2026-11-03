"""Subresource Integrity on the third-party assets of app/index.html (SP-WEB-ASSETS)."""
import os
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(ROOT, "app", "index.html")
CDNJS_HOST = "cdnjs.cloudflare.com"
CDNJS_TAG_COUNT = 9
SHA384_DIGEST = re.compile(r"^sha384-[A-Za-z0-9+/]{64}$")


class ExternalAssets(HTMLParser):
    """Collect the `<script src>` and `<link rel="stylesheet" href>` tags with their attributes."""

    def __init__(self):
        super().__init__()
        self.tags: list[tuple[str, str, dict[str, str | None]]] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        rel = (attributes.get("rel") or "").lower().split()
        if tag == "script" and attributes.get("src"):
            self.tags.append((tag, attributes["src"], attributes))
        elif tag == "link" and "stylesheet" in rel and attributes.get("href"):
            self.tags.append((tag, attributes["href"], attributes))


def cdnjs_tags():
    parser = ExternalAssets()
    with open(INDEX_HTML, encoding="utf-8") as fh:
        parser.feed(fh.read())
    return [
        (tag, url, attributes)
        for tag, url, attributes in parser.tags
        if (urlsplit(url).hostname or "").lower() == CDNJS_HOST
    ]


CDNJS_TAGS = cdnjs_tags()


def test_index_html_loads_the_expected_number_of_cdnjs_assets():
    assert len(CDNJS_TAGS) == CDNJS_TAG_COUNT, [url for _, url, _ in CDNJS_TAGS]


@pytest.mark.parametrize(("tag", "url", "attributes"), CDNJS_TAGS, ids=[url for _, url, _ in CDNJS_TAGS])
def test_cdnjs_assets_carry_subresource_integrity(tag, url, attributes):
    integrity = attributes.get("integrity") or ""
    assert integrity.startswith("sha384-"), f"<{tag}> {url} has no sha384 integrity attribute"
    assert attributes.get("crossorigin") == "anonymous", f"<{tag}> {url} must be loaded with crossorigin=anonymous"


@pytest.mark.parametrize(("tag", "url", "attributes"), CDNJS_TAGS, ids=[url for _, url, _ in CDNJS_TAGS])
def test_integrity_values_are_sha384_digests(tag, url, attributes):
    assert SHA384_DIGEST.match(attributes.get("integrity") or ""), f"<{tag}> {url} has a malformed digest"


@pytest.mark.parametrize("value", [
    "",
    "sha384-",
    "sha256-" + "A" * 43 + "=",
    "sha512-" + "A" * 86 + "==",
    "sha384-" + "A" * 63,
    "sha384-" + "A" * 64 + "=",
    "sha384-" + "A" * 63 + "!",
    "SHA384-" + "A" * 64,
])
def test_digest_pattern_rejects_other_algorithms_and_malformed_values(value):
    assert not SHA384_DIGEST.match(value)


def test_parser_finds_cdnjs_tags_regardless_of_host_case_and_rel_tokens():
    parser = ExternalAssets()
    parser.feed(
        '<link rel="preload stylesheet" href="https://CDNJS.cloudflare.com/ajax/libs/x/1/x.css">'
        '<script src="https://cdnjs.cloudflare.com/ajax/libs/x/1/x.js"></script>'
        '<link rel="preconnect" href="https://cdnjs.cloudflare.com">'
        '<script src="js/app.js"></script>'
    )
    hosts = [(tag, (urlsplit(url).hostname or "").lower()) for tag, url, _ in parser.tags]
    assert hosts == [("link", CDNJS_HOST), ("script", CDNJS_HOST), ("script", "")]
