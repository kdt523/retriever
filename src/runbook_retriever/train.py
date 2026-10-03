"""Phase 4: fine-tune bge-small on (query, positive, hard negative) triplets.

Loss is CachedMultipleNegativesRankingLoss: every other positive and hard negative in the batch
is a negative for each query, and the gradient cache lets a 64-pair batch fit in 4 GB of VRAM.
The model is scored on the frozen val set (whole corpus, same QUERY_PREFIX as eval and serving)
before training and every ``eval_steps``; the best checkpoint by val NDCG@10 is kept.
The test set is never touched here.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from runbook_retriever.config import MAX_SEQ_LENGTH, QUERY_PREFIX, Paths, get_settings
from runbook_retriever.corpus import Chunk, load_corpus
from runbook_retriever.evaluate import load_eval_set
from runbook_retriever.io import read_jsonl, sha256_file
from runbook_retriever.logging_setup import setup_logging
from runbook_retriever.runlog import RunTracker, git_sha
from runbook_retriever.seed import set_seed

log = logging.getLogger(__name__)

EVAL_NAME = "val"


class TrainConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    base_model: str
    train_file: str
    output_dir: str
    batch_size: int = Field(gt=1)
    mini_batch_size: int = Field(gt=0)
    use_hard_negatives: bool = True
    learning_rate: float = Field(gt=0)
    warmup_ratio: float = Field(ge=0, lt=1)
    epochs: float = Field(gt=0)
    weight_decay: float = Field(ge=0)
    eval_steps: int = Field(gt=0)
    metric_for_best: str = "ndcg@10"
    fp16: bool = True


def load_train_config(path: Path) -> TrainConfig:
    return TrainConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_triplets(path: Path, *, hard_negatives: bool) -> dict[str, list[str]]:
    """Columns for the trainer: anchor/positive(/negative). Order matters to the loss."""
    columns: dict[str, list[str]] = {"anchor": [], "positive": []}
    if hard_negatives:
        columns["negative"] = []
    for row in read_jsonl(path):
        columns["anchor"].append(row["anchor"])
        columns["positive"].append(row["positive"])
        if hard_negatives:
            columns["negative"].append(row["negative"])
    if not columns["anchor"]:
        raise SystemExit(f"no training rows in {path}")
    return columns


def val_ir_data(
    paths: Paths, corpus: list[Chunk]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, set[str]]]:
    """Queries, whole-corpus passages and qrels for the val InformationRetrievalEvaluator."""
    val = load_eval_set("val", paths, corpus)
    queries = {q["qid"]: q["query"] for q in val.queries}
    passages = {c.chunk_id: c.passage for c in corpus}
    return queries, passages, val.relevant


def metric_key(metric: str) -> str:
    """Name the evaluator gives ``metric`` (cosine scores), e.g. ``val_cosine_ndcg@10``."""
    return f"{EVAL_NAME}_cosine_{metric}"


def summarize(scores: dict[str, Any]) -> dict[str, float]:
    """Keep the evaluator's headline metrics under short names."""
    wanted = ("accuracy@1", "accuracy@5", "accuracy@10", "mrr@10", "ndcg@10")
    out: dict[str, float] = {}
    for name in wanted:
        for key, value in scores.items():
            if key.endswith(metric_key(name)):
                out[name.replace("accuracy", "hit")] = round(float(value), 4)
    return out


