"""README code blocks that end in asyncio.run() are full scripts and must compile as files."""

from __future__ import annotations

import re
from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"


def test_readme_scripts_compile() -> None:
    blocks = re.findall(r"```python\n(.*?)```", README.read_text(encoding="utf-8"), re.DOTALL)
    scripts = [code for code in blocks if "asyncio.run(" in code]
    assert len(scripts) >= 2
    for code in scripts:
        compile(code, "README.md", "exec")


def test_readme_links_are_absolute() -> None:
    # The README is also the PyPI description, where relative links break.
    assert re.findall(r"\]\((?!https?://)[^)]*\)", README.read_text(encoding="utf-8")) == []
