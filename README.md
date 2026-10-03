# RunbookRetriever

Fine-tuned `BAAI/bge-small-en-v1.5` embeddings that retrieve the right Kubernetes runbook or doc
section from messy incident signals (pod status, events, exit codes, log tails).

> **Status:** Phase 1 (corpus) complete: 3,340 chunks from 197 Kubernetes doc pages + 35 runbooks
> (`results/corpus_stats.json`). 30 of the 35 runbooks are verified against real failures injected
> into a k3d cluster (`data/incidents/`). Results tables will appear here once Phases 3-5 run.
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
| 1 | Build corpus (`make inspect` to eyeball chunks) | `make corpus` | `data/corpus.jsonl` |
| 1b | Verify runbooks: inject 36 faults into k3d, record real output | `make cluster-up faults` | `data/incidents/` |
| 2 | Generate, filter, split, mine negatives | `make data` | `data/splits/` |
| 3 | Baselines | `make baseline` | `results/baseline.csv` |
| 4 | Fine-tune | `make train` | `models/` |
| 5 | Ablations, error analysis | `make evaluate` | `results/final.csv` |
| 6 | ONNX int8 + FastAPI | `make export serve` | `serve/` |

Every run appends its config, wall-clock time, peak RAM/VRAM and metrics to `results/runs.csv`.

### Phase 3 baselines (frozen test set, 269 queries, from `results/baseline.csv`)

| Retriever | hit@1 | hit@10 | MRR@10 | NDCG@10 |
| --- | --- | --- | --- | --- |
| BM25 | 0.628 | 0.885 | 0.705 | 0.557 |
| all-MiniLM-L6-v2 | 0.532 | 0.885 | 0.651 | 0.566 |
| bge-small-en-v1.5 | 0.565 | 0.892 | 0.684 | 0.626 |
| bge-base-en-v1.5 | 0.621 | 0.929 | 0.725 | 0.677 |
| Hybrid BM25 + bge-small (RRF) | 0.665 | 0.941 | 0.761 | 0.658 |

Test labels were written by Claude and audited by a blind human spot check (24/30 agreement,
`results/label_agreement.json`); see `docs/DECISIONS.md` D20. Per-slice numbers are in the CSV.

### Phase 4 fine-tuning (val set, 715 queries, from `results/tuned_val.csv`)

| Retriever | hit@1 | hit@5 | hit@10 | MRR@10 | NDCG@10 |
| --- | --- | --- | --- | --- | --- |
| bge-small (base) | 0.387 | 0.678 | 0.792 | 0.514 | 0.576 |
| bge-small tuned (`make train`) | 0.505 | 0.786 | 0.870 | 0.625 | 0.679 |
| Hybrid BM25 + tuned (RRF) | 0.546 | 0.814 | 0.891 | 0.659 | 0.709 |

Val is the model-selection set, so these numbers are optimistic; the frozen test set is scored
once in Phase 5. Training setup and deviations from the plan: `docs/DECISIONS.md` D21.

### Phase 5 results (frozen test set, 269 queries, from `results/final.csv`)

| Retriever | hit@1 | hit@5 | hit@10 | MRR@10 | NDCG@10 |
| --- | --- | --- | --- | --- | --- |
| BM25 | 0.628 | 0.822 | 0.885 | 0.705 | 0.557 |
| all-MiniLM-L6-v2 | 0.532 | 0.799 | 0.885 | 0.651 | 0.566 |
| bge-small (base) | 0.565 | 0.833 | 0.892 | 0.684 | 0.626 |
| bge-base | 0.621 | 0.881 | 0.929 | 0.725 | 0.677 |
| **bge-small tuned** | 0.639 | 0.892 | 0.941 | 0.746 | 0.664 |
| Hybrid BM25 + bge-small | 0.665 | 0.881 | 0.941 | 0.760 | 0.658 |
| **Hybrid BM25 + tuned** | 0.669 | 0.903 | 0.941 | 0.766 | 0.657 |

hit@5 per slice (n in the header row):

