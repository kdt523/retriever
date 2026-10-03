# Decision log

Short records of choices not spelled out in [PLAN.md](PLAN.md). Newest last.

## D1: Python 3.12 + uv instead of 3.11 + venv (2026-10-02)
`uv.lock` pins every dependency, so anyone can reproduce the results table exactly.
3.12 is fully supported by torch and sentence-transformers.

## D2: Train on the local GPU (2026-10-02)
The laptop has an RTX 3050 (4 GB). bge-small trains in fp16 with `CachedMultipleNegativesRankingLoss`
within that budget, so seeds and ablations run locally; Kaggle is a fallback only.

## D3: Library package + per-phase modules (2026-10-02)
PLAN.md lists flat scripts in `src/`. They live in `src/runbook_retriever/` instead and run as
`python -m runbook_retriever.<phase>`, so shared code (config, cache, run log) is importable and
unit-testable. Make targets hide the module paths.

## D4: Chunks are capped in model tokens (2026-10-02)
PLAN.md caps chunks at ~300 tokens but trains with `max_seq_length=256`, which would truncate
chunks silently. The full chunk (title + section + text) is capped at `MAX_SEQ_LENGTH`
model tokens, counted with the bge tokenizer.

## D5: LLM cache key excludes the model name (2026-10-02)
If the fallback model answered a prompt, reruns reuse that answer instead of spending quota.
The model that answered is stored in each cache entry and can be reported per query.

