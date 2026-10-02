# Labeling instructions

You are labeling evaluation data for **RunbookRetriever**, a search engine for Kubernetes
incidents. Your labels decide which questions go into the frozen test set that every model is
scored on, so accuracy matters far more than speed. Be strict and consistent.

## The project

When something breaks in a Kubernetes cluster, an on-call engineer types what they see (an
error string, a `kubectl get pods` line, a symptom, or a how-to question) and the search engine
must return the passage that helps them. The searchable corpus is about 3,300 **chunks**:
sections of the official Kubernetes documentation (ids starting `k8s/`) and of 35 hand-written
incident runbooks (ids starting `runbook/`). Each chunk shows `Page title > Section` and its text.

The questions you will judge were mostly **written by another AI (Gemini)** from one chunk,
so some are wrong, too vague, or answered better by a different chunk. Your job is to catch
that. Some batches contain real Stack Overflow questions instead.

## What "answers the query" means

A chunk **answers** a query when an engineer who asked it would find, in that chunk, what they
need: the explanation of the error or behaviour, the likely cause, the check to run, or the
steps to do what they asked. Use this one standard for every task.

- It is enough to address the *core* of the query; it need not cover every detail.
- It is **not** enough to share keywords or the general topic. A chunk about PersistentVolume
  node affinity does not answer a question about Pod node affinity.
- A chunk that only *mentions* the error in passing, or answers a neighbouring question, does
  not answer it.
- Judge only the text shown. Do not assume content the chunk does not contain, and do not
  reward a chunk for being from the "right" page if the shown section is about something else.
- Specific names in queries (pod names, namespaces, images like `cart-7d9f8b6c4-x2k9p`) are
  realistic placeholders. Ignore them when judging.

## The four tasks

Each batch file says which task it is. Items look like `<item id="...">` blocks.

### `test_pairs`: verify a test question
You see a `<query>`, the `<labeled_chunk>` it was generated from, and up to 5 other
`<candidate letter="A">` chunks.
- `verdict`:
  - `"correct"`: the labeled chunk answers the query.
  - `"wrong"`: it does not (different problem, only topically related, or the query asks for
    something the chunk does not contain).
  - `"ambiguous"`: the query is too vague to have a clear answer (e.g. "pod not working"), is
    not a realistic thing an engineer would type, or is garbled.
- `also_relevant`: letters of the other candidates that **on their own** also answer the query
  by the same standard. Usually empty or one or two letters. Use `[]` when the verdict is not
  `"correct"`.

### `so_questions`: map a real Stack Overflow question
You see the full `<question>` and 10 `<candidate>` chunks found by a search engine.
- `relevant`: letters of every candidate that substantially helps answer the question's main
  problem. Use `[]` when none does. Many questions are out of scope (cloud-provider specifics,
  third-party tools, application bugs); `[]` is a valid and useful answer, never forced.

### `train_audit`: check a training pair
You see a `<query>` and its `<chunk>`.
- `verdict`: `"correct"` if the chunk answers the query, otherwise `"wrong"` (including queries
  that are too vague or unrealistic). This measures the error rate of the training data.

### `negatives_audit`: check a "hard negative"
You see a `<query>`, its `<positive_chunk>` (the answer), and a `<negative_chunk>` that was
picked automatically as a similar-looking *wrong* answer.
- `verdict`:
  - `"true_negative"`: the negative chunk does **not** answer the query. Being on a similar
    topic is fine and expected.
  - `"false_negative"`: the negative chunk **also** answers the query by the standard above,
    so it was wrongly treated as a wrong answer.

## Output format (follow exactly)

Reply with **one** code block tagged `jsonl` and nothing else after it. One line per item, in
the same order as the items, covering **every** item in the batch. Copy each `id` exactly.
Keep `reason` under 15 words: the deciding fact, not a summary.

```jsonl
{"id": "0000000000000001", "verdict": "correct", "also_relevant": ["B"], "reason": "explains NXDOMAIN from wrong service name and how to check it"}
{"id": "0000000000000002", "relevant": [], "reason": "Kafka Helm chart vs operator choice; no chunk covers it"}
{"id": "0000000000000003", "verdict": "wrong", "reason": "chunk covers liveness probes; query is a startup probe failure"}
{"id": "0000000000000004", "verdict": "true_negative", "reason": "negative sets privileged mode, does not show how to verify it"}
```

Fields per task:

| Task | Fields |
| --- | --- |
| `test_pairs` | `id`, `verdict` (`correct` / `wrong` / `ambiguous`), `also_relevant` (letters), `reason` |
| `so_questions` | `id`, `relevant` (letters, may be empty), `reason` |
| `train_audit` | `id`, `verdict` (`correct` / `wrong`), `reason` |
| `negatives_audit` | `id`, `verdict` (`true_negative` / `false_negative`), `reason` |

Before answering, read every item fully. When unsure between two options, choose the stricter
one: `wrong` over `correct`, `ambiguous` over a guess, fewer letters over more.
