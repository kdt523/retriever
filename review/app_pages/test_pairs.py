from typing import Any

import streamlit as st
from common import advance, nav_bar, require_queue, show_chunk, show_query, store

from runbook_retriever.labeling import Task

TASK: Task = "test_pairs"
items = require_queue(TASK)
i = nav_bar(TASK, items)
if i >= len(items):
    st.success("Every test pair is labeled.", icon=":material/task_alt:")
    st.stop()
item = items[i]


def extra_key(item_id: str, chunk_id: str) -> str:
    return f"extra::{item_id}::{chunk_id}"


def save(item: dict[str, Any], verdict: str) -> None:
    extras = [c for c in item["candidates"] if st.session_state.get(extra_key(item["id"], c))]
    store(TASK).put(
        item["id"],
        {
            "verdict": verdict,
            "query": item["query"],
            "chunk_id": item["chunk_id"],
            "also_relevant": extras,
        },
    )
    advance(TASK, items)


existing = store(TASK).get(item["id"]) or {}
for cid in item["candidates"]:
    st.session_state.setdefault(
        extra_key(item["id"], cid), cid in existing.get("also_relevant", [])
    )

st.caption(f"Style **{item['style']}** · source {item['source']}")
show_query(item["query"])

st.markdown("**Labeled chunk.** Does it answer the query?")
show_chunk(item["chunk_id"])
with st.container(horizontal=True):
    st.button(
        "Correct",
        key="v_correct",
        shortcut="1",
        type="primary",
        icon=":material/check:",
        on_click=save,
        args=(item, "correct"),
    )
    st.button(
        "Wrong",
        key="v_wrong",
        shortcut="2",
        icon=":material/close:",
        on_click=save,
        args=(item, "wrong"),
    )
    st.button(
        "Ambiguous",
        key="v_ambiguous",
        shortcut="3",
        icon=":material/help:",
        on_click=save,
        args=(item, "ambiguous"),
    )

st.markdown("**Other candidates.** Tick any that also answer the query; saved with the verdict.")
for cid in item["candidates"]:
    with st.container(border=True):
        st.checkbox(f"`{cid}` also answers the query", key=extra_key(item["id"], cid))
        with st.expander("Show chunk"):
            show_chunk(cid, border=False)
