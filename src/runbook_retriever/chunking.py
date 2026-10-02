"""Pack document sections into token-capped chunks.

Guarantees for every chunk produced:
- ``count(format_passage(title, section, text)) + 2 <= max_tokens`` (2 = [CLS]/[SEP]),
  so nothing is truncated at encode time;
- paragraphs and code blocks are only split when one alone exceeds the cap, and a
  split code block is re-wrapped in its fence;
- consecutive chunks of one section share up to ``overlap_tokens`` of trailing text.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from runbook_retriever.config import BASE_MODEL, format_passage
from runbook_retriever.corpus_config import ChunkingConfig
from runbook_retriever.markdown_clean import Section

SPECIAL_TOKENS = 2  # [CLS] + [SEP]
SECTION_DEPTH = 2  # how many trailing headings form the chunk's section label

_FENCE_LINE = re.compile(r"^\s*(```|~~~)")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z`\"'(])")


class TokenCounter(Protocol):
    def count(self, text: str) -> int:
        """Number of model tokens in ``text``, excluding special tokens."""
        ...


class HFTokenCounter:
    """Counts tokens with the base model's own tokenizer."""

    def __init__(self, model_name: str = BASE_MODEL) -> None:
        from transformers import AutoTokenizer

        self._tok = AutoTokenizer.from_pretrained(model_name)
        self._tok.model_max_length = 10**9  # silence ">512 tokens" warnings while measuring
        self.count = lru_cache(maxsize=200_000)(self._count)  # type: ignore[method-assign]

    def _count(self, text: str) -> int:
        return len(self._tok(text, add_special_tokens=False)["input_ids"])

    def count(self, text: str) -> int:  # replaced by the cached version in __init__
        return self._count(text)


@dataclass(frozen=True)
class ChunkText:
    section: str
    text: str
    n_tokens: int  # full passage incl. special tokens


def section_label(path: tuple[str, ...], title: str) -> str:
    headings = [h for h in path if h.casefold() != title.casefold()]
    return " > ".join(headings[-SECTION_DEPTH:])


def split_blocks(body: str) -> list[str]:
    """Paragraphs separated by blank lines; a fenced code block is always one block."""
    blocks: list[str] = []
    cur: list[str] = []
    in_fence = False
    for line in body.split("\n"):
        if _FENCE_LINE.match(line):
            in_fence = not in_fence
        if not line.strip() and not in_fence:
            if cur:
                blocks.append("\n".join(cur))
                cur = []
        else:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    return blocks


def _is_fenced(block: str) -> bool:
    lines = block.split("\n")
    return (
        len(lines) >= 2 and bool(_FENCE_LINE.match(lines[0])) and bool(_FENCE_LINE.match(lines[-1]))
    )


def _greedy(units: list[str], joiner: str, fits: Callable[[str], bool]) -> list[str]:
    """Group ``units`` into the fewest consecutive runs that each ``fits``.

    A single unit that never fits is cut word by word.
    """
    out: list[str] = []
    cur: list[str] = []
    for unit in units:
        if fits(joiner.join([*cur, unit])):
            cur.append(unit)
            continue
        if cur:
            out.append(joiner.join(cur))
            cur = []
        if fits(unit):
            cur = [unit]
        else:
            words = unit.split(" ")
            if len(words) == 1:  # one unsplittable token run: hard-cut by characters
                out.extend(_hard_cut(unit, fits))
            else:
                out.extend(_greedy(words, " ", fits))
    if cur:
        out.append(joiner.join(cur))
    return out


def _hard_cut(text: str, fits: Callable[[str], bool]) -> list[str]:
    out: list[str] = []
    while text:
        lo, hi = 1, len(text)
        while lo < hi:  # longest prefix that fits
            mid = (lo + hi + 1) // 2
            if fits(text[:mid]):
                lo = mid
            else:
                hi = mid - 1
        out.append(text[:lo])
        text = text[lo:]
    return out


def split_oversized(block: str, fits: Callable[[str], bool]) -> list[str]:
    if fits(block):
        return [block]
    if _is_fenced(block):
        lines = block.split("\n")
        opener, closer, inner = lines[0], lines[-1], lines[1:-1]
        wrapped_fits: Callable[[str], bool] = lambda s: fits(f"{opener}\n{s}\n{closer}")  # noqa: E731
        return [f"{opener}\n{g}\n{closer}" for g in _greedy(inner, "\n", wrapped_fits)]
    if "\n" in block:
        return _greedy(block.split("\n"), "\n", fits)
    return _greedy(_SENTENCE_END.split(block), " ", fits)


def _overlap_seed(blocks: list[str], counter: TokenCounter, budget: int) -> list[str]:
    """Trailing whole blocks (or, failing that, trailing sentences) within ``budget``."""
    if budget <= 0 or not blocks:
        return []
    seed: list[str] = []
    for block in reversed(blocks):
        if counter.count("\n\n".join([block, *seed])) > budget:
            break
        seed.insert(0, block)
    if seed:
        return seed
    last = blocks[-1]
    if _is_fenced(last):
        return []
    sentences = _SENTENCE_END.split(last)
    tail: list[str] = []
    for sentence in reversed(sentences[1:]):  # never repeat the whole block
        if counter.count(" ".join([sentence, *tail])) > budget:
            break
        tail.insert(0, sentence)
    return [" ".join(tail)] if tail else []


def merge_short_sections(
    sections: list[Section], counter: TokenCounter, min_tokens: int, title: str
) -> list[Section]:
    """Fold sections with fewer than ``min_tokens`` body tokens into the next section.

    A trailing short section is appended to the previous one instead. The folded text
    keeps its heading as a lead-in line so no context is lost.
    """
    out: list[Section] = []
    carry = ""
    for sec in sections:
        body = f"{carry}\n\n{sec.body}" if carry else sec.body
        carry = ""
        if counter.count(body) < min_tokens:
            label = section_label(sec.path, title)
            carry = f"{label.split(' > ')[-1]}:\n{body}" if label else body
            continue
        out.append(Section(sec.path, body))
    if carry:
        if out:
            out[-1] = Section(out[-1].path, f"{out[-1].body}\n\n{carry}")
        elif counter.count(carry) >= min_tokens:
            out.append(Section((), carry))
    return out


def chunk_document(
    title: str, sections: list[Section], counter: TokenCounter, cfg: ChunkingConfig
) -> list[ChunkText]:
    chunks: list[ChunkText] = []
    for sec in merge_short_sections(sections, counter, cfg.min_tokens, title):
        label = section_label(sec.path, title)

        def n_tokens(body: str, label: str = label) -> int:
            return counter.count(format_passage(title, label, body)) + SPECIAL_TOKENS

        def fits(body: str) -> bool:
            return n_tokens(body) <= cfg.max_tokens

        blocks = [piece for b in split_blocks(sec.body) for piece in split_oversized(b, fits)]
        cur: list[str] = []
        fresh = False  # does `cur` hold anything not already emitted?
        for block in blocks:
            if fits("\n\n".join([*cur, block])):
                cur.append(block)
                fresh = True
                continue
            if cur and fresh:
                body = "\n\n".join(cur)
                chunks.append(ChunkText(label, body, n_tokens(body)))
            seed = _overlap_seed(cur, counter, cfg.overlap_tokens)
            cur = [*seed, block] if fits("\n\n".join([*seed, block])) else [block]
            fresh = True
        if cur and fresh:
            body = "\n\n".join(cur)
            chunks.append(ChunkText(label, body, n_tokens(body)))
    return chunks
