"""Phase 2b: generate search queries for corpus chunks with Gemini.

Chunks are sent in batches (one split per batch) with a strict JSON schema. Every
response is cached, so the run is resumable: when the per-process call budget or the
daily quota runs out, rerun the same command and it continues where it stopped.
Order: test, then val, then train, runbooks first within each split.

    python -m runbook_retriever.gen_queries --limit-batches 2   # pilot
    python -m runbook_retriever.gen_queries                     # everything
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import random
import re
from collections import Counter
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from runbook_retriever.config import get_settings
from runbook_retriever.corpus import Chunk, load_corpus
from runbook_retriever.io import write_jsonl
from runbook_retriever.llm import (
    AllModelsExhaustedError,
    CachedLLM,
    CallBudgetExceededError,
    LLMError,
    parse_json,
)
from runbook_retriever.logging_setup import setup_logging
from runbook_retriever.runlog import RunTracker
from runbook_retriever.splits import Split, load_doc_splits

log = logging.getLogger(__name__)

PROMPT_VERSION = 3
BATCH_SIZE = 8
QUERIES_PER_CHUNK = 3
TEMPERATURE = 0.8
MAX_CODE_FRACTION = 0.8  # skip chunks that are almost entirely code (D9)
MIN_PROSE_CHARS = 120

Style = Literal["incident_snapshot", "symptom", "error_string", "how_to", "kubectl_output"]
STYLES: tuple[Style, ...] = (
    "incident_snapshot",
    "symptom",
    "error_string",
    "how_to",
    "kubectl_output",
)
SPLIT_ORDER: dict[Split, int] = {"test": 0, "val": 1, "train": 2}

_FENCED = re.compile(r"```.*?```", re.DOTALL)

# Generated pod / ReplicaSet names: "<name>-<rs-hash>[-<pod-suffix>]".
# The suffix may be followed by "_" (BackOff events print "<pod>_<namespace>(<uid>)").
_GENERATED_NAME = re.compile(
    r"\b([a-z][a-z0-9]*(?:-[a-z][a-z0-9]*)*)-([a-z0-9]{8,10})(-[a-z0-9]{5})?(?![a-z0-9])"
)
# Kubernetes' SafeEncodeString alphabet, used for ReplicaSet hashes and pod suffixes.
_K8S_ALPHABET = "bcdfghjklmnpqrstvwxz2456789"


# --- Chunk eligibility ---------------------------------------------------------------


def code_fraction(text: str) -> float:
    code = sum(len(m) for m in _FENCED.findall(text))
    return code / max(len(text), 1)


def randomize_names(query: str) -> str:
    """Give every generated pod/ReplicaSet name a fresh hash, seeded by the query text.

    LLMs reuse the same few hashes (often copied from the prompt or passage); left alone,
    those strings become a spurious shortcut shared by unrelated queries.
    """
    if not _GENERATED_NAME.search(query):
        return query
    rng = random.Random(hashlib.sha256(query.encode("utf-8")).digest())
    mapping: dict[str, str] = {}  # same original name -> same new name within a query

    def fresh(original: str) -> str:
        if original not in mapping:
            mapping[original] = "".join(rng.choice(_K8S_ALPHABET) for _ in range(len(original)))
        return mapping[original]

    def sub(m: re.Match[str]) -> str:
        rs_hash = m.group(2)
        # Real hashes mix letters and digits; skip words ("-workloads") and dates ("-20240101").
        if not (any(ch.isdigit() for ch in rs_hash) and any(ch.isalpha() for ch in rs_hash)):
            return m.group(0)
        suffix = "-" + fresh(m.group(3)[1:]) if m.group(3) else ""
        return f"{m.group(1)}-{fresh(rs_hash)}{suffix}"

    return _GENERATED_NAME.sub(sub, query)


def is_eligible(chunk: Chunk) -> bool:
    prose = _FENCED.sub("", chunk.text).strip()
    return code_fraction(chunk.text) <= MAX_CODE_FRACTION and len(prose) >= MIN_PROSE_CHARS


# --- Prompt and schema ---------------------------------------------------------------

STYLE_GUIDE = """\
- incident_snapshot: what an on-call engineer or an automated agent sees during an incident,
  pasted as one query. It must combine at least two concrete signals: a pod/node status line,
  event messages, an exit code or reason, a short log tail. It must be consistent with how
  Kubernetes really behaves (for example ImagePullBackOff pods have 0 restarts).
  Example: "payments-api-7c9d8b6f5-x2k4l 0/1 CrashLoopBackOff 6 (40s ago) | Last State:
  Terminated Reason: OOMKilled Exit Code: 137 | log: java.lang.OutOfMemoryError: Java heap space"
