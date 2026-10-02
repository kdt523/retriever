# RunbookRetriever

Fine-tuned `BAAI/bge-small-en-v1.5` embeddings that retrieve the right Kubernetes runbook or doc
section from messy incident signals (pod status, events, exit codes, log tails).

> **Status:** Phase 0 (scaffold) complete. Results tables will appear here once Phases 3-5 run.
> No numbers are reported until they exist in `results/`.

The full plan, research and success criteria are in [docs/PLAN.md](docs/PLAN.md).

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/), GNU make, git. An NVIDIA GPU is optional
(training falls back to CPU).

```bash
make setup        # install Python 3.12 env with CUDA PyTorch + dev tools
cp .env.example .env   # then put your Gemini API key in it (needed from Phase 2)
make check-env    # print Python / torch / GPU / settings
make check        # lint + typecheck + tests
```

## Pipeline

| Phase | What | Make target | Output |
| --- | --- | --- | --- |
| 0 | Scaffold | `make check` | — |
| 1 | Build corpus | `make corpus` | `data/corpus.jsonl` |
| 2 | Generate, filter, split, mine negatives | `make data` | `data/splits/` |
| 3 | Baselines | `make baseline` | `results/baseline.csv` |
| 4 | Fine-tune | `make train` | `models/` |
| 5 | Ablations, error analysis | `make evaluate` | `results/final.csv` |
| 6 | ONNX int8 + FastAPI | `make export serve` | `serve/` |

Every run appends its config, wall-clock time, peak RAM/VRAM and metrics to `results/runs.csv`.

## Repo layout

```
src/runbook_retriever/   # library + one module per pipeline phase
tests/                   # offline unit tests (network is blocked)
runbooks/                # hand-written runbooks (part of the corpus)
data/                    # raw sources, corpus, splits, LLM cache (git-ignored except splits)
results/                 # CSV results (committed)
configs/                 # training configs
serve/                   # FastAPI service (Phase 6)
docs/                    # plan and decision log
```