def train(
    cfg: TrainConfig, paths: Paths, seed: int, max_steps: int | None = None
) -> dict[str, Any]:
    import torch
    from datasets import Dataset
    from sentence_transformers import (
        SentenceTransformer,
        SentenceTransformerTrainer,
        SentenceTransformerTrainingArguments,
    )
    from sentence_transformers.sentence_transformer.evaluation import (
        InformationRetrievalEvaluator,
    )
    from sentence_transformers.sentence_transformer.losses import (
        CachedMultipleNegativesRankingLoss,
    )
    from sentence_transformers.sentence_transformer.training_args import BatchSamplers

    set_seed(seed)
    cuda = torch.cuda.is_available()
    train_path = paths.root / cfg.train_file
    out_dir = paths.root / cfg.output_dir
    ckpt_dir = out_dir.parent / "checkpoints" / out_dir.name

    data = Dataset.from_dict(load_triplets(train_path, hard_negatives=cfg.use_hard_negatives))
    corpus = load_corpus(paths.corpus)
    queries, passages, relevant = val_ir_data(paths, corpus)
    log.info(
        "train rows %d (%s), val queries %d over %d chunks, device %s",
        len(data),
        ", ".join(data.column_names),
        len(queries),
        len(passages),
        "cuda" if cuda else "cpu",
    )

    model = SentenceTransformer(cfg.base_model, device="cuda" if cuda else "cpu")
    model.max_seq_length = MAX_SEQ_LENGTH
    evaluator = InformationRetrievalEvaluator(
        queries=queries,
        corpus=passages,
        relevant_docs=relevant,
        name=EVAL_NAME,
        query_prompt=QUERY_PREFIX,
        batch_size=64,
        write_csv=False,
    )
    before = summarize(evaluator(model))
    log.info("val before training: %s", before)

    loss = CachedMultipleNegativesRankingLoss(model, mini_batch_size=cfg.mini_batch_size)
    args = SentenceTransformerTrainingArguments(
        output_dir=str(ckpt_dir),
        num_train_epochs=cfg.epochs,
        max_steps=max_steps if max_steps is not None else -1,
        per_device_train_batch_size=cfg.batch_size,
        learning_rate=cfg.learning_rate,
        warmup_ratio=cfg.warmup_ratio,
        weight_decay=cfg.weight_decay,
        fp16=cfg.fp16 and cuda,
        batch_sampler=BatchSamplers.NO_DUPLICATES,
        # BGE instruction on queries only; passages are embedded as-is (same as eval/serve).
        prompts={"anchor": QUERY_PREFIX},
        eval_strategy="steps",
        eval_steps=cfg.eval_steps,
        save_strategy="steps",
        save_steps=cfg.eval_steps,
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model=f"eval_{metric_key(cfg.metric_for_best)}",
        greater_is_better=True,
        logging_steps=10,
        seed=seed,
        data_seed=seed,
        report_to="none",
        dataloader_drop_last=False,
    )
    trainer = SentenceTransformerTrainer(
        model=model, args=args, train_dataset=data, loss=loss, evaluator=evaluator
    )
    trainer.train()

    after = summarize(evaluator(model))
    history = [
        {"step": h["step"], **summarize(h)}
        for h in trainer.state.log_history
        if any(k.endswith(metric_key("ndcg@10")) for k in h)
    ]
    best_step = max(history, key=lambda h: h["ndcg@10"])["step"] if history else None
    log.info("val after training (best checkpoint, step %s): %s", best_step, after)

    out_dir.mkdir(parents=True, exist_ok=True)
    model.save(str(out_dir))
    meta = {
        "base_model": cfg.base_model,
        "config": cfg.model_dump(),
        "seed": seed,
        "git_sha": git_sha(),
        "train_file_sha256": sha256_file(train_path),
        "train_rows": len(data),
        "steps": trainer.state.global_step,
        "best_step": best_step,
        "query_prefix": QUERY_PREFIX,
        "max_seq_length": MAX_SEQ_LENGTH,
        "val_before": before,
        "val_after": after,
        "val_history": history,
    }
    (out_dir / "train_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    shutil.rmtree(ckpt_dir, ignore_errors=True)  # the best checkpoint is now in out_dir
    log.info("saved %s", out_dir)
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None, help="default configs/train.yaml")
    parser.add_argument("--seed", type=int, default=None, help="default RR_SEED (42)")
    parser.add_argument("--output-dir", help="override output_dir (e.g. for extra seeds)")
    parser.add_argument("--max-steps", type=int, help="stop early (smoke test)")
    args = parser.parse_args(argv)
    setup_logging()
    settings = get_settings()
    paths = settings.paths
    cfg = load_train_config(args.config or paths.configs / "train.yaml")
    if args.output_dir:
        cfg = cfg.model_copy(update={"output_dir": args.output_dir})
    seed = settings.seed if args.seed is None else args.seed

    with RunTracker(
        phase="4", name="train", config=cfg.model_dump(), seed=seed, runs_csv=paths.runs_csv
    ) as run:
        meta = train(cfg, paths, seed, max_steps=args.max_steps)
        run.metrics = {
            "val_before": meta["val_before"],
            "val_after": meta["val_after"],
            "best_step": meta["best_step"],
            "steps": meta["steps"],
        }
        if args.max_steps is not None:
            run.notes = f"smoke test: max_steps={args.max_steps}"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
