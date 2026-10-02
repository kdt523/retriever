from __future__ import annotations

from pathlib import Path

from runbook_retriever.build_corpus import build, corpus_stats, iter_k8s_docs, k8s_doc_id
from runbook_retriever.corpus import Chunk
from runbook_retriever.corpus_config import ChunkingConfig, CorpusConfig, K8sDocsConfig

PARA = " ".join(f"word{i}" for i in range(30))


class WordCounter:
    def count(self, text: str) -> int:
        return len(text.split())


def make_repo(root: Path) -> None:
    docs = root / "content/en/docs"
    (docs / "tasks/debug").mkdir(parents=True)
    (docs / "reference/kubectl/generated").mkdir(parents=True)
    (root / "content/en/examples/pods").mkdir(parents=True)
    (root / "content/en/examples/pods/p.yaml").write_text("kind: Pod\n", encoding="utf-8")
    (docs / "tasks/debug/_index.md").write_text("---\ntitle: Debug\n---\n" + PARA, encoding="utf-8")
    (docs / "tasks/debug/debug-pods.md").write_text(
        "---\ntitle: Debug Pods\n---\n<!-- overview -->\n"
        f"## My pod crashes\n\n{PARA}\n\n"
        '{{% code_sample file="pods/p.yaml" %}}\n\n'
        f"## What's next\n\n{PARA}\n",
        encoding="utf-8",
    )
    (docs / "reference/kubectl/generated/kubectl_get.md").write_text(PARA, encoding="utf-8")


def config(root: Path) -> CorpusConfig:
    return CorpusConfig(
        k8s_docs=K8sDocsConfig(
            repo="https://example.invalid/repo.git",
            commit="0" * 40,
            docs_root="content/en/docs",
            examples_root="content/en/examples",
            include=["tasks/debug", "reference/kubectl"],
            exclude=["reference/kubectl/generated/*"],
        ),
        chunking=ChunkingConfig(
            max_tokens=64, overlap_tokens=5, min_tokens=5, exclude_sections=["What's next"]
        ),
    )


def test_doc_ids() -> None:
    assert k8s_doc_id("tasks/debug/_index.md") == "k8s/tasks/debug"
    assert k8s_doc_id("tasks/debug/debug-pods.md") == "k8s/tasks/debug/debug-pods"


def test_build_end_to_end(tmp_path: Path) -> None:
    make_repo(tmp_path)
    cfg = config(tmp_path)
    docs = list(iter_k8s_docs(cfg.k8s_docs, tmp_path))
    assert [d.doc_id for d in docs] == ["k8s/tasks/debug", "k8s/tasks/debug/debug-pods"]
    assert docs[1].url == "https://kubernetes.io/docs/tasks/debug/debug-pods/"

    chunks, dropped = build(cfg, iter(docs), WordCounter(), tmp_path / "content/en/examples")
    pods = [c for c in chunks if c.doc_id == "k8s/tasks/debug/debug-pods"]
    assert [c.chunk_id for c in pods] == ["k8s/tasks/debug/debug-pods#000"]
    assert pods[0].section == "My pod crashes"
    assert "```yaml\nkind: Pod\n```" in pods[0].text
    assert "What's next" not in pods[0].passage
    assert pods[0].passage.startswith("Debug Pods > My pod crashes\n\n")
    # The _index page has the same paragraph text, so it is deduplicated.
    assert all(Chunk.model_validate(c.model_dump()) == c for c in chunks)
    stats = corpus_stats(chunks, dropped, cfg)
    assert stats["chunks"] == len(chunks)


def test_sparse_patterns_distinguish_files_and_dirs() -> None:
    from runbook_retriever.fetch_docs import sparse_patterns

    cfg = config(Path())
    k8s = cfg.k8s_docs.model_copy(update={"include": ["tasks/debug", "tasks/x/dns.md"]})
    assert sparse_patterns(k8s) == [
        "/content/en/docs/tasks/debug/",
        "/content/en/docs/tasks/x/dns.md",
        "/content/en/examples/",
    ]
