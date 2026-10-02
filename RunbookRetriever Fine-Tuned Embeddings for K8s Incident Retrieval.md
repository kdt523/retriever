# RunbookRetriever — Fine-Tuned Embeddings for K8s Incident Retrieval

Oct 2, 2026 · @krushna datir

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

That last eval upgrades the resume line from "improved Recall@5" to "cut OpsPilot's tool calls per diagnosis from X to Y and raised correct diagnoses from A% to B%". That is the kind of result STCLab reported, and the kind teams care about.

## System architecture

The project has two halves: an offline pipeline you run once on your laptop to produce the tuned model, and an online path where OpsPilot calls that model on every incident.

&#91;embedded content: pipeline · 8 offline steps, 4 online steps\]

The fine-tune step is the core of the project. Everything before it builds the training data; everything after it proves and ships the result.

## Tech stack and environment

Everything runs on Windows 11 with 12 GB RAM and no GPU. Use WSL2 or plain Python 3.11 with a venv. The only paid or rate-limited piece is the LLM used to generate training queries.

| Layer | Choice | Why |
| --- | --- | --- |
| Base model | `BAAI/bge-small-en-v1.5` (33M, 384-dim) | Strong small retriever, trains on CPU |
| Comparison models | `all-MiniLM-L6-v2`, `bge-base-en-v1.5`, BM25 | Baselines for the results table |
| Training | `sentence-transformers` (v3+ Trainer API), PyTorch CPU | Built-in contrastive losses and IR evaluator |
| Query generation | Gemini 2.5 Flash API | Already your OpsPilot LLM; free tier is enough at this scale |
| Parsing and chunking | `markdown-it-py` or simple heading splitter, `tiktoken`-style token counts | K8s docs are Markdown |
| Vector index | FAISS (CPU) or Chroma | Simple, local, fast |
| Serving | FastAPI + ONNX Runtime (int8) via `optimum` | Fast CPU inference, small memory |
| Tracking | MLflow or a plain CSV results log | Every run's config and metrics saved |
| Model hosting | Hugging Face Hub | Public model card = proof of work |

**Memory budget.** Training `bge-small` at sequence length 256 and batch 32 fits comfortably in 12 GB. To get the benefit of large batches without more RAM, use `CachedMultipleNegativesRankingLoss` (gradient caching).

**If training feels slow,** time the first 50 steps and extrapolate. Fall back to a free Kaggle notebook only for the bigger ablations, not the main run.

## Phase 1: Build the corpus

Goal: about 1,500 to 3,000 clean, self-contained chunks of Kubernetes troubleshooting knowledge, each with its source and section title.

**Sources.**

1. Official Kubernetes docs from the `kubernetes/website` GitHub repo (`content/en/docs`). Focus on `tasks/debug`, `concepts/workloads`, `concepts/configuration`, `concepts/services-networking`, and `reference/kubectl`. Clone the repo; don't scrape the site.
2. Your own OpsPilot runbooks: one Markdown file per failure mode (CrashLoopBackOff, ImagePullBackOff, OOMKilled, Pending pods, failed readiness probes, node NotReady, DNS failures, PVC stuck, and so on). Write 15 to 25 of these. They double as OpsPilot content.
3. Optional: troubleshooting pages from Helm or ingress-nginx docs if OpsPilot will touch them.

**Chunking rules.**

- Split on Markdown headings first, then cap at about 300 tokens with a 50-token overlap.
- Prepend the page title and section heading to each chunk (`Debug Pods > My pod keeps crashing`). This alone improves retrieval.
- Strip Hugo shortcodes, front matter and navigation noise. Keep code blocks and kubectl output; they matter for error-string queries.
- Drop chunks under about 40 tokens.

**Output.** `data/corpus.jsonl`, one row per chunk: `chunk_id`, `doc_id`, `source_path`, `title`, `section`, `text`.

**Done when** you can print 20 random chunks and each one makes sense on its own.

## Phase 2: Training data

Goal: about 4,000 to 6,000 (query, positive chunk) training pairs, a hand-verified test set of about 200 queries, and mined hard negatives. Data quality decides the result more than any hyperparameter.

