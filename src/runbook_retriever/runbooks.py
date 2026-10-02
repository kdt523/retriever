"""Load and validate the hand-written runbooks in ``runbooks/*.md``.

Format: YAML front matter (title, scope, tools, cautions, related) followed by a
short intro and exactly these H2 sections, in order. The front matter is metadata
for the consuming agent and is not embedded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from runbook_retriever.markdown_clean import split_front_matter

REQUIRED_SECTIONS = ("Symptoms", "Checks", "Likely causes", "Fix", "Rollback / escalation")
MIN_WORDS, MAX_WORDS = 150, 700

_H2 = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class RunbookMeta(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=3)
    scope: str = Field(min_length=10)
    tools: list[str] = Field(min_length=1)
    cautions: list[str] = Field(min_length=1)
    related: list[str] = []


@dataclass(frozen=True)
class Runbook:
    id: str
    path: Path
    meta: RunbookMeta
    body: str


def load_runbook(path: Path) -> Runbook:
    try:
        meta_raw, body = split_front_matter(path.read_text(encoding="utf-8"))
        meta = RunbookMeta.model_validate(meta_raw)
    except (ValidationError, yaml.YAMLError) as e:
        raise ValueError(f"{path.name}: bad front matter: {e}") from e
    return Runbook(id=path.stem, path=path, meta=meta, body=body.strip())


def runbook_errors(rb: Runbook) -> list[str]:
    errors: list[str] = []
    if not _SLUG.match(rb.id):
        errors.append(f"{rb.id}: file name must be a lowercase-hyphen slug")
    headings = tuple(_H2.findall(rb.body))
    if headings != REQUIRED_SECTIONS:
        errors.append(f"{rb.id}: H2 sections {headings} != {REQUIRED_SECTIONS}")
    if re.search(r"^#\s", rb.body, re.MULTILINE):
        errors.append(f"{rb.id}: no H1 in the body; the title comes from front matter")
    words = len(rb.body.split())
    if not MIN_WORDS <= words <= MAX_WORDS:
        errors.append(f"{rb.id}: {words} words, expected {MIN_WORDS}-{MAX_WORDS}")
    return errors


def load_runbooks(directory: Path) -> list[Runbook]:
    """Load every runbook, raising one error that lists every problem found."""
    runbooks = [load_runbook(p) for p in sorted(directory.glob("*.md"))]
    if not runbooks:
        raise ValueError(f"no runbooks in {directory}")
    ids = {rb.id for rb in runbooks}
    errors = [e for rb in runbooks for e in runbook_errors(rb)]
    errors += [
        f"{rb.id}: related runbook '{r}' does not exist"
        for rb in runbooks
        for r in rb.meta.related
        if r not in ids
    ]
    if errors:
        raise ValueError("invalid runbooks:\n  " + "\n  ".join(errors))
    return runbooks