## D6: Corpus scope and size (2026-10-02)
kubernetes/website pinned at `7a1c866f`. Included: debugging tasks, pod/container configuration,
workloads, configuration, containers, services/networking, scheduling/eviction, storage, nodes,
jobs, the hand-written kubectl reference pages, and the DNS debugging page. Excluded: generated
kubectl command pages (mostly flag tables). Result: 3,292 chunks (above PLAN's 1,500-3,000).
Kept in full because a larger search space makes retrieval harder and the evaluation more honest;
Phase 2 can generate queries for a subset to stay inside Gemini quotas.

## D7: 27 runbooks with a fixed shape (2026-10-02)
One file per failure mode in `runbooks/`, YAML front matter (title, scope, tools, cautions,
related) plus sections Symptoms / Checks / Likely causes / Fix / Rollback / escalation, validated
by `runbooks.py` and a test. 27 (not 15-25) so the runbook stratum still has several documents
in val and test after the doc-level split. Front matter is stored in the chunk's `meta` and is
not embedded.

## D8: Short sections are merged, not dropped (2026-10-02)
PLAN says drop chunks under ~40 tokens. Short sections are instead folded into the next section
(with their heading as a lead-in line), so intro paragraphs and short troubleshooting tips survive.
A document is dropped only if all of it is under the minimum.

## D9: Code-heavy chunks stay in the corpus (2026-10-02)
Long manifests and command output split into chunks that are mostly YAML. They stay in the
corpus (they are realistic distractors and carry exact identifiers), but Phase 2 should skip
query generation for chunks that are almost entirely code.

## D10: Runbooks verified against a real cluster (2026-10-02)
`make cluster-up faults` injects 36 failures into a throwaway k3d cluster (k3s v1.35.5) and
records what Kubernetes really prints to `data/incidents/` (committed). A scenario only counts
as captured when its `expect` patterns appear in the real output. Runbook symptom text was
corrected against these captures; notable differences from commonly documented behaviour:
- crash loops show `STATUS Error` between restarts, not only `CrashLoopBackOff`;
- scheduler messages now append `no new claims to deallocate, preemption: ...`, and the
  insufficient-resources case says `Preemption is not helpful for scheduling`;
- the volume zone/node conflict now reads `didn't match PersistentVolume's node affinity`;
- NetworkPolicy blocks surface as `Connection refused` on kube-router (k3s) but as timeouts on
  Calico/Cilium, so the runbook no longer claims "always a timeout";
- Python on Alpine reports unknown hosts as `gaierror(-3, 'Try again')`;
- evicted pods can show `ContainerStatusUnknown` with exit code 137.
5 runbooks cannot be reproduced locally (metrics-, cert-manager-, ingress- or Helm-dependent);
they are listed with reasons in `faults/_unverified.yaml`, and a test enforces that every
runbook is either verified or listed there.

## D11: Leakage guard between captures and runbooks (2026-10-02)
Captures will serve as real "incident snapshot" test queries in Phase 2. Runbooks therefore use
the real Kubernetes message formats but different identifiers (pod names, IPs, ConfigMap names,
app log lines). `tests/test_fault_capture.py::test_runbooks_do_not_copy_capture_identifiers`
fails if any scenario-specific string appears in a runbook.

## D12: 35 runbooks (2026-10-02)
Added resource-quota-exceeded, rbac-forbidden, admission-denied, pdb-blocking-drain,
loadbalancer-pending, volume-node-affinity-conflict, statefulset-rollout-stuck and
helm-upgrade-failed to cover common production failures beyond pod crashes.
Corpus is now 3,340 chunks (165 from runbooks).

## D13: Document splits stratified by source (2026-10-02)
`make splits` shuffles sorted doc_ids with the project seed, separately for k8s docs and
runbooks, and cuts 80/10/10 with at least 3 documents in val and test per stratum. Result:
k8s 157/20/20 docs, runbooks 27/4/4. Frozen in `data/splits/doc_splits.json` before any query
existed; the script refuses to overwrite it.

## D14: Gemini free tier forced a model chain (2026-10-02)
In practice this key's free tier allows 20 `gemini-2.5-flash` requests per day, and
`gemini-2.5-flash-lite` is no longer offered to new users. Generation uses a chain
(`RR_GEMINI_MODELS`): gemini-3.5-flash-lite -> gemini-3.1-flash-lite -> gemini-2.5-flash. Each
model has its own daily quota. A 429 that asks to retry in more than 5 minutes is treated as an
exhausted daily quota and trips that model for the run (no wasted retries); a 404 trips it too.
The cache key excludes the model, and each query records which model wrote it. Prompt quality
was piloted on both runbook and k8s-doc batches before the full run (prompt v3).

## D15: Query generation rules (2026-10-02)
3 queries per chunk in different styles (incident_snapshot, symptom, error_string, how_to,
kubectl_output), batches of 8 chunks from one split, JSON schema output validated per query
(one bad query never discards a batch). Chunks that are >80% code or have <120 prose chars are
skipped (D9). The prompt forbids invented error messages and placeholder names. Generated
pod/ReplicaSet names get fresh hashes from Kubernetes' own alphabet, consistently within a
query, because LLMs reuse a few hashes and those would become a spurious shared feature.

## D16: Pair filters (2026-10-02)
Dropped in order: exact duplicates; the same query generated for different chunks (ambiguous
label); word overlap with the passage above a per-style cap (incident_snapshot 0.6,
symptom 0.75, how_to 0.9; none for error_string and kubectl_output, which quote text on
purpose); cosine > 0.95 to an earlier query of the same chunk; source chunk
not in base bge-base top 50 (round trip). Every dropped row keeps its reason in
`data/queries/filtered.jsonl`; counts in `results/filter_stats.json`.

The first run used 0.6 for all prose styles and dropped 59% of how-to questions; sampled
drops at 0.6-0.9 were realistic ("how to configure dnsConfig when dnsPolicy is None"), since
how-to questions reuse API vocabulary. Caps were relaxed rather than losing ~40% of the data.
Test difficulty is guarded instead by the stored `overlap` (a low-overlap slice is reported in
Phase 3) and by the real-incident, Stack Overflow and handwritten slices.

## D17: Hard negatives are split-aware and positive-aware (2026-10-02)
Own implementation instead of `mine_hard_negatives`: negatives come only from train-split
chunks (no val/test text enters training), never from the positive's neighbouring chunks
(40-token overlap), only from base bge-small ranks 10-30 (fallback 31-60), and never scoring
above 95% of the positive. Up to 3 are stored per pair for n-tuple experiments.

## D18: Evaluation set composition (2026-10-02)
Test slices: generated queries whose pair was labeled correct (per style; who labeled is in D20); real cluster incident
snapshots, split into `real_incident_heldout` (runbook in val/test) and `real_incident_seen`
(runbook in train: unseen query, seen document); hand-mapped Stack Overflow questions; optional
hand-written queries. Incident relevance is document-level (every chunk of the scenario's
runbook, plus `also_relevant` runbooks that directly address the visible symptom). SO questions
with no match become out-of-scope sets, split 50/50 into calibration (val) and reporting (test)
for the "no runbook matches" threshold. `data/splits/MANIFEST.json` stores sha256 of every frozen
file and a test fails if any changes.

## D19: Metrics and known evaluation biases (2026-10-02)
Retrieval is over the whole corpus (3,340 chunks). Reported: hit@1/5/10 (at least one
relevant chunk in the top k; equals recall@k when one chunk is relevant), MRR@10 and binary
NDCG@10, per slice plus `all` and `low_overlap` (generated queries sharing at most half their
content words with the positive: the hardest synthetic ones). Fractional recall is not used:
incident queries count every chunk of the right runbook as relevant, so it would punish a
retriever for not returning the whole runbook. For the same reason NDCG understates
real-incident slices; read hit@k and MRR there. Known bias: generated val/test queries passed a
bge-base round trip (D16), so bge-base is slightly favoured on generated slices; the
real-incident, Stack Overflow and handwritten slices are free of it. `make baseline` refuses to
run unless every frozen file matches MANIFEST.json.

## D20: Claude-assisted labels with a blind human spot check (2026-10-03)
All four review queues (220 test pairs, 150 Stack Overflow questions, 100 train-audit pairs,
50 hard negatives) were labeled by Claude from `docs/LABELING_PROMPT.md` (`make label-export`,
answers in `data/llm_labeling/answers/`, `make label-import`). A human then labeled a random
sample of 30 test pairs blind, without seeing Claude's verdict (`make label-spot-check`, Spot
check page). Agreement was 24/30 (0.8, `results/label_agreement.json`); all six disagreements
were borderline (bare output with no question, or partial topical coverage), not clear errors.
At freeze the human verdict replaces Claude's on every spot-checked item, and
`MANIFEST.json` records how many labels came from each labeler. Consequence: the test set is
Claude-labeled with a human audit, not fully human-labeled; treat differences of a few points on
small slices (incident_snapshot n=4, real_incident_heldout n=10) as noise. The train audit found
19/100 wrong pairs, an estimate of label noise in training data, not something fixed by hand.