**Step 1: Split by document first.** Assign whole `doc_id`s to train (80%), validation (10%) and test (10%) before generating anything. If chunks from one page land in both train and test, your scores will be inflated.

**Step 2: Generate queries with Gemini.** For each chunk, ask for 3 queries in different styles:

| Style | Example |
| --- | --- |
| Symptom | `my pod restarts every few seconds after I deployed` |
| Error string | `Back-off pulling image "registry/app:v2"` |
| How-to | `how do I raise the memory limit on a deployment` |
| kubectl output | `STATUS OOMKilled RESTARTS 7` |

Prompt rules: write like a stressed on-call engineer, don't copy sentences from the chunk, answerable only from this chunk. Ask for JSON output. Cache every response to disk so reruns cost nothing.

**Step 3: Filter.**

- Drop queries with high word overlap with their chunk (for example, more than 60% of query words appear in the chunk). Those are too easy and teach nothing.
- Round-trip check: embed the query with base `bge-base`. If the source chunk is not in its top 50, the query is probably vague or wrong. Drop it.
- Deduplicate near-identical queries.
- Read 100 random pairs yourself and record the error rate. Report it in the README.

**Step 4: Mine hard negatives.** For each training query, use base `bge-small` to retrieve the top 30 chunks. Take a few chunks ranked 10 to 30 that are not the positive as hard negatives. Skip the top few because they may be correct answers too (false negatives). `sentence_transformers.util.mine_hard_negatives` does this.

**Step 5: Build the test set by hand.** Take about 200 test queries, check each label yourself, and write 30 to 50 of your own realistic queries. Optional: add real Kubernetes questions from Stack Overflow, mapped to the right chunk. Real queries make the result far more convincing than synthetic ones alone.

**Output.** `train.jsonl` (anchor, positive, negative), `val.jsonl`, `test_queries.jsonl`, `test_qrels.jsonl`.

## Phase 3: Baseline evaluation

Goal: one script, `evaluate.py`, that scores any model on the frozen test set. Run it on every baseline before touching training. If the baselines are already near-perfect, the task is too easy, so make the queries harder first.

**Metrics.** Recall@1, Recall@5, Recall@10, MRR@10 and NDCG@10. Use `InformationRetrievalEvaluator` from sentence-transformers for the neural models and `rank_bm25` for BM25. Retrieval runs over the whole corpus, not just the test documents.

**Baselines to run.**

| Model | Role in the story |
| --- | --- |
| BM25 | Keyword baseline; strong on exact error strings |
| `all-MiniLM-L6-v2` | Popular small default |
| `bge-small-en-v1.5` | The model you will tune |
| `bge-base-en-v1.5` | The bigger model you want to beat |

Also report results per query style (symptom, error string, how-to, kubectl output). This shows where the base model fails, which is your justification for fine-tuning.

**Done when** `results/baseline.csv` exists and the test set is frozen. Never edit the test set after this point.

## Phase 4: Fine-tuning

Goal: a tuned `bge-small` checkpoint trained with contrastive loss on (query, positive, hard negative) triplets, selected on the validation set.

**How it learns.** Multiple Negatives Ranking Loss pulls each query toward its positive chunk and pushes it away from every other chunk in the batch, plus its hard negative. Bigger batches give more negatives, which is why the cached version of the loss helps on a laptop.

**Starting config.**

| Setting | Value |
| --- | --- |
| Loss | `CachedMultipleNegativesRankingLoss` (mini-batch 16) |
| Batch size | 64 (effective, via caching) |
| Learning rate | 2e-5, linear warmup 10% |
| Epochs | 2 to 3 |
| Max sequence length | 256 |
| Batch sampler | `NO_DUPLICATES` (no repeated texts in a batch) |
| Eval | Validation `InformationRetrievalEvaluator` every 200 steps, keep the best checkpoint by NDCG@10 |
| Seed | Fixed, logged with the run |

**Query prefix.** BGE models expect a short instruction in front of queries for retrieval. Use the same prefix in training, evaluation and serving, or results will silently drop.

**Training script outline.**

