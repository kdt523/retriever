from __future__ import annotations

from runbook_retriever.bm25 import BM25Index, tokenize


def test_tokenize_keeps_compounds_and_parts() -> None:
    toks = tokenize('StorageClass "fast-ssd" not found on kubernetes.io/hostname, Exit Code: 137')
    assert "fast-ssd" in toks and "fast" in toks and "ssd" in toks
    assert "kubernetes.io/hostname" in toks and "hostname" in toks
    assert "137" in toks and "storageclass" in toks


def test_exact_identifier_ranks_first() -> None:
    docs = [
        "Pods restart in a loop: CrashLoopBackOff with exit code 1.",
        "The kubelet evicts pods when ephemeral storage exceeds the limit.",
        "ImagePullBackOff means the registry refused or did not find the image.",
    ]
    index = BM25Index(docs)
    assert index.top_k("ImagePullBackOff on deploy", 1) == [2]
    assert index.top_k("crashloopbackoff", 1) == [0]
