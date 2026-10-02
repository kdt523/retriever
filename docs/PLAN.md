# RunbookRetriever — Fine-Tuned Embeddings for K8s Incident Retrieval

Plan as of Oct 2, 2026 · kd (Krushna Datir)

## Overview

Fine-tune a small embedding model (`bge-small-en-v1.5`, 33M params) so it finds the right Kubernetes runbook or doc section for a messy incident query. It then becomes the retrieval layer inside OpsPilot. Everything trains on a 12 GB RAM CPU laptop.

**The problem.** On-call queries look like `pod stuck Back-off restarting failed container after helm upgrade`. General embedders were trained on web text, so they match surface words and miss that this is a CrashLoopBackOff troubleshooting question. Bad retrieval means the LLM in OpsPilot answers from the wrong context.

**Why fine-tuning is the right fix (not just prompting).**

- Retrieval quality is decided by the embedding model, before any LLM sees the context. Prompting can't fix a wrong top-5.
- The domain has its own vocabulary: error strings, kubectl output, resource names. Contrastive fine-tuning teaches the model which phrasings mean the same incident.
- A tuned small model is cheap to run (CPU, milliseconds per query) versus paying an API per embedding.

**Success criteria (set these before you train).**

1. Tuned `bge-small` beats base `bge-small` by at least 10 points Recall@5 on a held-out, hand-verified test set.
2. Tuned `bge-small` matches or beats base `bge-base` (3x bigger). This is the headline result: small and tuned beats big and generic.
3. Query embedding under 50 ms on your laptop CPU.
4. Plugged into OpsPilot as a working `search_runbooks` tool.

## Research: where the real pain is

The biggest problem in AI incident response is not the LLM. It is getting the right runbook in front of the agent, from messy incident signals, at the moment it starts investigating. Teams that fix this see bigger gains than from swapping models. That is exactly the gap this project should attack.