- symptom: a stressed engineer describing what they observe in their own words, no exact
  error text. Example: "pods keep restarting every few seconds right after we deployed"
- error_string: one exact error message or event text as it would be pasted into search.
  Example: "Back-off pulling image \\"registry.example.com/shop/cart:2.4.1\\""
- how_to: a task question. Example: "how do I raise the memory limit on a deployment"
- kubectl_output: pasted OUTPUT of a kubectl command (get table rows, describe fields, event
  lines, rollout status messages). Never the kubectl command itself.
  Example: "NAME READY STATUS RESTARTS AGE cart-6f7d9c8b5-q2w4e 0/1 OOMKilled 4 (12s ago) 3m"
"""

PROMPT_TEMPLATE = """\
You create search queries for training a retrieval model for Kubernetes troubleshooting.
For EACH passage below, write exactly {n} queries that this passage answers.

Rules:
- Each query must be answerable by THIS passage specifically, not just by Kubernetes knowledge
  in general. Target what is distinctive about the passage.
- Write like a stressed on-call engineer: terse, sometimes lowercase, no "according to the docs".
- Do not copy sentences from the passage. Paraphrase. Exception: error_string and
  kubectl_output queries may quote messages or output formats that appear in the passage, but
  change names, namespaces, numbers and image tags.
- Never mention the passage title or section name verbatim, and do not paraphrase the
  passage's first sentence.
- A query that a generic Kubernetes overview page would answer equally well is not acceptable.
- Use realistic, varied names: deployments like cart, ledger-worker, auth-api; pods with a
  ReplicaSet hash and suffix like cart-5d8f7c6b9d-x2k4l; namespaces like prod, payments, team-a.
  Never placeholders such as my-app, my-pod, abcde, xyz, foo, example-app.
- Use {n} different styles per passage, chosen from the list below, picking the styles that fit
  the passage. Prefer incident_snapshot, symptom and error_string when the passage is about a
  failure; use how_to, symptom and kubectl_output for task or reference passages.
- Never invent error, warning or event message texts. Only use messages that appear in the
  passage or that Kubernetes and common runtimes really emit. If the passage is not about a
  failure, do not write incident_snapshot or error_string queries for it.
- If a passage is navigation, a changelog, a list of links, or has no troubleshooting or
  operational value, set "suitable" to false and return no queries.

