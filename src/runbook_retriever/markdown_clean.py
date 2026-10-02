"""Turn Hugo-flavoured Kubernetes docs Markdown into clean text sections.

Pipeline: front matter -> Hugo shortcodes -> prose cleanup (outside code fences)
-> split on headings. Code blocks and kubectl output are kept verbatim because
error-string queries match against them.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import yaml

# --- Front matter --------------------------------------------------------------------

_FRONT_MATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    match = _FRONT_MATTER.match(text)
    if not match:
        return {}, text
    meta = yaml.safe_load(match.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError("front matter is not a mapping")
    return meta, text[match.end() :]


# --- Hugo shortcodes -----------------------------------------------------------------

_O, _C = r"\{\{[<%]\s*", r"\s*[>%]\}\}"  # shortcode open/close delimiters

_DROP_WITH_BODY = re.compile(
    _O + r"(comment|mermaid)\b[^}]*?" + _C + r".*?" + _O + r"/\1" + _C, re.DOTALL
)
_CODE_SAMPLE = re.compile(
    _O + r"(?:code_sample|codenew|code)\b[^}]*?\bfile=\"([^\"]+)\"[^}]*?" + _C
)
_HIGHLIGHT_OPEN = re.compile(_O + r"highlight\s+([\w-]+)[^}]*?" + _C)
_HIGHLIGHT_CLOSE = re.compile(_O + r"/highlight" + _C)
_HEADING = re.compile(_O + r"heading\s+\"(\w+)\"" + _C)
_CALLOUT_OPEN = re.compile(_O + r"(note|caution|warning)\b[^}]*?" + _C)
_TEXT_ATTR = re.compile(_O + r"(?:glossary_tooltip|link)\b[^}]*?\btext=\"([^\"]*)\"[^}]*?" + _C)
_ANY_SHORTCODE = re.compile(_O + r".*?" + _C, re.DOTALL)

_HEADING_NAMES = {
    "prerequisites": "Before you begin",
    "whatsnext": "What's next",
    "objectives": "Objectives",
    "cleanup": "Clean up",
    "synopsis": "Synopsis",
    "options": "Options",
    "seealso": "See also",
}

_LANG_BY_EXT = {".yaml": "yaml", ".yml": "yaml", ".json": "json", ".sh": "shell", ".conf": ""}

ExampleLoader = Callable[[str], str | None]


def _inline_example(file: str, load: ExampleLoader) -> str:
    content = load(file)
    if content is None:
        return ""
    lang = _LANG_BY_EXT.get(PurePosixPath(file).suffix, "")
    return f"\n```{lang}\n{content.strip()}\n```\n"


def strip_shortcodes(text: str, load_example: ExampleLoader) -> str:
    text = _DROP_WITH_BODY.sub("", text)
    text = _CODE_SAMPLE.sub(lambda m: _inline_example(m.group(1), load_example), text)
    text = _HIGHLIGHT_OPEN.sub(lambda m: f"```{m.group(1)}", text)
    text = _HIGHLIGHT_CLOSE.sub("```", text)
    text = _HEADING.sub(lambda m: _HEADING_NAMES.get(m.group(1), m.group(1).capitalize()), text)
    text = _CALLOUT_OPEN.sub(lambda m: f"{m.group(1).capitalize()}: ", text)
    text = _TEXT_ATTR.sub(lambda m: m.group(1), text)
    return _ANY_SHORTCODE.sub("", text)


# --- Prose cleanup (never applied inside code fences) --------------------------------

_FENCE = re.compile(r"^\s*(```|~~~)")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_IMAGE = re.compile(r"!\[[^\]]*\]\((?:[^()]|\([^)]*\))*\)")
_LINK = re.compile(r"\[([^\]]+)\]\((?:[^()]|\([^)]*\))*\)")
_REF_LINK = re.compile(r"\[([^\]]+)\]\[[^\]]*\]")
_LINK_DEF = re.compile(r"^\s*\[[^\]]+\]:\s*\S+.*$", re.MULTILINE)
_HEADING_ANCHOR = re.compile(r"\s*\{#[\w.:-]+\}")
_HTML_TAG = re.compile(
    r"</?(?:a|br|div|span|p|sup|sub|b|i|em|strong|code|table|thead|tbody|tr|td|th|img|"
    r"details|summary|ul|ol|li|pre|nav|section|h[1-6])\b[^>]*>",
    re.IGNORECASE,
)
_INNER_SPACES = re.compile(r"(?<=\S)[ \t]{2,}(?=\S)")


def _clean_prose(text: str) -> str:
    text = _HTML_COMMENT.sub("", text)
    text = _IMAGE.sub("", text)
    text = _LINK.sub(r"\1", text)
    text = _REF_LINK.sub(r"\1", text)
    text = _LINK_DEF.sub("", text)
    text = _HEADING_ANCHOR.sub("", text)
    text = _HTML_TAG.sub("", text)
    text = _INNER_SPACES.sub(" ", text)  # gaps left by removed shortcodes; keeps indentation
    return html.unescape(text)


def map_outside_fences(text: str, fn: Callable[[str], str]) -> str:
    """Apply ``fn`` to every run of lines outside fenced code blocks."""
    out: list[str] = []
    prose: list[str] = []
    in_fence = False
    for line in text.split("\n"):
        if _FENCE.match(line):
            if not in_fence:
                out.append(fn("\n".join(prose)))
                prose = []
            in_fence = not in_fence
            out.append(line)
        elif in_fence:
            out.append(line)
        else:
            prose.append(line)
    out.append(fn("\n".join(prose)))
    return "\n".join(out)


def normalize_whitespace(text: str) -> str:
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def clean_markdown(text: str, load_example: ExampleLoader) -> str:
    text = strip_shortcodes(text, load_example)
    return normalize_whitespace(map_outside_fences(text, _clean_prose))


# --- Sections ------------------------------------------------------------------------

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


@dataclass(frozen=True)
class Section:
    path: tuple[str, ...]  # heading trail, outermost first; () = text before any heading
    body: str


def split_sections(text: str) -> list[Section]:
    """Split on ATX headings outside code fences. Empty bodies are dropped."""
    sections: list[Section] = []
    stack: list[tuple[int, str]] = []
    lines: list[str] = []
    in_fence = False

    def flush() -> None:
        body = normalize_whitespace("\n".join(lines))
        if body:
            sections.append(Section(tuple(h for _, h in stack), body))
        lines.clear()

    for line in text.split("\n"):
        if _FENCE.match(line):
            in_fence = not in_fence
        heading = None if in_fence else _MD_HEADING.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, heading.group(2).strip()))
        else:
            lines.append(line)
    flush()
    return sections


def drop_sections(sections: list[Section], excluded: list[str]) -> list[Section]:
    """Remove sections whose heading trail contains an excluded heading (case-insensitive)."""
    banned = {h.casefold() for h in excluded}
    return [s for s in sections if not any(h.casefold() in banned for h in s.path)]
