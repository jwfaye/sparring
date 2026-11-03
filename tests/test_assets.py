"""Subresource Integrity on the third-party assets of app/index.html (SP-WEB-ASSETS)."""
import os
import re
from html.parser import HTMLParser

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(ROOT, "app", "index.html")
CDNJS = "https://cdnjs.cloudflare.com/"
SHA384_DIGEST = re.compile(r"^sha384-[A-Za-z0-9+/]{64}$")


class ExternalAssets(HTMLParser):
    """Collect the `<script src>` and `<link rel="stylesheet" href>` tags with their attributes."""

    def __init__(self):
        super().__init__()
        self.tags: list[tuple[str, str, dict[str, str | None]]] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "script" and attributes.get("src"):
            self.tags.append((tag, attributes["src"], attributes))
        elif tag == "link" and attributes.get("rel") == "stylesheet" and attributes.get("href"):
            self.tags.append((tag, attributes["href"], attributes))


def cdnjs_tags():
    parser = ExternalAssets()
    with open(INDEX_HTML, encoding="utf-8") as fh:
        parser.feed(fh.read())
    return [(tag, url, attributes) for tag, url, attributes in parser.tags if url.startswith(CDNJS)]


@pytest.fixture(scope="module")
def tags():
    found = cdnjs_tags()
    assert len(found) == 9, [url for _, url, _ in found]
    return found


def test_cdnjs_assets_carry_subresource_integrity(tags):
    for tag, url, attributes in tags:
        integrity = attributes.get("integrity") or ""
        assert integrity.startswith("sha384-"), f"<{tag}> {url} has no sha384 integrity attribute"
        assert attributes.get("crossorigin") == "anonymous", f"<{tag}> {url} must be loaded with crossorigin=anonymous"


def test_integrity_values_are_sha384_digests(tags):
    for tag, url, attributes in tags:
        assert SHA384_DIGEST.match(attributes.get("integrity") or ""), f"<{tag}> {url} has a malformed digest"
