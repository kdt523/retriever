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
