"""Every relative link and image in the README and the docs points at a file that exists."""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FENCE = re.compile(r"^(```|~~~).*?^\1", re.M | re.S)
INLINE_CODE = re.compile(r"`[^`\n]*`")
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HTML_REF = re.compile(r"""(?:src|srcset|href)=["']([^"']+)["']""")
EXTERNAL = ("http://", "https://", "mailto:", "#", "data:")


def _documents() -> list[Path]:
    found = [REPO / "README.md", *sorted((REPO / "docs").rglob("*.md"))]
    found += sorted((REPO / "playbook").glob("*.md"))
    for name in ("SECURITY.md", "CLAUDE.md"):
        if (REPO / name).is_file():
            found.append(REPO / name)
    return found


def _references(text: str) -> list[str]:
    text = INLINE_CODE.sub("", FENCE.sub("", text))
    refs = MARKDOWN_LINK.findall(text) + HTML_REF.findall(text)
    return [r for r in refs if not r.startswith(EXTERNAL)]


def _missing(document: Path) -> list[str]:
    bad = []
    for ref in _references(document.read_text(encoding="utf-8")):
        target = ref.split("#", 1)[0]
        if target and not (document.parent / target).resolve().exists():
            bad.append(ref)
    return bad


@pytest.mark.parametrize("document", _documents(), ids=lambda p: str(p.relative_to(REPO)))
def test_every_relative_link_and_image_resolves(document: Path) -> None:
    assert _missing(document) == []


def test_the_scan_sees_links_images_and_html_and_ignores_code_and_external_urls() -> None:
    text = (
        '[a](docs/a.md) ![i](img/x.png) <img src="p/y.svg"> <source srcset="p/z.svg">\n'
        "[web](https://example.com) [anchor](#top) `[code](nope.md)`\n"
        "```\n[fenced](nope2.md)\n```\n"
    )
    assert _references(text) == ["docs/a.md", "img/x.png", "p/y.svg", "p/z.svg"]


def test_a_broken_link_is_reported(tmp_path: Path) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text("[gone](missing.md#part) [here](doc.md)", encoding="utf-8")
    assert _missing(doc) == ["missing.md#part"]


def test_the_readme_is_covered() -> None:
    assert REPO / "README.md" in _documents()
