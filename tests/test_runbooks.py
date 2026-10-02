from __future__ import annotations

from pathlib import Path

import pytest

from runbook_retriever.config import REPO_ROOT
from runbook_retriever.runbooks import REQUIRED_SECTIONS, load_runbooks

FILLER = " ".join(["word"] * 40)


def write_runbook(
    directory: Path,
    name: str,
    *,
    sections: tuple[str, ...] = REQUIRED_SECTIONS,
    related: str = "[]",
    front: str | None = None,
) -> None:
    fm = front or (
        "title: Example runbook\nscope: Scope sentence for the example.\n"
        f"tools: [kubectl get pods]\ncautions: [Be careful]\nrelated: {related}\n"
    )
    body = "\n\n".join(f"## {s}\n\n{FILLER}" for s in sections)
    (directory / f"{name}.md").write_text(f"---\n{fm}---\n\nIntro.\n\n{body}\n", encoding="utf-8")


def test_repo_runbooks_are_valid() -> None:
    runbooks = load_runbooks(REPO_ROOT / "runbooks")
    assert len(runbooks) >= 20
    assert len({rb.meta.title for rb in runbooks}) == len(runbooks), "titles must be unique"


def test_valid_example(tmp_path: Path) -> None:
    write_runbook(tmp_path, "a-ok")
    write_runbook(tmp_path, "b-ok", related="[a-ok]")
    assert [rb.id for rb in load_runbooks(tmp_path)] == ["a-ok", "b-ok"]


def test_reports_every_problem(tmp_path: Path) -> None:
    write_runbook(tmp_path, "Bad_Name")
    write_runbook(tmp_path, "missing-fix", sections=REQUIRED_SECTIONS[:3])
    write_runbook(tmp_path, "dangling", related="[nope]")
    with pytest.raises(ValueError) as exc:
        load_runbooks(tmp_path)
    msg = str(exc.value)
    assert "Bad_Name: file name" in msg
    assert "missing-fix: H2 sections" in msg
    assert "dangling: related runbook 'nope'" in msg


def test_bad_front_matter_names_the_file(tmp_path: Path) -> None:
    write_runbook(tmp_path, "broken", front="title: x\ncautions:\n  - `bad`\n")
    with pytest.raises(ValueError, match=r"broken.md"):
        load_runbooks(tmp_path)


def test_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no runbooks"):
        load_runbooks(tmp_path)
