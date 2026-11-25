"""README code blocks that end in asyncio.run() are full scripts and must compile as files."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"


def test_readme_scripts_compile() -> None:
    blocks = re.findall(r"```python\n(.*?)```", README.read_text(encoding="utf-8"), re.DOTALL)
    scripts = [code for code in blocks if "asyncio.run(" in code]
    assert len(scripts) >= 2
    for code in scripts:
        compile(code, "README.md", "exec")


def test_readme_links_are_absolute() -> None:
    # The README is also the PyPI description, where relative links break.
    assert re.findall(r"\]\((?!https?://)[^)]*\)", README.read_text(encoding="utf-8")) == []


def test_readme_first_script_type_checks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A typed codebase indexes the result without a None check or a cast
    api = pytest.importorskip("mypy.api")
    script = re.search(r"```python\n(.*?)```", README.read_text(encoding="utf-8"), re.DOTALL)[1]
    assert "btc[-1].close" in script
    monkeypatch.setenv("MYPYPATH", str(ROOT / "src"))
    out, err, status = api.run(
        ["--check-untyped-defs", "--follow-imports=silent", "--cache-dir", str(tmp_path), "-c", script]
    )
    assert status == 0, out + err