## D21: Fine-tuning setup (2026-10-03)
`make train` (`src/runbook_retriever/train.py`, `configs/train.yaml`) fine-tunes bge-small on the
4,634 train triplets with CachedMultipleNegativesRankingLoss (batch 64, mini-batch 16, so every
other positive and hard negative in the batch is a negative), lr 2e-5, 10% warmup, 3 epochs,
fp16 on the RTX 3050, `NO_DUPLICATES` sampler, seed from `RR_SEED`. Deviations from PLAN.md:
- Training uses the GPU (peak ~1.4 GB VRAM, ~2 s per step), not the CPU the plan assumed.
- Evaluation every 25 steps instead of 200: an epoch is only ~73 steps at batch 64.
- The 617 train pairs with no surviving hard negative are left out, so every batch has the same
  three columns; the hard-negative ablation in Phase 5 can use all pairs.
- The query instruction is passed as the trainer's `anchor` prompt and to the val evaluator,
  both from `QUERY_PREFIX`, so training, evaluation and serving share one constant.
Model selection uses only the frozen val set (whole corpus, 715 queries); the best checkpoint by
val NDCG@10 is saved to `models/bge-small-rr/` with `train_meta.json` (config, seed, git sha,
train-file sha256, val curve). The test set is first scored in Phase 5. Corpus embeddings for
local model directories are cached by file size and mtime, so retraining into the same directory
cannot reuse stale vectors.

## D22: Phase 5 findings and limits (2026-10-03)
Main results and ablations are in the README and `results/` (`final.csv`, `ablations_*.csv`,
`ablations.md`, `error_analysis.md`). The ablation models were chosen before looking at test and
are all reported, so the test numbers are not selected on. Findings that change later work:
- Hard negatives gave no measurable gain (D17 mining is kept, but not required for the result).
- The test gain over untrained bge-small is +5.5 hit@5, below the +10 target; val showed +11.
  The test set mixes in Stack Overflow questions and real incidents, which the synthetic train
  queries match less well. Real-query slices are where more training data would help most.
- Two test pairs are wrong labels (`gen/bb141ad982ce4819`, `gen/289a87657a28a681`), found in the
  error analysis, plus nine queries where the qrels miss an equally good chunk. The frozen test
  files are not edited (the manifest guards them); this is stated here instead. A corrected set
  would be a new, versioned freeze.
- `make evaluate` writes `results/final.csv` and the worst-30 report; `make ablate` retrains the
  six variants (about 50 minutes on the RTX 3050) and `python -m runbook_retriever.ablation_report`
  rebuilds `results/ablations.md` from the two ablation CSVs.
