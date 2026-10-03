from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from runbook_retriever.config import REPO_ROOT
from runbook_retriever.embed import model_fingerprint
from runbook_retriever.train import load_train_config, load_triplets, metric_key, summarize


def _write(path: Path, rows: list[dict[str, str]]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def test_repo_train_config_is_valid() -> None:
    cfg = load_train_config(REPO_ROOT / "configs" / "train.yaml")
    assert cfg.base_model == "BAAI/bge-small-en-v1.5"
    assert cfg.batch_size % cfg.mini_batch_size == 0


def test_load_triplets_keeps_column_order(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "t.jsonl", [{"anchor": "q", "positive": "p", "negative": "n", "x": "1"}]
    )
    assert list(load_triplets(path, hard_negatives=True)) == ["anchor", "positive", "negative"]
    assert load_triplets(path, hard_negatives=False) == {"anchor": ["q"], "positive": ["p"]}


def test_load_triplets_rejects_empty_file(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        load_triplets(_write(tmp_path / "t.jsonl", []), hard_negatives=True)


def test_summarize_maps_evaluator_and_trainer_keys() -> None:
    raw = {
        "val_cosine_accuracy@1": 0.5,
        "val_cosine_accuracy@10": 0.9,
        "val_cosine_ndcg@10": 0.7,
        "val_cosine_mrr@10": 0.6,
        "val_dot_ndcg@10": 0.1,
    }
    assert summarize(raw) == {"hit@1": 0.5, "hit@10": 0.9, "mrr@10": 0.6, "ndcg@10": 0.7}
    trainer = {f"eval_{k}": v for k, v in raw.items()}
    assert summarize(trainer)["ndcg@10"] == 0.7
    assert metric_key("ndcg@10") == "val_cosine_ndcg@10"


def test_model_fingerprint_changes_when_local_model_changes(tmp_path: Path) -> None:
    assert model_fingerprint("BAAI/bge-small-en-v1.5") == "BAAI/bge-small-en-v1.5"
    weights = tmp_path / "model.safetensors"
    weights.write_bytes(b"a")
    before = model_fingerprint(str(tmp_path))
    weights.write_bytes(b"bb")
    os.utime(weights, ns=(1, 1))
    assert model_fingerprint(str(tmp_path)) != before
