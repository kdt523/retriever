# RunbookRetriever — project context for Claude Code

Read `docs/PLAN.md` before starting any task. It is the full build plan and research, carried over from a claude.ai planning chat (live doc: https://claude.ai/code/artifact/e37ce32b-e12d-4eae-81f5-d96fc92ee858). The live doc will NOT sync with changes made here; `docs/PLAN.md` is the source of truth in this repo.

## What we're building
Fine-tune a small embedding model (`BAAI/bge-small-en-v1.5`, 33M) so it retrieves the right Kubernetes runbook / doc chunk from messy incident signals (pod status, events, exit codes, log tails). It becomes the `search_runbooks` retrieval tool inside **OpsPilot**, kd's AI incident-response agent for Kubernetes (Gemini 2.5 Flash as the agent LLM, AWS free tier for deployment).

## Why (research summary — details + sources in docs/PLAN.md)
- Runbooks matter more than the model for AI SRE agents (same model 4.6/5 with runbooks vs 3.6 without; 3–4 tool calls vs 20+).
- Existing tools match runbooks by alert-name regex/namespace → brittle. Semantic retrieval from incident signals is the gap.
- Embedding fine-tuning on synthetic data works, but keyword search is still needed → ship hybrid (BM25 + tuned dense, RRF).

## Three problems to target (priority order)
1. Incident signal → runbook (primary query style + headline test slice)
2. Exact identifiers (OOMKilled, CrashLoopBackOff, exit codes, error strings) → hybrid retrieval, per-slice reporting
3. Downstream impact + no-match detection → agent eval on a local `kind` cluster with injected faults; calibrated "no runbook matches" threshold

## Owner / machine
- kd (Krushna Datir), B.Tech IT student; this is a resume project for ML / agentic-AI / backend roles.
- Windows 11 (native, not WSL), ~16 GB RAM, **NVIDIA RTX 3050 Laptop GPU (4 GB VRAM, sm_86)**: train in fp16 locally; Kaggle only as fallback.
- Python 3.12 managed with **uv** (`make setup`); CUDA torch from the cu128 index. Has an AWS free-tier account.
- Prefers casual, direct, actionable replies.

## Hard rules (don't break these)
- Split train/val/test by `doc_id` BEFORE generating queries. Freeze the test set after Phase 3; never edit it later.
- One shared constant for the BGE query prefix, used in training, eval and serving.
- Cache every Gemini call to `data/cache/` so reruns are free.
- Hard-negative mining: ranks ~10–30 only, and drop negatives scoring above 95% of the positive's score.
- Report results per slice: incident snapshot, error string, real Stack Overflow question, how-to.
- Log every run's config, wall-clock time, peak RAM and metrics to `results/runs.csv`.
- Serving image: ONNX Runtime + int8 model only (no PyTorch) — AWS free tier ~1 GB RAM.

## Repo layout & commands
- Package `src/runbook_retriever/`: shared code (`config.py` holds `QUERY_PREFIX`, `MAX_SEQ_LENGTH`, paths, `RR_*` settings; `llm.py` cached Gemini client; `runlog.py` → `results/runs.csv`) plus one module per phase, run as `python -m runbook_retriever.<phase>` via Make targets.
- `make setup | check-env | check (lint+mypy strict+tests) | format`. Pipeline targets: `corpus data baseline train evaluate export serve`.
- Settings only via `config.py` (`RR_*` env / `.env`). Tests never hit the network (socket blocked in `tests/conftest.py`).
- Decisions not in PLAN.md go in `docs/DECISIONS.md`.
- `data/incidents/*.json` = real cluster captures; planned use: real incident-snapshot test queries in Phase 2.
- Build strictly phase by phase; stop at each phase's gate. OpsPilot integration comes later, not now.

## Current status
Phases 0-1 done: `make corpus` builds 3,340 chunks (197 k8s pages @ pinned commit + 35 runbooks). Runbooks verified against 36 real fault captures (`make cluster-up faults` → `data/incidents/`, k3d); runbooks must never copy scenario identifiers (leakage test). **Next: Phase 2 (doc-level splits stratified by source, Gemini query generation, filters, hard negatives, hand-checked test set).**
