from __future__ import annotations

from pathlib import Path

from runbook_retriever.labeling import LabelStore, first_unlabeled, rate, summarize


def test_store_is_append_only_and_latest_wins(tmp_path: Path) -> None:
    path = tmp_path / "labels" / "test_pairs.jsonl"
    store = LabelStore(path)
    store.put("a", {"verdict": "wrong"})
    store.put("a", {"verdict": "correct", "also_relevant": ["k8s/x#001"]})
    store.put("b", {"verdict": "ambiguous"})
    assert len(path.read_text(encoding="utf-8").splitlines()) == 3  # history kept
    reloaded = LabelStore(path)
    assert reloaded.get("a")["verdict"] == "correct"  # type: ignore[index]
    assert reloaded.get("a")["also_relevant"] == ["k8s/x#001"]  # type: ignore[index]
    assert reloaded.labeled_ids() == {"a", "b"}


def test_first_unlabeled_and_summary(tmp_path: Path) -> None:
    queue = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    store = LabelStore(tmp_path / "l.jsonl")
    store.put("a", {"verdict": "correct"})
    store.put("zzz", {"verdict": "wrong"})  # label for an item no longer queued is ignored
    assert first_unlabeled(queue, store.labeled_ids()) == 1
    s = summarize(queue, store.all())
    assert (s.total, s.labeled, s.counts, s.done) == (3, 1, {"correct": 1}, False)
    assert rate(s, "correct") == 1.0 and rate(s, "wrong") == 0.0


def test_so_labels_count_mapped_and_no_match(tmp_path: Path) -> None:
    queue = [{"id": "a"}, {"id": "b"}]
    store = LabelStore(tmp_path / "so.jsonl")
    store.put("a", {"relevant": ["k8s/x#000"]})
    store.put("b", {"relevant": []})
    assert summarize(queue, store.all()).counts == {"mapped": 1, "no_match": 1}
    assert first_unlabeled(queue, store.labeled_ids()) == 2