1. Load `train.jsonl` into a Hugging Face `Dataset` with `anchor`, `positive`, `negative` columns.
2. Load the base model, set `max_seq_length`.
3. Build the loss, the validation evaluator and `SentenceTransformerTrainingArguments`.
4. Train with `SentenceTransformerTrainer`, saving the best checkpoint.
5. Log config, wall-clock time, peak RAM and final metrics to `results/runs.csv`.

**Expected cost.** About 5,000 triplets for 2 epochs on CPU should finish within an hour or two. Measure it; don't guess.

## Phase 5: Evaluation, ablations and error analysis

Goal: a results table and a short write-up that prove the fine-tune helped and explain why. This is what interviewers will ask about.

**Main results table.** Every baseline from Phase 3 plus the tuned model, on the frozen test set, with all five metrics. Add one row for *tuned `bge-small` + BM25 hybrid* (combine scores with reciprocal rank fusion). Hybrid often wins on exact error strings.

**Ablations (pick 3 or 4).**

- No hard negatives versus with hard negatives.
- Training set size: 25%, 50%, 100% of pairs. Shows how much data you actually need.
- No section-title prefix on chunks versus with it.
- 1 versus 3 epochs, to check for overfitting.
- Synthetic-only test queries versus your hand-written and real queries.

**Error analysis.** Pull the 30 worst test queries for the tuned model and tag each failure: wrong label, ambiguous query, missing doc, chunk too long, or a true model miss. Two or three concrete examples in the README are worth more than another metric.

**Sanity checks.**

- Run 2 or 3 seeds for the main run and report the spread.
- Check the tuned model on a general benchmark task (a small MTEB retrieval set) to show it did not forget general English. A small drop is fine; say so honestly.

**Done when** `results/final.csv`, the ablation table and `ERROR_ANALYSIS.md` exist.

## Phase 6: Serving and OpsPilot integration

Goal: a small FastAPI service that OpsPilot calls as a tool, running the tuned model in ONNX int8 on CPU.

**Export and shrink.**

1. Export the tuned model to ONNX with `optimum` and apply dynamic int8 quantization.
2. Re-run `evaluate.py` on the quantized model. Report the metric drop (should be small) and the latency gain.
3. Pre-compute corpus embeddings once and save the FAISS index to disk.

**API.**

| Endpoint | Input | Output |
| --- | --- | --- |
| `POST /search` | `query`, `k`, `mode` (dense or hybrid) | Top-k chunks with score, title, section, source path |
| `POST /embed` | list of texts | Vectors (for re-indexing) |
| `GET /health` | none | Model version, index size |

**OpsPilot wiring.**

- Register `search_runbooks(query)` as a tool for the Gemini agent. When OpsPilot sees a failing pod, it builds a query from pod status, events and the last log lines, calls the tool, and grounds its diagnosis in the returned chunks.
- Show the cited runbook section in OpsPilot's incident report so users can verify the answer.
- Keep a switch to call base `bge-small` instead, so you can demo before and after on the same incident.

**Deployment.** Containerize with Docker. AWS free-tier instances have about 1 GB RAM, so use the int8 ONNX model and ONNX Runtime only, not full PyTorch, in the serving image.

**Done when** OpsPilot answers a simulated CrashLoopBackOff incident using a chunk retrieved by your tuned model.

## Repo structure

One repo, one script per phase, so anyone can reproduce the results table from scratch with `make all`.

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

## Timeline and milestones

Plan on about four weeks at a part-time pace around classes and placement prep. Phase 3 (the eval harness) starts in week 1 alongside the corpus so it is ready the moment data exists.

&#91;embedded content: roadmap · 4 weeks, 4 gates\]

If the tuned model misses the 10-point gate, don't ship yet. Go back to Phase 2: harder queries, better negatives, cleaner labels.

- [ ] Corpus checked: 20 random chunks read cleanly
- [ ] Test set frozen and baselines logged
- [ ] Tuned model beats base `bge-small` by 10+ points Recall@5
- [ ] OpsPilot answers a simulated incident using the tuned retriever

## Risks and mitigations