| Retriever | low overlap (n=59) | error string (n=27) | symptom (n=61) | how-to (n=64) | kubectl output (n=17) | real incident (seen runbook) (n=54) | real incident (held-out runbook) (n=10) | Stack Overflow (n=32) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BM25 | 0.661 | 1.000 | 0.770 | 0.734 | 1.000 | 0.926 | 1.000 | 0.594 |
| bge-small (base) | 0.831 | 0.926 | 0.803 | 0.859 | 0.824 | 0.907 | 1.000 | 0.594 |
| bge-base | 0.864 | 0.926 | 0.836 | 0.938 | 0.882 | 0.889 | 0.800 | 0.844 |
| **bge-small tuned** | 0.932 | 0.926 | 0.885 | 0.922 | 0.941 | 0.944 | 0.900 | 0.688 |
| **Hybrid BM25 + tuned** | 0.848 | 1.000 | 0.918 | 0.844 | 0.941 | 0.963 | 1.000 | 0.750 |

**What the numbers say**

- Fine-tuning helps, less than val suggested. On the test set the tuned bge-small gains
  +7.6 points hit@1 and +5.5 points hit@5 over the untuned model (mean over 3 seeds: hit@1
  0.641 ± 0.006, hit@5 0.888 ± 0.004), and it beats the 3x larger bge-base on hit@1, hit@5 and
  hit@10 but not on NDCG@10. The plan's target of +10 points hit@5 was met on val (+11.0) and
  not on test.
- BM25 is a strong baseline here: it wins hit@5 on error strings and kubectl output, and ties the
  tuned model on hit@1 overall. The hybrid (RRF of BM25 and the tuned model) has the best hit@1,
  hit@5 and MRR@10. NDCG@10 understates it on the incident slices (see D19).
- Stack Overflow questions are the weak spot: tuned hit@5 0.688 against 0.844 for bge-base
  (n=32, so one query is 3 points).
- Slices with 4 to 10 queries (incident snapshots, held-out incidents) are too small to rank
  retrievers; read them as smoke tests.

### Phase 5 ablations (`make ablate`, tables in `results/ablations.md`)

Test hit@5 / NDCG@10 (val in the same file); one run each unless noted.

| Variant | test hit@5 | test NDCG@10 | val NDCG@10 |
| --- | --- | --- | --- |
| untrained bge-small | 0.833 | 0.626 | 0.576 |
| 25% of training pairs | 0.848 | 0.632 | 0.642 |
| 50% of training pairs | 0.881 | 0.644 | 0.659 |
| 1 epoch instead of 3 | 0.870 | 0.646 | 0.652 |
| no hard negatives | 0.896 | 0.673 | 0.672 |
| full (3 seeds, mean) | 0.888 | 0.664 | 0.676 |

- More data helps steadily (25% to 50% to 100%), and three epochs beat one.
- Hard negatives did not help: val NDCG@10 is 0.004 lower without them, which is inside the
  seed spread (sd 0.002), and test is slightly higher without. The mined negatives (D17) are
  not buying anything at this data size.
- Seed spread is small (sd about 0.002 NDCG@10 on val).
- Not run: section-title prefix on/off, synthetic-only vs real queries, and the forgetting check
  on an MTEB retrieval subset.

### Error analysis (`results/error_analysis.md`)

The 30 test queries where the tuned model ranks the right chunk lowest, tagged by hand:
17 model misses (mostly the right page but a neighbouring chunk, or a long pasted question hiding
the real one), 9 ambiguous queries or incomplete answer keys (another returned chunk answers the
question as well), 2 questions with no good chunk in the corpus, and 2 wrong labels in the test
set (D22). That is about 4 of the 30 worst cases that are the test set's fault, not the model's.

## Repo layout

```
src/runbook_retriever/   # library + one module per pipeline phase
tests/                   # offline unit tests (network is blocked)
runbooks/                # hand-written runbooks (part of the corpus)
faults/                  # fault-injection scenarios used to verify runbooks
data/                    # raw sources, corpus, splits, LLM cache (git-ignored except splits)
results/                 # CSV results (committed)
configs/                 # training configs
serve/                   # FastAPI service (Phase 6)
docs/                    # plan and decision log
```

## Data sources and licences

- Kubernetes documentation from [kubernetes/website](https://github.com/kubernetes/website),
  pinned in `configs/corpus.yaml`, licensed CC BY 4.0. Chunks keep their source URL.
- `runbooks/`: written for this project; symptom text checked against `data/incidents/`.
