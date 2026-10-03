# RunbookRetriever

Fine-tuning a small embedding model (`BAAI/bge-small-en-v1.5`, 33M parameters) to find the right
Kubernetes runbook or documentation section from messy incident signals: pod status, events,
exit codes and log tails.

**The problem.** During an incident, an engineer (or an AI agent) pastes something like
`Reason: OOMKilled, Exit Code 137` and needs the one page that explains it. Keyword search misses
paraphrases, and an off-the-shelf embedding model has never seen Kubernetes failure modes.

**The result** on a locked 269-query test set (generated queries, real incidents, Stack Overflow
questions), searching 3,340 chunks:

| Retriever | Right chunk ranked 1st | In top 5 | In top 10 |
| --- | --- | --- | --- |
| BM25 keyword search | 62.8% | 82.2% | 88.5% |
| bge-small, no fine-tuning | 56.5% | 83.3% | 89.2% |
| bge-base (3x larger, no fine-tuning) | 62.1% | 88.1% | 92.9% |
| **bge-small, fine-tuned (mean of 3 seeds)** | **64.1%** | **88.8%** | **94.1%** |
| **Fine-tuned + BM25 hybrid** | **66.9%** | **90.3%** | **94.1%** |

Fine-tuning gains +7.6 points top-1 and +5.5 points top-5 over the same model untrained, and the
33M-parameter model matches the 3x larger bge-base. Seed-to-seed spread is small (top-5 sd 0.4
points). Every number here comes from [`results/`](results/); full metrics (MRR, NDCG) and
per-slice tables are in [`results/final.csv`](results/final.csv).

**A real example** from the test set. Query: *"pods without gpu requirements are landing on our
accelerated nodes and blocking jobs"*.

| | Top result | Rank of the correct chunk |
| --- | --- | --- |
| Untrained bge-small | *Pods Pending due to insufficient CPU or memory* (a runbook) | 22 |
| Fine-tuned | *Taints and Tolerations > Example Use Cases* (the GPU-node taint section) | 1 |

> **Status:** data pipeline, fine-tuning, evaluation, ablations and error analysis are done.
> An ONNX export and FastAPI search service are planned but not built, and the tuned model is not
> published yet (`models/` is git-ignored), so there is nothing to download or call today.

## How it works

1. **Corpus.** Kubernetes docs (3,340 chunks from 197 pages) plus 35 hand-written runbooks.
   30 of the runbooks were checked against real failures injected into a local k3d cluster
   (`faults/`, `data/incidents/`).
2. **Training data.** Gemini writes questions for each chunk in 5 styles (error string, symptom,
   how-to, kubectl output, incident snapshot). Questions that copy the chunk's wording, or that a
   baseline model cannot connect to their chunk, are dropped. Whole documents are assigned to
   train, validation or test before any generation, so test text never leaks into training.
   Result: about 5,000 question-passage pairs and 4,634 triplets with mined hard negatives.
3. **Fine-tuning** (`make train`). Contrastive learning with
   `CachedMultipleNegativesRankingLoss`: batch size 64 via gradient caching, learning rate 2e-5
   with 10% warmup, 3 epochs, fp16, max sequence length 256. One run takes about 10 minutes on a
   4 GB RTX 3050. The best checkpoint is chosen on a validation set, never on the test set.
4. **Evaluation** (`make evaluate`). Retrieval over the whole corpus on a test set frozen with
   file hashes. Metrics: hit@k (the right chunk is in the top k), MRR@10, NDCG@10, reported per
   query type. Compared against BM25, MiniLM, bge-small and bge-base.

## What the experiments showed

Ablations (`make ablate`), test set, one run each unless noted:

| Variant | top-5 | NDCG@10 |
| --- | --- | --- |
| No fine-tuning | 83.3% | 0.626 |
| 25% of the training pairs | 84.8% | 0.632 |
| 50% of the training pairs | 88.1% | 0.644 |
| 1 epoch instead of 3 | 87.0% | 0.646 |
| No hard negatives | 89.6% | 0.673 |
| Full recipe (3 seeds, mean) | 88.8% | 0.664 |

