"""Brand assets (SP-BRAND): favicon links, served content types, image sizes and README references."""

import http.server
import os
import re
import struct
import threading
import urllib.request
from html.parser import HTMLParser

import pytest

import server

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
INDEX_HTML = os.path.join(APP_DIR, "index.html")
IMG_DIR = os.path.join(ROOT, "docs", "img")
README = os.path.join(ROOT, "README.md")
IMAGE_MAX_BYTES = 400 * 1024
BANNER_SIZE = (1600, 500)
ICON_RELS = {"icon", "apple-touch-icon"}


class IconLinks(HTMLParser):
    """Collect the `<link rel="icon">` and `<link rel="apple-touch-icon">` tags of the head."""

    def __init__(self):
        super().__init__()
        self.links: list[dict[str, str | None]] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "link" and set((attributes.get("rel") or "").lower().split()) & ICON_RELS:
            self.links.append(attributes)


def icon_links():
    parser = IconLinks()
    with open(INDEX_HTML, encoding="utf-8") as fh:
        parser.feed(fh.read())
    return parser.links


def webp_size(path):
    """Width and height of a WebP file, from its VP8, VP8L or VP8X chunk."""
    with open(path, "rb") as fh:
        head = fh.read(30)
    assert head[:4] == b"RIFF" and head[8:12] == b"WEBP", path
    chunk = head[12:16]
    if chunk == b"VP8X":
        width = int.from_bytes(head[24:27], "little") + 1
        height = int.from_bytes(head[27:30], "little") + 1
    elif chunk == b"VP8L":
        bits = int.from_bytes(head[21:25], "little")
        width, height = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    else:
        width, height = struct.unpack("<HH", head[26:30])
        width, height = width & 0x3FFF, height & 0x3FFF
    return width, height


@pytest.fixture
def static_server():
    """server.py's handler on an ephemeral port, for the static files only."""
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def test_index_html_links_existing_icons():
    links = icon_links()
    by_type = {(link.get("rel"), link.get("type")): link for link in links}
    assert ("icon", "image/svg+xml") in by_type
    assert ("icon", "image/png") in by_type
    assert ("apple-touch-icon", None) in by_type
    for link in links:
        href = link.get("href") or ""
        assert href and not href.startswith(("http:", "https:", "/")), link
        assert os.path.isfile(os.path.join(APP_DIR, href)), href


def test_server_serves_the_icons_with_their_content_type(static_server):
    expected = {"img/favicon.svg": "image/svg+xml", "img/favicon-32.png": "image/png"}
    for path, content_type in expected.items():
        with urllib.request.urlopen(f"{static_server}/{path}", timeout=5) as resp:
            assert resp.status == 200
            assert resp.headers["Content-Type"] == content_type, path
            assert resp.headers["X-Content-Type-Options"] == "nosniff"
            policy = resp.headers["Content-Security-Policy"]
            assert re.search(r"img-src [^;]*'self'", policy), policy
            assert len(resp.read()) == os.path.getsize(os.path.join(APP_DIR, path))


def test_top_bar_heading_carries_the_mark():
    with open(INDEX_HTML, encoding="utf-8") as fh:
        page = fh.read()
    match = re.search(r'<h1 class="brand">(.*?)</h1>', page, re.S)
    assert match, "no h1.brand in index.html"
    heading = match.group(1)
    assert '<svg class="mark"' in heading
    assert 'aria-hidden="true"' in heading
    assert 'fill="currentColor"' in heading
    assert heading.rstrip().endswith("Sparring")


def test_images_are_small():
    files = sorted(os.listdir(IMG_DIR))
    assert files, "docs/img is empty"
    oversized = {name: os.path.getsize(os.path.join(IMG_DIR, name)) for name in files}
    oversized = {name: size for name, size in oversized.items() if size > IMAGE_MAX_BYTES}
    assert oversized == {}


@pytest.mark.parametrize("name", ["banner-light.webp", "banner-dark.webp"])
def test_banner_variants_are_1600_by_500(name):
    assert webp_size(os.path.join(IMG_DIR, name)) == BANNER_SIZE


def test_readme_references_existing_images_and_keeps_the_anchors():
    with open(README, encoding="utf-8") as fh:
        readme = fh.read()
    referenced = set(re.findall(r'(?:src|srcset)="(docs/img/[^"]+)"', readme))
    assert "docs/img/banner-light.webp" in referenced and "docs/img/banner-dark.webp" in referenced
    for path in referenced:
        assert os.path.isfile(os.path.join(ROOT, path)), path
    assert readme.index("banner-light.webp") < readme.index("## ")
    assert "actions/workflows/ci.yml/badge.svg" in readme
    assert "img.shields.io/badge/license-AGPL" in readme
    for heading in ("## What it is", "## Quick start", "## Development", "## Contributing"):
        assert heading in readme, heading
