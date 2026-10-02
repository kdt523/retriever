from __future__ import annotations

from itertools import pairwise

from runbook_retriever.chunking import (
    SPECIAL_TOKENS,
    chunk_document,
    merge_short_sections,
    section_label,
    split_blocks,
    split_oversized,
)
from runbook_retriever.config import format_passage
from runbook_retriever.corpus_config import ChunkingConfig
from runbook_retriever.markdown_clean import Section


class WordCounter:
    """1 token per whitespace-separated word: deterministic and offline."""

    def count(self, text: str) -> int:
        return len(text.split())


COUNTER = WordCounter()


def cfg(max_tokens: int = 40, overlap: int = 6, min_tokens: int = 5) -> ChunkingConfig:
    return ChunkingConfig(max_tokens=max_tokens, overlap_tokens=overlap, min_tokens=min_tokens)


def words(n: int, tag: str) -> str:
    return " ".join(f"{tag}{i}" for i in range(n))


def test_section_label_drops_title_and_keeps_last_two() -> None:
    assert section_label(("Debug Pods", "A", "B", "C"), "Debug Pods") == "B > C"
    assert section_label((), "T") == ""


def test_split_blocks_keeps_fences_whole() -> None:
    body = "p1 line\n\n```\na\n\nb\n```\n\np2"
    assert split_blocks(body) == ["p1 line", "```\na\n\nb\n```", "p2"]


def test_split_oversized_code_rewraps_fences() -> None:
    block = "```yaml\n" + "\n".join(f"k{i}: v" for i in range(30)) + "\n```"
    pieces = split_oversized(block, lambda s: COUNTER.count(s) <= 12)
    assert len(pieces) > 1
    for p in pieces:
        assert p.startswith("```yaml\n") and p.endswith("\n```")
        assert COUNTER.count(p) <= 12


def test_every_chunk_fits_the_cap() -> None:
    sections = [
        Section(("A",), "\n\n".join(words(9, f"a{j}_") for j in range(12))),
        Section(("B",), words(150, "b")),  # one giant paragraph
    ]
    c = cfg()
    chunks = chunk_document("Title", sections, COUNTER, c)
    assert len(chunks) > 4
    for ch in chunks:
        full = COUNTER.count(format_passage("Title", ch.section, ch.text)) + SPECIAL_TOKENS
        assert full == ch.n_tokens <= c.max_tokens
    # Nothing lost: every source word appears in some chunk.
    joined = " ".join(ch.text for ch in chunks)
    assert all(f"b{i}" in joined.split() for i in range(150))


def test_overlap_between_consecutive_chunks() -> None:
    paras = [words(5, f"p{j}_") for j in range(20)]
    chunks = chunk_document("T", [Section(("S",), "\n\n".join(paras))], COUNTER, cfg(overlap=6))
    assert len(chunks) >= 3
    for prev, nxt in pairwise(chunks):
        assert nxt.text.split("\n\n")[0] == prev.text.split("\n\n")[-1]


def test_no_overlap_when_disabled() -> None:
    paras = [words(5, f"p{j}_") for j in range(20)]
    chunks = chunk_document("T", [Section(("S",), "\n\n".join(paras))], COUNTER, cfg(overlap=0))
    seen = [p for ch in chunks for p in ch.text.split("\n\n")]
    assert seen == paras


def test_short_sections_merge_forward_with_heading() -> None:
    secs = [Section(("Tiny",), "two words"), Section(("Big",), words(10, "w"))]
    merged = merge_short_sections(secs, COUNTER, min_tokens=5, title="T")
    assert len(merged) == 1
    assert merged[0].path == ("Big",)
    assert merged[0].body.startswith("Tiny:\ntwo words\n\n")


def test_trailing_short_section_appends_backward() -> None:
    secs = [Section(("Big",), words(10, "w")), Section(("End",), "tail bit")]
    merged = merge_short_sections(secs, COUNTER, min_tokens=5, title="T")
    assert len(merged) == 1 and merged[0].body.endswith("End:\ntail bit")


def test_lone_short_doc_is_dropped() -> None:
    assert chunk_document("T", [Section((), "too short")], COUNTER, cfg()) == []
