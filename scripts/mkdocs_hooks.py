"""MkDocs hook: point relative links into the repository's evidence/ folder at the repository on GitHub.

The docs link archived data with paths like `../../evidence/rounds/06-v3-main/`, which work when reading the Markdown
on GitHub. MkDocs only knows files inside docs/, so the built site rewrites them to repository URLs. A link that does
not resolve to an existing path in the repository fails the build (`scripts/check_doc_links.py` checks the same in CI).
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

REPO_URL = "https://github.com/manykarim/robotframework-harness"
ROOT = Path(__file__).resolve().parents[1]  # scripts/ -> repo root
LINK_RE = re.compile(r"\]\((?P<target>(?:\.\./)+evidence/[^)\s#]*)(?P<frag>#[^)\s]*)?\)")


def on_page_markdown(markdown: str, page, config, files):  # noqa: ANN001, ARG001
    src_dir = posixpath.dirname("docs/" + page.file.src_uri)

    def repl(m: re.Match) -> str:
        target = posixpath.normpath(posixpath.join(src_dir, m.group("target")))
        if not (ROOT / target).exists():
            raise ValueError(f"{page.file.src_uri}: link to missing repository path {target}")
        kind = "tree" if (ROOT / target).is_dir() else "blob"
        return f"]({REPO_URL}/{kind}/main/{target}{m.group('frag') or ''})"

    return LINK_RE.sub(repl, markdown)
