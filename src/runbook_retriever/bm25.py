"""BM25 keyword retrieval with an identifier-preserving tokenizer.

Kubernetes text is full of compound identifiers (``CrashLoopBackOff``, ``fast-ssd``,
``kubernetes.io/hostname``, ``nginx:1.27``). Each compound is indexed both whole and as
its parts, so an exact identifier matches strongly while partial mentions still match.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import numpy as np
from rank_bm25 import BM25Okapi

_COMPOUND = re.compile(r"[a-z0-9]+(?:[._:/-][a-z0-9]+)*")
_PART = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for compound in _COMPOUND.findall(text.lower()):
        parts = _PART.findall(compound)
        tokens.extend(parts)
        if len(parts) > 1:
            tokens.append(compound)
    return tokens


class BM25Index:
    def __init__(self, documents: Sequence[str]) -> None:
        self._bm25 = BM25Okapi([tokenize(d) for d in documents])

    def scores(self, query: str) -> np.ndarray:
        return np.asarray(self._bm25.get_scores(tokenize(query)), dtype=np.float32)

    def top_k(self, query: str, k: int) -> list[int]:
        s = self.scores(query)
        return [int(i) for i in np.argsort(-s, kind="stable")[:k]]
