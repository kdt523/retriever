"""Claude-assisted labeling of the review queues, with a blind human spot check.

  export      write self-contained batch files (instructions + items) to
              ``data/llm_labeling/batches/``; paste each into a fresh Claude chat
  import      read Claude's replies saved anywhere under ``data/llm_labeling/answers/``,
              validate every line and store them as labels with ``labeler: "claude"``
  spot-check  sample Claude-labeled test pairs into a queue for a blind human check
  agreement   compare the human spot check with Claude's verdicts

Labels go to the same ``data/labels/<task>.jsonl`` files as the review app. A label made by a
human in the app is never replaced by an import unless ``--overwrite``.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import string
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from runbook_retriever.config import REPO_ROOT, Paths, get_settings
from runbook_retriever.corpus import Chunk, load_corpus
from runbook_retriever.io import write_jsonl, write_text_atomic
from runbook_retriever.labeling import (
    AUDIT_VERDICTS,
    NEGATIVE_VERDICTS,
    TEST_VERDICTS,
    LabelStore,
    Task,
    load_queue,
)
from runbook_retriever.logging_setup import setup_logging

log = logging.getLogger(__name__)

LLM_TASKS: tuple[Task, ...] = ("test_pairs", "so_questions", "train_audit", "negatives_audit")
BATCH_SIZE: dict[Task, int] = {
    "test_pairs": 20,
    "so_questions": 10,
    "train_audit": 50,
    "negatives_audit": 25,
}
LABELER = "claude"
SPOT_CHECK_N = 30
PROMPT = REPO_ROOT / "docs" / "LABELING_PROMPT.md"
LETTERS = string.ascii_uppercase


class LabelFormatError(ValueError):
    pass


def labeling_dir(paths: Paths) -> Path:
    return paths.data / "llm_labeling"


# --- export ----------------------------------------------------------------------------


def _chunk_xml(tag: str, chunk: Chunk, letter: str | None = None) -> str:
    attrs = f' letter="{letter}"' if letter else ""
    return f'<{tag}{attrs} id="{chunk.chunk_id}">\n{chunk.passage}\n</{tag}>'


def render_item(task: Task, item: Mapping[str, Any], chunks: Mapping[str, Chunk]) -> str:
    parts = [f'<item id="{item["id"]}">']
    if task == "so_questions":
        parts.append(f"<question>\n{item['question']}\n</question>")
    else:
        parts.append(f"<query>{item['query']}</query>")
    if task == "test_pairs":
        parts.append(_chunk_xml("labeled_chunk", chunks[item["chunk_id"]]))
    elif task == "train_audit":
        parts.append(_chunk_xml("chunk", chunks[item["chunk_id"]]))
    elif task == "negatives_audit":
        parts.append(_chunk_xml("positive_chunk", chunks[item["chunk_id"]]))
        parts.append(_chunk_xml("negative_chunk", chunks[item["negative_id"]]))
    for letter, cid in zip(LETTERS, item.get("candidates", []), strict=False):
        parts.append(_chunk_xml("candidate", chunks[cid], letter))
    parts.append("</item>")
    return "\n".join(parts)


def render_batch(
    task: Task,
    items: list[dict[str, Any]],
    chunks: Mapping[str, Chunk],
    prompt: str,
    number: int,
    total: int,
) -> str:
    header = (
        f"# Batch: task `{task}`, {number} of {total}, {len(items)} items\n\n"
        f"Label every item below for the task **`{task}`**, following the instructions."
    )
    body = "\n\n".join(render_item(task, item, chunks) for item in items)
    return f"{prompt.rstrip()}\n\n---\n\n{header}\n\n{body}\n"


def export(paths: Paths, chunks: Mapping[str, Chunk], prompt: str) -> dict[str, int]:
    out_dir = labeling_dir(paths) / "batches"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.md"):
        old.unlink()
    counts: dict[str, int] = {}
    for task in LLM_TASKS:
        queue = load_queue(paths.data / "review" / f"{task}.jsonl")
        size = BATCH_SIZE[task]
        batches = [queue[i : i + size] for i in range(0, len(queue), size)]
        for n, batch in enumerate(batches, start=1):
            text = render_batch(task, batch, chunks, prompt, n, len(batches))
            write_text_atomic(out_dir / f"{task}-{n:02d}.md", text)
        counts[task] = len(batches)
    (labeling_dir(paths) / "answers").mkdir(exist_ok=True)
    return counts


# --- import ----------------------------------------------------------------------------


def extract_json_lines(text: str) -> list[dict[str, Any]]:
    """Every line of ``text`` that is a JSON object (code fences and prose are ignored)."""
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip().rstrip(",")
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise LabelFormatError(f"not valid JSON: {line[:80]!r} ({e.msg})") from e
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _letters(answer: Mapping[str, Any], key: str, candidates: list[str]) -> list[str]:
    raw = answer.get(key)
    if not isinstance(raw, list):
        raise LabelFormatError(f"{key} must be a list of letters")
    out: list[str] = []
    for letter in raw:
        text = str(letter).strip().upper()
        index = LETTERS.index(text) if len(text) == 1 and text in LETTERS else -1
        if index < 0 or index >= len(candidates):
            raise LabelFormatError(f"{key} has unknown letter {letter!r}")
        out.append(candidates[index])
    return list(dict.fromkeys(out))


def _verdict(answer: Mapping[str, Any], allowed: tuple[str, ...]) -> str:
    verdict = str(answer.get("verdict", "")).strip().lower()
    if verdict not in allowed:
        raise LabelFormatError(f"verdict {answer.get('verdict')!r} is not one of {allowed}")
    return verdict


def to_label(task: Task, item: Mapping[str, Any], answer: Mapping[str, Any]) -> dict[str, Any]:
    """The label row the review app would write for this item, plus labeler and reason."""
    reason = str(answer.get("reason", ""))[:300]
    base = {"labeler": LABELER, "reason": reason}
    if task == "test_pairs":
        verdict = _verdict(answer, TEST_VERDICTS)
        extras = _letters(answer, "also_relevant", item["candidates"])
        if verdict != "correct":
            extras = []  # extra relevant chunks only matter for pairs kept in the test set
        return base | {
            "verdict": verdict,
            "query": item["query"],
            "chunk_id": item["chunk_id"],
            "also_relevant": extras,
        }
    if task == "so_questions":
        return base | {
            "relevant": _letters(answer, "relevant", item["candidates"]),
            "query": item["query"],
            "dataset_row": item["dataset_row"],
            "author": item["author"],
        }
    if task == "train_audit":
        return base | {
            "verdict": _verdict(answer, AUDIT_VERDICTS),
            "query": item["query"],
            "chunk_id": item["chunk_id"],
        }
    return base | {
        "verdict": _verdict(answer, NEGATIVE_VERDICTS),
        "query": item["query"],
        "chunk_id": item["chunk_id"],
        "negative_id": item["negative_id"],
    }


def _same(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    keys = ("verdict", "also_relevant", "relevant", "reason", "labeler")
    return all(a.get(k) == b.get(k) for k in keys)


def import_answers(paths: Paths, *, overwrite: bool = False) -> dict[str, Any]:
    queues = {t: load_queue(paths.data / "review" / f"{t}.jsonl") for t in LLM_TASKS}
    where = {item["id"]: (task, item) for task, q in queues.items() for item in q}
    answers: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    files = sorted(p for p in (labeling_dir(paths) / "answers").rglob("*") if p.is_file())
    for path in files:
        try:
            rows = extract_json_lines(path.read_text(encoding="utf-8"))
        except LabelFormatError as e:
            errors.append(f"{path.name}: {e}")
            continue
        for row in rows:
            item_id = str(row.get("id", ""))
            if item_id not in where:
                errors.append(f"{path.name}: unknown id {item_id!r}")
                continue
            if item_id in answers and answers[item_id] != row:
                log.warning("%s: id %s answered again; using this later answer", path.name, item_id)
            answers[item_id] = row

    stats: Counter[str] = Counter()
    for task in LLM_TASKS:
        store = LabelStore(paths.data / "labels" / f"{task}.jsonl")
        for item in queues[task]:
            answer = answers.get(item["id"])
            if answer is None:
                continue
            try:
                label = to_label(task, item, answer)
            except LabelFormatError as e:
                errors.append(f"{task} {item['id']}: {e}")
                continue
            existing = store.get(item["id"])
            if existing and existing.get("labeler") != LABELER and not overwrite:
                stats["kept_human"] += 1
                continue
            if existing and _same(existing, label):
                stats["unchanged"] += 1
                continue
            store.put(item["id"], label)
            stats["saved"] += 1
    return {
        "files": len(files),
        "answers": len(answers),
        "stats": dict(stats),
        "errors": errors,
        "missing": missing_items(paths, queues),
    }


def missing_items(paths: Paths, queues: Mapping[Task, list[dict[str, Any]]]) -> dict[str, Any]:
    """Per task: unlabeled count and the batch files that still have gaps."""
    out: dict[str, Any] = {}
    for task, queue in queues.items():
        labeled = LabelStore(paths.data / "labels" / f"{task}.jsonl").labeled_ids()
        size = BATCH_SIZE[task]
        gaps = sorted(
            {
                f"{task}-{i // size + 1:02d}.md"
                for i, it in enumerate(queue)
                if it["id"] not in labeled
            }
        )
        out[task] = {
            "labeled": len(queue) - sum(it["id"] not in labeled for it in queue),
            "total": len(queue),
            "batches_with_gaps": gaps,
        }
    return out


# --- spot check ------------------------------------------------------------------------


def make_spot_check(paths: Paths, n: int, seed: int) -> int:
    """Random Claude-labeled test pairs, re-labeled blind by a human in the review app."""
    queue = load_queue(paths.data / "review" / "test_pairs.jsonl")
    labels = LabelStore(paths.data / "labels" / "test_pairs.jsonl")
    pool = [
        item
        for item in queue
        if (lab := labels.get(item["id"])) is not None and lab.get("labeler") == LABELER
    ]
    if not pool:
        raise SystemExit("no Claude labels on test pairs yet: run `import` first")
    sample = random.Random(seed).sample(pool, min(n, len(pool)))
    write_jsonl(paths.data / "review" / "spot_check.jsonl", sample)
    return len(sample)


def agreement(paths: Paths) -> dict[str, Any]:
    claude = LabelStore(paths.data / "labels" / "test_pairs.jsonl")
    human = LabelStore(paths.data / "labels" / "spot_check.jsonl").all()
    if not human:
        raise SystemExit("no spot-check labels yet: label the Spot check page in `make review`")
    pairs = [
        (h["verdict"], c["verdict"])
        for item_id, h in human.items()
        if (c := claude.get(item_id)) is not None and c.get("labeler") == LABELER
    ]
    agree = sum(h == c for h, c in pairs)
    return {
        "n": len(pairs),
        "agreement": round(agree / len(pairs), 3) if pairs else None,
        "confusion_human_vs_claude": dict(Counter(f"{h}/{c}" for h, c in pairs)),
        "disagreements": sorted(
            item_id
            for item_id, h in human.items()
            if (c := claude.get(item_id)) is not None and c.get("verdict") != h["verdict"]
        ),
    }


# --- cli -------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("export")
    imp = sub.add_parser("import")
    imp.add_argument("--overwrite", action="store_true", help="also replace human labels")
    spot = sub.add_parser("spot-check")
    spot.add_argument("-n", type=int, default=SPOT_CHECK_N)
    sub.add_parser("agreement")
    args = parser.parse_args(argv)
    setup_logging()
    settings = get_settings()
    paths = settings.paths

    if args.command == "export":
        chunks = {c.chunk_id: c for c in load_corpus(paths.corpus)}
        counts = export(paths, chunks, PROMPT.read_text(encoding="utf-8"))
        log.info("wrote %s batch files to %s", counts, labeling_dir(paths) / "batches")
        log.info("save each Claude reply under %s (any file name)", labeling_dir(paths) / "answers")
    elif args.command == "import":
        report = import_answers(paths, overwrite=args.overwrite)
        for err in report["errors"]:
            log.error("%s", err)
        log.info(
            "read %d answers from %d files: %s", report["answers"], report["files"], report["stats"]
        )
        for task, m in report["missing"].items():
            gaps = ", ".join(m["batches_with_gaps"]) or "none"
            log.info(
                "%-16s %3d / %3d labeled; batches with gaps: %s",
                task,
                m["labeled"],
                m["total"],
                gaps,
            )
        return 1 if report["errors"] else 0
    elif args.command == "spot-check":
        n = make_spot_check(paths, args.n, settings.seed)
        log.info("spot check queue: %d test pairs; label them on the Spot check page", n)
    else:
        result = agreement(paths)
        write_text_atomic(
            paths.root / "results" / "label_agreement.json", json.dumps(result, indent=2) + "\n"
        )
        log.info("human vs Claude agreement on %d test pairs: %s", result["n"], result["agreement"])
        log.info("confusion (human/claude): %s", result["confusion_human_vs_claude"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
