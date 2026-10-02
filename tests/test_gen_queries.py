from __future__ import annotations

import json

from runbook_retriever.corpus import Chunk
from runbook_retriever.gen_queries import (
    Batch,
    is_eligible,
    make_batches,
    parse_response,
    randomize_names,
)


def chunk(cid: str, text: str = "word " * 60, source: str = "k8s_docs") -> Chunk:
    doc = cid.split("#")[0]
    return Chunk(
        chunk_id=cid, doc_id=doc, source=source, source_path="x", url=None,  # type: ignore[arg-type]
        title="T", section="S", text=text, n_tokens=100,
    )  # fmt: skip


def test_eligibility_skips_code_dumps_and_tiny_chunks() -> None:
    assert is_eligible(chunk("a#000"))
    code = "intro line\n\n```yaml\n" + "key: value\n" * 80 + "```"
    assert not is_eligible(chunk("a#001", text=code))
    assert not is_eligible(chunk("a#002", text="too short"))


def test_batches_never_mix_splits_and_put_test_first() -> None:
    chunks = [chunk(f"k8s/d{i}#000") for i in range(5)] + [chunk("runbook/r#000", source="runbook")]
    splits = {"k8s/d0": "train", "k8s/d1": "test", "k8s/d2": "val", "k8s/d3": "train",
              "k8s/d4": "test", "runbook/r": "test"}  # fmt: skip
    batches = make_batches(chunks, splits)  # type: ignore[arg-type]
    assert [b.split for b in batches] == ["test", "val", "train"]
    assert batches[0].chunks[0].chunk_id == "runbook/r#000"  # runbooks first within a split
    assert all(len({splits[c.doc_id] for c in b.chunks}) == 1 for b in batches)


def test_parse_drops_only_the_bad_query() -> None:
    batch = Batch("train", (chunk("k8s/a#000"), chunk("k8s/b#000")))
    text = json.dumps({"results": [
        {"passage": 1, "suitable": True, "queries": [
            {"style": "symptom", "query": "pods keep restarting after deploy"},
            {"style": "how_to", "query": "x" * 900},  # too long: dropped alone
            {"style": "made_up_style", "query": "bad style is dropped"},
        ]},
        {"passage": 2, "suitable": False, "queries": [{"style": "how_to", "query": "ignored query"}]},
        {"passage": 9, "suitable": True, "queries": [{"style": "how_to", "query": "out of range"}]},
    ]})  # fmt: skip
    rows = list(parse_response(text, batch))
    assert [r["query"] for r in rows] == ["pods keep restarting after deploy"]
    assert rows[0]["chunk_id"] == "k8s/a#000" and rows[0]["split"] == "train"


def test_parse_survives_garbage() -> None:
    assert list(parse_response("not json at all", Batch("train", (chunk("k8s/a#000"),)))) == []


def test_randomize_names_is_consistent_and_deterministic() -> None:
    q = "cart-7f9c6d5b84-qz2lp 0/1 Error | pod cart-7f9c6d5b84-qz2lp_prod(uid) backoff"
    out = randomize_names(q)
    assert out == randomize_names(q)
    assert "7f9c6d5b84" not in out and "qz2lp" not in out
    new_pod = out.split()[0]
    assert f"{new_pod}_prod(uid)" in out
    assert (
        randomize_names("image app:v2-20240101 in kube-system")
        == "image app:v2-20240101 in kube-system"
    )
