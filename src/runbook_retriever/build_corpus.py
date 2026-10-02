"""Phase 1: build ``data/corpus.jsonl`` from the pinned k8s docs and ``runbooks/``.

Run ``make corpus`` (fetches the docs first). Writes the corpus plus
``results/corpus_stats.json`` and logs the run to ``results/runs.csv``.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import logging
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from runbook_retriever.chunking import HFTokenCounter, TokenCounter, chunk_document
from runbook_retriever.config import MAX_SEQ_LENGTH, get_settings
from runbook_retriever.corpus import Chunk
from runbook_retriever.corpus_config import CorpusConfig, K8sDocsConfig, load_corpus_config
from runbook_retriever.io import sha256_file, write_jsonl, write_text_atomic
from runbook_retriever.logging_setup import setup_logging
from runbook_retriever.markdown_clean import (
    clean_markdown,
    drop_sections,
    split_front_matter,
    split_sections,
)
from runbook_retriever.runbooks import load_runbooks
from runbook_retriever.runlog import RunTracker
from runbook_retriever.seed import set_seed

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceDoc:
    doc_id: str
    source: str
    source_path: str
    url: str | None
    title: str
    markdown: str  # body without front matter
    meta: dict[str, object]


def k8s_doc_id(rel: str) -> str:
    """``tasks/debug/_index.md`` -> ``k8s/tasks/debug``; ``a/b.md`` -> ``k8s/a/b``."""
    stem = rel.removesuffix(".md")
    stem = stem.removesuffix("/_index").removesuffix("_index")
    return f"k8s/{stem.rstrip('/')}"


def iter_k8s_docs(cfg: K8sDocsConfig, repo: Path) -> Iterator[SourceDoc]:
    docs_root = repo / cfg.docs_root
    if not docs_root.is_dir():
        raise FileNotFoundError(f"{docs_root} missing; run `make fetch` first")
    files: set[Path] = set()
    for inc in cfg.include:
        target = docs_root / inc
        if target.is_file():
            files.add(target)
        elif target.is_dir():
            files.update(target.rglob("*.md"))
        else:
            raise FileNotFoundError(f"include entry not found: {inc}")
    for path in sorted(files):
        rel = path.relative_to(docs_root).as_posix()
        if any(fnmatch.fnmatch(rel, pat) for pat in cfg.exclude):
            continue
        meta, body = split_front_matter(path.read_text(encoding="utf-8"))
        doc_id = k8s_doc_id(rel)
        yield SourceDoc(
            doc_id=doc_id,
            source="k8s_docs",
            source_path=f"{cfg.docs_root}/{rel}",
            url=f"https://kubernetes.io/docs/{doc_id.removeprefix('k8s/')}/",
            title=str(meta.get("title") or path.stem.replace("-", " ").title()).strip(),
            markdown=body,
            meta={},
        )


def iter_runbooks(directory: Path, root: Path) -> Iterator[SourceDoc]:
    for rb in load_runbooks(directory):
        meta = rb.meta.model_dump()
        title = meta.pop("title")
        yield SourceDoc(
            doc_id=f"runbook/{rb.id}",
            source="runbook",
            source_path=rb.path.relative_to(root).as_posix(),
            url=None,
            title=title,
            markdown=rb.body,
            meta=meta,
        )


def build(
    cfg: CorpusConfig, docs: Iterator[SourceDoc], counter: TokenCounter, examples_dir: Path
) -> tuple[list[Chunk], dict[str, int]]:
    def load_example(file: str) -> str | None:
        path = examples_dir / file
        return path.read_text(encoding="utf-8") if path.is_file() else None

    chunks: list[Chunk] = []
    seen_text: set[str] = set()
    dropped: Counter[str] = Counter()
    for doc in docs:
        text = clean_markdown(doc.markdown, load_example)
        sections = drop_sections(split_sections(text), cfg.chunking.exclude_sections)
        pieces = chunk_document(doc.title, sections, counter, cfg.chunking)
        if not pieces:
            dropped["empty_docs"] += 1
            continue
        kept = 0
        for piece in pieces:
            if piece.text in seen_text:
                dropped["duplicate_chunks"] += 1
                continue
            seen_text.add(piece.text)
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.doc_id}#{kept:03d}",
                    doc_id=doc.doc_id,
                    source=doc.source,  # type: ignore[arg-type]
                    source_path=doc.source_path,
                    url=doc.url,
                    title=doc.title,
                    section=piece.section,
                    text=piece.text,
                    n_tokens=piece.n_tokens,
                    meta=doc.meta,
                )
            )
            kept += 1
    return chunks, dict(dropped)


def corpus_stats(
    chunks: list[Chunk], dropped: dict[str, int], cfg: CorpusConfig
) -> dict[str, object]:
    tokens = np.array([c.n_tokens for c in chunks])
    by_source: dict[str, dict[str, int]] = {}
    for src in sorted({c.source for c in chunks}):
        sub = [c for c in chunks if c.source == src]
        by_source[src] = {"docs": len({c.doc_id for c in sub}), "chunks": len(sub)}
    return {
        "k8s_commit": cfg.k8s_docs.commit,
        "max_tokens": cfg.chunking.max_tokens,
        "docs": len({c.doc_id for c in chunks}),
        "chunks": len(chunks),
        "by_source": by_source,
        "tokens": {
            "min": int(tokens.min()),
            "p50": int(np.percentile(tokens, 50)),
            "p90": int(np.percentile(tokens, 90)),
            "max": int(tokens.max()),
        },
        "dropped": dropped,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)
    setup_logging()
    settings = get_settings()
    paths = settings.paths
    config_path = args.config or paths.configs / "corpus.yaml"
    cfg = load_corpus_config(config_path)
    set_seed(settings.seed)

    with RunTracker(
        phase="1",
        name="build_corpus",
        config=cfg.model_dump(),
        seed=settings.seed,
        runs_csv=paths.runs_csv,
    ) as run:
        repo = paths.raw / "k8s-website"
        docs = (
            *iter_k8s_docs(cfg.k8s_docs, repo),
            *iter_runbooks(paths.runbooks, settings.root),
        )
        chunks, dropped = build(
            cfg, iter(docs), HFTokenCounter(), repo / cfg.k8s_docs.examples_root
        )
        over = [c.chunk_id for c in chunks if c.n_tokens > MAX_SEQ_LENGTH]
        if over:
            raise AssertionError(f"chunks over {MAX_SEQ_LENGTH} tokens: {over[:5]}")
        write_jsonl(paths.corpus, (c.model_dump() for c in chunks))
        stats = corpus_stats(chunks, dropped, cfg)
        stats["corpus_sha256"] = sha256_file(paths.corpus)
        write_text_atomic(paths.results / "corpus_stats.json", json.dumps(stats, indent=2) + "\n")
        run.metrics = {k: stats[k] for k in ("docs", "chunks", "by_source", "tokens", "dropped")}
    log.info("wrote %d chunks from %d docs to %s", stats["chunks"], stats["docs"], paths.corpus)
    log.info("stats: %s", json.dumps(stats["by_source"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