- More training data helps steadily, and 3 epochs beat 1.
- **Mined hard negatives gave no measurable gain** at this data size; the difference is inside
  the seed noise. They are kept in the pipeline but are not what produces the result.
- BM25 is a strong baseline on exact error strings and kubectl output, which is why the hybrid
  (rank fusion of BM25 and the tuned model) is the best system overall.
- **Error analysis** (`results/error_analysis.md`): of the 30 worst test queries, 17 are real
  model misses (usually the right page but a neighbouring chunk), 9 are ambiguous queries or
  answer keys that miss an equally good chunk, 2 have no good chunk in the corpus, and 2 are
  wrong labels.

## Limitations

- **The gain is smaller on the test set than on validation** (+5.5 vs +11.0 points top-5). The
  test set contains real incidents and Stack Overflow questions, which the generated training
  questions resemble less.
- **Stack Overflow questions are the weak spot**: tuned top-5 is 68.8% against 84.4% for
  bge-base (32 questions, so one question is 3 points).
- **Test labels were written by Claude and spot-checked by a human**: a blind check of 30 pairs
  agreed on 24 (80%), and the human verdict wins where they differ. Two test labels were later
  found to be wrong; the frozen files are not edited, and this is recorded in
  [`docs/DECISIONS.md`](docs/DECISIONS.md) (D20, D22).
- Slices with 4 to 10 queries (incident snapshots, held-out incidents) are too small to rank
  retrievers.
- Not done: section-title ablation, synthetic-vs-real training queries ablation, a forgetting
  check on a general retrieval benchmark.

## Reproduce

Requires [uv](https://docs.astral.sh/uv/), GNU make and git; an NVIDIA GPU is optional (training
falls back to CPU, slower). The committed `data/splits/` are enough to retrain and evaluate; a
Gemini key (`.env`, see `.env.example`) is only needed to regenerate the questions with
`make data`.

```bash
make setup        # Python 3.12 env with CUDA PyTorch
make corpus       # fetch the pinned Kubernetes docs and build data/corpus.jsonl
make check        # lint, type-check and 123 offline tests
make train        # fine-tune -> models/bge-small-rr
make evaluate     # test-set table -> results/final.csv, worst-30 error report
make ablate       # the 6 ablation/seed runs (about an hour on the RTX 3050)
```

Every run appends its config, wall-clock time, peak RAM/VRAM and metrics to `results/runs.csv`.
Design decisions and their reasons are logged in [`docs/DECISIONS.md`](docs/DECISIONS.md); the
original plan is [`docs/PLAN.md`](docs/PLAN.md).

**Built with** Python 3.12, PyTorch, sentence-transformers, Hugging Face datasets, Gemini API,
BM25 (rank-bm25), pytest, ruff, mypy, k3d, uv.

## Repo layout

```
src/runbook_retriever/   # library, one module per pipeline stage (train.py, evaluate.py, ...)
tests/                   # offline unit tests (network is blocked)
configs/                 # corpus and training configs
runbooks/                # hand-written runbooks (part of the corpus)
faults/                  # fault-injection scenarios used to verify the runbooks
data/                    # frozen splits and labels (raw sources and caches are git-ignored)
results/                 # result tables, ablations, error analysis
scripts/                 # ablation runner
review/                  # Streamlit app used to check the test labels
docs/                    # decision log and plan
```

## Data sources and licences

- Kubernetes documentation from [kubernetes/website](https://github.com/kubernetes/website),
  pinned in `configs/corpus.yaml`, licensed CC BY 4.0. Chunks keep their source URL.
- `runbooks/`: written for this project; symptom text checked against `data/incidents/`.
- Test questions from Stack Overflow, via the
  [`mcipriano/stackoverflow-kubernetes-questions`](https://huggingface.co/datasets/mcipriano/stackoverflow-kubernetes-questions)
  dataset, licensed CC BY-SA 4.0. The questions belong to their authors on Stack Overflow.