Styles:
{styles}
Passages:
{passages}
"""

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "passage": {"type": "integer"},
                    "suitable": {"type": "boolean"},
                    "queries": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "style": {"type": "string", "enum": list(STYLES)},
                                "query": {"type": "string"},
                            },
                            "required": ["style", "query"],
                        },
                    },
                },
                "required": ["passage", "suitable", "queries"],
            },
        }
    },
    "required": ["results"],
}


MIN_QUERY_CHARS, MAX_QUERY_CHARS = 8, 600


class GenQuery(BaseModel):
    style: Style
    query: str = Field(min_length=MIN_QUERY_CHARS, max_length=MAX_QUERY_CHARS)


class GenResult(BaseModel):
    passage: int
    suitable: bool
    queries: list[dict[str, Any]] = []  # validated one by one, so one bad query costs one query


def build_prompt(batch: Sequence[Chunk]) -> str:
    passages = "\n".join(
        f"<passage id={i}>\n{c.passage}\n</passage>" for i, c in enumerate(batch, start=1)
    )
    return PROMPT_TEMPLATE.format(n=QUERIES_PER_CHUNK, styles=STYLE_GUIDE, passages=passages)


# --- Batching and parsing ------------------------------------------------------------


@dataclass(frozen=True)
class Batch:
    split: Split
    chunks: tuple[Chunk, ...]


def make_batches(chunks: list[Chunk], doc_splits: dict[str, Split]) -> list[Batch]:
    """Group eligible chunks into batches that never mix splits, test first."""

    def order(c: Chunk) -> tuple[int, int, str]:
        return (SPLIT_ORDER[doc_splits[c.doc_id]], 0 if c.source == "runbook" else 1, c.chunk_id)

    eligible = sorted((c for c in chunks if is_eligible(c)), key=order)
    batches: list[Batch] = []
    for split in SPLIT_ORDER:
        group = [c for c in eligible if doc_splits[c.doc_id] == split]
        batches += [
            Batch(split, tuple(group[i : i + BATCH_SIZE])) for i in range(0, len(group), BATCH_SIZE)
        ]
    return batches


def _validated(items: list[Any], model: type[BaseModel], where: str) -> Iterator[Any]:
    for item in items:
        try:
            yield model.model_validate(item)
        except ValidationError as e:
            log.debug("skipping invalid %s in %s: %s", model.__name__, where, e)


def parse_response(text: str, batch: Batch) -> Iterator[dict[str, Any]]:
    """Validate a response and yield one row per query.

    Validation is per passage and per query: one malformed or overlong query is dropped on
    its own instead of discarding the whole batch.
    """
    where = batch.chunks[0].chunk_id
    try:
        payload = parse_json(text)
    except ValueError as e:
        log.warning("unparseable response for batch starting %s: %s", where, e)
        return
    results = payload.get("results", []) if isinstance(payload, dict) else []
    for result in _validated(results, GenResult, where):
        if not 1 <= result.passage <= len(batch.chunks) or not result.suitable:
            continue
        chunk = batch.chunks[result.passage - 1]
        seen: set[str] = set()
        valid = list(_validated(result.queries, GenQuery, where))
        for q in valid[:QUERIES_PER_CHUNK]:
            text_q = randomize_names(" ".join(q.query.split()))
            if text_q.casefold() in seen:
                continue
            seen.add(text_q.casefold())
            yield {
                "query": text_q,
                "style": q.style,
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "source": chunk.source,
                "split": batch.split,
            }


# --- Run -----------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit-batches", type=int, default=0, help="pilot: only first N batches")
    parser.add_argument("--skip-batches", type=int, default=0, help="pilot: skip first N batches")
    parser.add_argument("--workers", type=int, default=3, help="concurrent requests (rate-limited)")
    args = parser.parse_args(argv)
    setup_logging()
    settings = get_settings()
    paths = settings.paths
    chunks = load_corpus(paths.corpus)
    doc_splits = load_doc_splits(paths.splits / "doc_splits.json")
    batches = make_batches(chunks, doc_splits)
    batches = batches[args.skip_batches :]
    if args.limit_batches:
        batches = batches[: args.limit_batches]
    llm = CachedLLM.from_settings(settings, f"queries-v{PROMPT_VERSION}")
    log.info("%d eligible chunks in %d batches", sum(len(b.chunks) for b in batches), len(batches))

    config = {
        "prompt_version": PROMPT_VERSION,
        "batch_size": BATCH_SIZE,
        "temperature": TEMPERATURE,
        "models": llm.models,
        "batches": len(batches),
    }
    rows: list[dict[str, Any]] = []
    status: Counter[str] = Counter()
    with RunTracker(
        phase="2", name="gen_queries", config=config, seed=settings.seed, runs_csv=paths.runs_csv
    ) as run:

        def one(batch: Batch) -> tuple[Batch, str | None, str, bool]:
            try:
                res = llm.generate(
                    build_prompt(batch.chunks), temperature=TEMPERATURE, schema=RESPONSE_SCHEMA
                )
                return batch, res.text, res.model, res.cached
            except (CallBudgetExceededError, AllModelsExhaustedError):
                return batch, None, "budget", False
            except LLMError as e:
                log.warning("batch %s failed: %s", batch.chunks[0].chunk_id, e)
                return batch, None, "error", False

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for i, (batch, text, model, cached) in enumerate(pool.map(one, batches), start=1):
                if text is None:
                    status[model] += 1
                    continue
                status["cached" if cached else model] += 1
                for row in parse_response(text, batch):
                    rows.append(row | {"model": model})
                if i % 20 == 0:
                    log.info("%d/%d batches done (%s)", i, len(batches), dict(status))

        out = paths.data / "queries" / "generated.jsonl"
        write_jsonl(out, sorted(rows, key=lambda r: (r["chunk_id"], r["style"], r["query"])))
        by_split = Counter(r["split"] for r in rows)
        by_style = Counter(r["style"] for r in rows)
        run.metrics = {
            "queries": len(rows),
            "by_split": dict(by_split),
            "by_style": dict(by_style),
            "batch_status": dict(status),
            "api_calls": llm.calls_made,
        }
    log.info(
        "wrote %d queries to %s; by split %s; by style %s",
        len(rows),
        out,
        dict(by_split),
        dict(by_style),
    )
    incomplete = status["budget"] + status["error"]
    if incomplete:
        log.warning(
            "%d batches not generated yet (quota/budget/errors); rerun to continue", incomplete
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