| Risk | Sign | Fix |
| --- | --- | --- |
| Test leakage | Tuned scores look too good (near 100%) | Split by `doc_id` before generating; hand-check the test set |
| Synthetic queries too easy | Base model already scores very high | Add the overlap filter; add hand-written and Stack Overflow queries |
| False hard negatives | Training loss stalls or metrics drop | Mine from ranks 10 to 30, not the top; spot-check 50 negatives |
| Overfitting to the generator's style | Great on synthetic test, weak on real queries | Report the real-query slice separately; mix query styles |
| Gemini rate limits | Generation stalls | Cache every call; batch several chunks per prompt; run overnight |
| Slow CPU training | Run takes many hours | Shorter max length (192), fewer epochs, or one Kaggle run for ablations |
| Prefix mismatch | Serving results worse than eval | One shared constant for the query prefix used everywhere |
| Free-tier RAM too small | Container killed on AWS | ONNX int8, no PyTorch in the serving image |

## Showcase

The project is only as strong as how clearly you show the before and after. Ship these three things.

**README.** Lead with the results table and one before/after example query showing the top-3 chunks from the base and tuned models. Then cover how to reproduce it, the data pipeline, the ablations, the error analysis and the limits.

**Hugging Face model card.** Publish the tuned model with its intended use, training data description, metrics versus baselines, the query prefix, and known limits.

**Resume bullets (fill the brackets with your real numbers).**

- Fine-tuned `bge-small` (33M) embedding model on \[N\] synthetic and hand-verified Kubernetes incident queries with contrastive learning and mined hard negatives, improving Recall@5 from \[X\]% to \[Y\]% and beating a 3x larger `bge-base`.
- Built a leakage-safe data pipeline (LLM query generation, overlap and round-trip filtering, document-level splits) and ran ablations on hard negatives, data size and chunk titles.
- Served the model as an ONNX int8 FastAPI retrieval service (\[Z\] ms per query on CPU) powering the RAG layer of OpsPilot, a Kubernetes incident-response agent.

**Stretch goals (only after the core is done).**

- Matryoshka loss so embeddings can be cut to 128 dims with little quality loss.
- Fine-tune a small cross-encoder reranker on the same pairs and rerank the top 20.
- Small Gradio or Streamlit demo on Hugging Face Spaces: type a symptom, compare base versus tuned results side by side.
- Later: the QLoRA tool-calling idea for OpsPilot's agent, built on top of this retriever.

## Sources

- [Komodor 2025 Enterprise Kubernetes Report announcement](https://komodor.com/blog/komodor-2025-enterprise-kubernetes-report-finds-nearly-80-of-production-outages/) (vendor report)
- [Auto-diagnosing Kubernetes alerts with HolmesGPT and CNCF tools](https://www.cncf.io/blog/2026/04/21/auto-diagnosing-kubernetes-alerts-with-holmesgpt-and-cncf-tools/), CNCF blog, STCLab SRE team
- [HolmesGPT custom runbooks example](https://github.com/HolmesGPT/holmesgpt/blob/master/examples/custom_runbooks.yaml)
- [ITBench-AA: Frontier Models Score Below 50%](https://huggingface.co/blog/ibm-research/itbench-aa), IBM Research and Artificial Analysis
- [Why Do AI Agents Systematically Fail at Cloud Root Cause Analysis?](https://arxiv.org/abs/2602.09937)
- [Flow-of-Action: SOP enhanced LLM-based multi-agent system for RCA](https://arxiv.org/abs/2502.08224)
- [Fine-Tuning Embedding Models for Enterprise Retrieval](https://blogs.cisco.com/ai/fine-tuning-embedding-models-for-enterprise-retrieval-a-practical-guide-with-nvidia-nemotron-recipe), Cisco
- [Do We Need Domain-Specific Embedding Models?](https://arxiv.org/pdf/2409.18511)
- [NV-Retriever: effective hard-negative mining](https://arxiv.org/html/2407.15831)
- [Stack Overflow Kubernetes questions dataset](https://huggingface.co/datasets/mcipriano/stackoverflow-kubernetes-questions)