| Pain point | Evidence | What it means for this project |
| --- | --- | --- |
| Troubleshooting eats ops time | Over 60% of ops time goes to troubleshooting, median MTTR is over 50 minutes, and only 20% of incidents resolve without escalation. Skills gaps are named as a main constraint. ([Komodor 2025](https://komodor.com/blog/komodor-2025-enterprise-kubernetes-report-finds-nearly-80-of-production-outages/)) | A faster, correct first-pass diagnosis is the value. Measure it, not just Recall@5. |
| Runbooks beat models | Same model scored 4.6/5 with runbooks vs 3.6 without. With runbooks: 3 to 4 tool calls; without: 20+ steps chasing wrong hypotheses. Wasted calls fell from 16 to 2. ([CNCF / STCLab](https://www.cncf.io/blog/2026/04/21/auto-diagnosing-kubernetes-alerts-with-holmesgpt-and-cncf-tools/)) | Retrieval quality directly sets agent quality. |
| Runbook matching is brittle | HolmesGPT custom runbooks match on a regex of the alert name ([example](https://github.com/HolmesGPT/holmesgpt/blob/master/examples/custom_runbooks.yaml)). STCLab organizes runbooks by namespace and alert type. | New alerts, renamed alerts and symptoms described differently get no runbook. Semantic retrieval from incident signals fixes this. |
| Agents still fail at K8s root cause | Best frontier model scores 47% on ITBench-AA SRE; models that over-investigate add false root causes. ([IBM / Artificial Analysis](https://huggingface.co/blog/ibm-research/itbench-aa)) Hallucinated data interpretation persists across all models, and prompting alone does not fix it. ([arXiv 2602.09937](https://arxiv.org/abs/2602.09937)) | Grounding the agent is an open, high-value problem. |
| Retrieving the right procedure works | SOP-guided RCA (with a tool to find relevant SOPs) reached 64.01% accuracy vs 35.50% for plain ReAct. ([Flow-of-Action](https://arxiv.org/abs/2502.08224)) | Strong published evidence that runbook retrieval is worth optimizing. |
| Embedding fine-tuning works, with limits | Synthetic-data fine-tuning gave +7 NDCG@1, with gains on rare-identifier queries, yet keyword search was still needed. ([Cisco](https://blogs.cisco.com/ai/fine-tuning-embedding-models-for-enterprise-retrieval-a-practical-guide-with-nvidia-nemotron-recipe)) Domain tuning can hurt general retrieval. ([arXiv 2409.18511](https://arxiv.org/pdf/2409.18511)) | Ship hybrid (BM25 + tuned dense). Report forgetting honestly. |
| Training-data traps | Naive top-k negative mining adds false negatives and lowers accuracy; positive-aware mining does best. ([NV-Retriever](https://arxiv.org/html/2407.15831)) | Add a margin rule to negative mining. |
| Real queries are available | 30,044 Stack Overflow Kubernetes Q&A pairs, CC BY-SA 4.0. ([Hugging Face](https://huggingface.co/datasets/mcipriano/stackoverflow-kubernetes-questions)) | Real user queries for evaluation and extra training, not synthetic only. |

### The three problems to target

1. **Incident signal to runbook.** The query is not a tidy question. It is what OpsPilot sees: pod status, recent events, exit code, last log lines. Generic embedders and alert-name regex both fail here. Make this the primary query style in training and the headline test slice.
2. **Exact identifiers.** Reason codes (`OOMKilled`, `CrashLoopBackOff`), exit codes, and error strings must match precisely. Use hybrid retrieval (BM25 + tuned dense, reciprocal rank fusion) as the default, and report results per slice.
3. **Downstream impact, and knowing when nothing matches.** Prove the agent gets better, not just the retriever. Also return "no runbook matches" when the top score is below a calibrated threshold, so the agent never follows a wrong runbook.

### Changes to the plan

- **Phase 1:** write runbooks in the STCLab style, with a metadata header (scope, tools available, cautions) plus symptoms, checks and fixes.
- **Phase 2:** add an *incident snapshot* query style generated from runbooks (fake but realistic `kubectl describe` events and log tails). Use Stack Overflow questions as real queries: hand-map about 50 to corpus chunks for a real-query test slice, and try question to best-answer pairs as extra training data. Drop mined negatives that score above 95% of the positive's score.
- **Phase 3 and 5:** report four slices: incident snapshot, error string, real Stack Overflow question, how-to. Add a forgetting check on a small general retrieval set.
- **Phase 6:** hybrid is the default mode; add the calibrated no-match threshold.
- **New agent eval (week 4):** inject 10 to 15 faults into a local single-node `kind` cluster (bad image, OOM, failing probe, missing ConfigMap, NetworkPolicy block). Run OpsPilot with no retrieval, base retrieval, and tuned hybrid retrieval. Compare correct-diagnosis rate, tool calls and time to diagnosis.

That last eval upgrades the resume line from "improved Recall@5" to "cut OpsPilot's tool calls per diagnosis from X to Y and raised correct diagnoses from A% to B%".

## System architecture

Two halves: an offline pipeline you run once on your laptop to produce the tuned model, and an online path where OpsPilot calls that model on every incident.

```
OFFLINE (train once, laptop CPU)
Docs + runbooks -> Chunk corpus -> Generate queries (Gemini) -> Filter & split by doc_id
   -> Mine hard negatives -> FINE-TUNE bge-small -> Evaluate vs BM25/bge-base -> Export ONNX int8 + FAISS
                                                                                        |
ONLINE (every incident in OpsPilot)                                                     v (tuned model)
Incident signals (pod status, events, logs) -> OpsPilot agent (Gemini) -> Search API (/search) -> Diagnosis citing runbook
```

The fine-tune step is the core. Everything before it builds the training data; everything after it proves and ships the result.

## Tech stack and environment

Windows 11, 12 GB RAM, assume no GPU. Use WSL2 or plain Python 3.11 with a venv. The only rate-limited piece is the LLM used to generate training queries.

| Layer | Choice | Why |
| --- | --- | --- |
| Base model | `BAAI/bge-small-en-v1.5` (33M, 384-dim) | Strong small retriever, trains on CPU |
| Comparison models | `all-MiniLM-L6-v2`, `bge-base-en-v1.5`, BM25 | Baselines for the results table |
| Training | `sentence-transformers` (v3+ Trainer API), PyTorch CPU | Built-in contrastive losses and IR evaluator |
| Query generation | Gemini 2.5 Flash API | Already the OpsPilot LLM |
| Parsing and chunking | `markdown-it-py` or simple heading splitter | K8s docs are Markdown |
| Vector index | FAISS (CPU) or Chroma | Simple, local, fast |
| Serving | FastAPI + ONNX Runtime (int8) via `optimum` | Fast CPU inference, small memory |
| Tracking | MLflow or a plain CSV results log | Every run's config and metrics saved |
| Model hosting | Hugging Face Hub | Public model card = proof of work |

**Memory budget.** Training `bge-small` at sequence length 256 and batch 32 fits in 12 GB. For large effective batches without more RAM, use `CachedMultipleNegativesRankingLoss`.

**If training feels slow,** time the first 50 steps and extrapolate. Use a free Kaggle notebook only for the bigger ablations.

## Phase 1: Build the corpus

Goal: about 1,500 to 3,000 clean, self-contained chunks of Kubernetes troubleshooting knowledge, each with its source and section title.

**Sources.**

1. Official Kubernetes docs from the `kubernetes/website` GitHub repo (`content/en/docs`). Focus on `tasks/debug`, `concepts/workloads`, `concepts/configuration`, `concepts/services-networking`, and `reference/kubectl`. Clone the repo; don't scrape the site.
2. Your own OpsPilot runbooks: one Markdown file per failure mode (CrashLoopBackOff, ImagePullBackOff, OOMKilled, Pending pods, failed readiness probes, node NotReady, DNS failures, PVC stuck, and so on). Write 15 to 25. STCLab-style metadata header (scope, tools, cautions) + symptoms, checks, fixes.
3. Optional: Helm or ingress-nginx troubleshooting pages if OpsPilot will touch them.

**Chunking rules.**

- Split on Markdown headings first, then cap at about 300 tokens with a 50-token overlap.
- Prepend page title and section heading to each chunk (`Debug Pods > My pod keeps crashing`).
- Strip Hugo shortcodes, front matter and nav noise. Keep code blocks and kubectl output.
- Drop chunks under about 40 tokens.

**Output.** `data/corpus.jsonl`: `chunk_id`, `doc_id`, `source_path`, `title`, `section`, `text`.

**Done when** 20 random chunks each make sense on their own.

## Phase 2: Training data

Goal: about 4,000 to 6,000 (query, positive chunk) pairs, a hand-verified test set of about 200 queries, and mined hard negatives.

**Step 1: Split by document first.** Assign whole `doc_id`s to train (80%), val (10%), test (10%) before generating anything.

**Step 2: Generate queries with Gemini.** For each chunk, 3 queries in different styles:

| Style | Example |
| --- | --- |
| Incident snapshot (primary) | `Reason: CrashLoopBackOff, Exit Code 137, Last State: Terminated OOMKilled, log: "java.lang.OutOfMemoryError"` |
| Symptom | `my pod restarts every few seconds after I deployed` |
| Error string | `Back-off pulling image "registry/app:v2"` |
| How-to | `how do I raise the memory limit on a deployment` |
| kubectl output | `STATUS OOMKilled RESTARTS 7` |

Prompt rules: write like a stressed on-call engineer, don't copy sentences from the chunk, answerable only from this chunk. JSON output. Cache every response to disk.

**Step 3: Filter.**

- Drop queries where >60% of query words appear in the chunk.
- Round-trip check with base `bge-base`: drop if source chunk not in its top 50.
- Deduplicate near-identical queries.
- Read 100 random pairs yourself; report the error rate in the README.

**Step 4: Mine hard negatives.** Base `bge-small` top 30; take a few from ranks 10–30 that aren't the positive; drop any scoring above 95% of the positive's score. `sentence_transformers.util.mine_hard_negatives` helps.

**Step 5: Build the test set by hand.** ~200 test queries, labels checked by hand, plus 30–50 of your own. Hand-map ~50 real Stack Overflow questions (mcipriano/stackoverflow-kubernetes-questions) to corpus chunks as the real-query slice.

**Output.** `train.jsonl` (anchor, positive, negative), `val.jsonl`, `test_queries.jsonl`, `test_qrels.jsonl`.

## Phase 3: Baseline evaluation

Goal: `evaluate.py` scores any model on the frozen test set. Run all baselines before training. If baselines are near-perfect, make queries harder first.

**Metrics.** Recall@1/5/10, MRR@10, NDCG@10. `InformationRetrievalEvaluator` for neural models, `rank_bm25` for BM25. Retrieve over the whole corpus.

| Model | Role |
| --- | --- |
| BM25 | Keyword baseline; strong on exact error strings |
| `all-MiniLM-L6-v2` | Popular small default |
| `bge-small-en-v1.5` | The model you will tune |
| `bge-base-en-v1.5` | The bigger model you want to beat |

Report per slice: incident snapshot, error string, real SO question, how-to.

**Done when** `results/baseline.csv` exists and the test set is frozen.

## Phase 4: Fine-tuning

Goal: tuned `bge-small` checkpoint trained on (query, positive, hard negative) triplets, selected on val.

| Setting | Value |
| --- | --- |
| Loss | `CachedMultipleNegativesRankingLoss` (mini-batch 16) |
| Batch size | 64 effective |
| Learning rate | 2e-5, linear warmup 10% |
| Epochs | 2 to 3 |
| Max sequence length | 256 |
| Batch sampler | `NO_DUPLICATES` |
| Eval | Val `InformationRetrievalEvaluator` every 200 steps, keep best by NDCG@10 |
| Seed | Fixed, logged |

**Query prefix.** BGE expects a short instruction before queries. One shared constant for training, eval and serving.

**Script outline.** Load `train.jsonl` into an HF `Dataset` (anchor/positive/negative) → load base model, set `max_seq_length` → loss + val evaluator + `SentenceTransformerTrainingArguments` → `SentenceTransformerTrainer` → log config, time, peak RAM, metrics to `results/runs.csv`.

**Expected cost.** ~5,000 triplets × 2 epochs on CPU: within an hour or two. Measure it.

## Phase 5: Evaluation, ablations and error analysis

**Main results table.** All baselines + tuned model + *tuned bge-small + BM25 hybrid (RRF)*, all metrics, per slice.

**Ablations (pick 3–4).** Hard negatives on/off · training size 25/50/100% · section-title prefix on/off · 1 vs 3 epochs · synthetic-only vs real queries.

**Error analysis.** 30 worst test queries, tagged: wrong label, ambiguous query, missing doc, chunk too long, true model miss. Put 2–3 examples in the README.

**Sanity checks.** 2–3 seeds, report spread. Forgetting check on a small general MTEB retrieval set.

**Done when** `results/final.csv`, ablation table and `ERROR_ANALYSIS.md` exist.

## Phase 6: Serving and OpsPilot integration

1. Export to ONNX with `optimum`, dynamic int8 quantization.
2. Re-run `evaluate.py` on the quantized model; report metric drop and latency gain.
3. Pre-compute corpus embeddings; save FAISS index.

| Endpoint | Input | Output |
| --- | --- | --- |
| `POST /search` | `query`, `k`, `mode` (dense or hybrid, default hybrid) | Top-k chunks with score, title, section, source path; or "no match" below calibrated threshold |
| `POST /embed` | list of texts | Vectors |
| `GET /health` | none | Model version, index size |

**OpsPilot wiring.** Register `search_runbooks(query)` as a Gemini tool; build the query from pod status, events and last log lines; cite the runbook section in the incident report; keep a switch to base `bge-small` for before/after demos.

**Agent eval.** 10–15 injected faults on a local `kind` cluster; compare no retrieval / base / tuned hybrid on correct-diagnosis rate, tool calls, time to diagnosis.

**Deployment.** Docker; ONNX Runtime + int8 only (AWS free tier ~1 GB RAM).

**Done when** OpsPilot answers a simulated CrashLoopBackOff incident using a chunk retrieved by the tuned model.

## Repo structure

```
runbook-retriever/
  data/
    raw/                 # cloned k8s docs + your runbooks
    corpus.jsonl
    splits/              # train / val / test, frozen
    cache/               # cached Gemini responses
  src/
    build_corpus.py      # Phase 1
    gen_queries.py       # Phase 2: generation
    filter_pairs.py      # Phase 2: filters + dedupe
    mine_negatives.py    # Phase 2: hard negatives
    evaluate.py          # Phase 3 + 5
    train.py             # Phase 4
    export_onnx.py       # Phase 6
  serve/
    app.py               # FastAPI
    Dockerfile
  results/
    baseline.csv
    runs.csv
    final.csv
  configs/train.yaml
  ERROR_ANALYSIS.md
  README.md
  Makefile
```

## Timeline and milestones (~4 weeks part-time)

| Week | Work | Gate to pass |
| --- | --- | --- |
| 1: Corpus | Clone k8s docs, write 15–25 runbooks, build corpus.jsonl, eval-harness skeleton | Corpus checked |
| 2: Data | Generate queries, filter, split, mine negatives, run baselines | Test set frozen |
| 3: Train | Fine-tune bge-small, ablations + seeds, error analysis | Beats base by 10+ pts Recall@5 |
| 4: Ship | ONNX + FastAPI, wire into OpsPilot, kind agent eval, README + HF card | OpsPilot demo works |

If the tuned model misses the 10-point gate, don't ship. Go back to Phase 2: harder queries, better negatives, cleaner labels.

- [ ] Corpus checked: 20 random chunks read cleanly
- [ ] Test set frozen and baselines logged
- [ ] Tuned model beats base `bge-small` by 10+ points Recall@5
- [ ] OpsPilot answers a simulated incident using the tuned retriever

## Risks and mitigations

| Risk | Sign | Fix |
| --- | --- | --- |
| Test leakage | Tuned scores near 100% | Split by `doc_id` before generating; hand-check test set |
| Synthetic queries too easy | Base model already very high | Overlap filter; hand-written and SO queries |
| False hard negatives | Loss stalls or metrics drop | Ranks 10–30 + 95% margin rule; spot-check 50 |
| Overfitting to generator style | Great on synthetic, weak on real | Report real-query slice separately; mix styles |
| Gemini rate limits | Generation stalls | Cache every call; batch chunks per prompt; run overnight |
| Slow CPU training | Many hours | Max length 192, fewer epochs, or one Kaggle run |
| Prefix mismatch | Serving worse than eval | One shared constant |
| Free-tier RAM too small | Container killed | ONNX int8, no PyTorch in serving image |

## Showcase

**README.** Lead with results table + one before/after query showing top-3 chunks from base vs tuned. Then reproduce steps, pipeline, ablations, error analysis, limits.

**HF model card.** Intended use, training data, metrics vs baselines, query prefix, limits.

**Resume bullets (fill with real numbers).**

- Fine-tuned `bge-small` (33M) embedding model on [N] synthetic and hand-verified Kubernetes incident queries with contrastive learning and mined hard negatives, improving Recall@5 from [X]% to [Y]% and beating a 3x larger `bge-base`.
- Built a leakage-safe data pipeline (LLM query generation, overlap and round-trip filtering, document-level splits) and ran ablations on hard negatives, data size and chunk titles.
- Served the model as an ONNX int8 FastAPI retrieval service ([Z] ms/query on CPU) powering OpsPilot's RAG layer; cut tool calls per diagnosis from [A] to [B] in a fault-injection eval.

**Stretch goals.** Matryoshka loss (128-dim) · cross-encoder reranker on top-20 · Gradio/Streamlit demo on HF Spaces · later: QLoRA tool-calling model for OpsPilot's agent.

## Sources

- [Komodor 2025 Enterprise Kubernetes Report announcement](https://komodor.com/blog/komodor-2025-enterprise-kubernetes-report-finds-nearly-80-of-production-outages/) (vendor report)
- [Auto-diagnosing Kubernetes alerts with HolmesGPT and CNCF tools](https://www.cncf.io/blog/2026/04/21/auto-diagnosing-kubernetes-alerts-with-holmesgpt-and-cncf-tools/), CNCF blog, STCLab SRE team
- [HolmesGPT custom runbooks example](https://github.com/HolmesGPT/holmesgpt/blob/master/examples/custom_runbooks.yaml)
- [ITBench-AA: Frontier Models Score Below 50%](https://huggingface.co/blog/ibm-research/itbench-aa)
- [Why Do AI Agents Systematically Fail at Cloud Root Cause Analysis?](https://arxiv.org/abs/2602.09937)
- [Flow-of-Action](https://arxiv.org/abs/2502.08224)
- [Fine-Tuning Embedding Models for Enterprise Retrieval](https://blogs.cisco.com/ai/fine-tuning-embedding-models-for-enterprise-retrieval-a-practical-guide-with-nvidia-nemotron-recipe), Cisco
- [Do We Need Domain-Specific Embedding Models?](https://arxiv.org/pdf/2409.18511)
- [NV-Retriever](https://arxiv.org/html/2407.15831)
- [Stack Overflow Kubernetes questions dataset](https://huggingface.co/datasets/mcipriano/stackoverflow-kubernetes-questions)
