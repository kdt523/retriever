from typing import Any

import streamlit as st
from common import advance, nav_bar, require_queue, safe_md, show_chunk, store

from runbook_retriever.labeling import Task

TASK: Task = "so_questions"
items = require_queue(TASK)
i = nav_bar(TASK, items)
if i >= len(items):
    st.success("Every question is labeled.", icon=":material/task_alt:")
    st.stop()
item = items[i]


def pick_key(item_id: str, chunk_id: str) -> str:
    return f"so::{item_id}::{chunk_id}"


def save(item: dict[str, Any], no_match: bool) -> None:
    chosen = (
        []
        if no_match
        else [c for c in item["candidates"] if st.session_state.get(pick_key(item["id"], c))]
    )
    if not no_match and not chosen:
        st.toast("Tick at least one chunk, or press No match.", icon=":material/warning:")
        return
    store(TASK).put(
        item["id"],
        {
            "relevant": chosen,
            "query": item["query"],
            "dataset_row": item["dataset_row"],
            "author": item["author"],
        },
    )
    advance(TASK, items)


existing = store(TASK).get(item["id"]) or {}
for cid in item["candidates"]:
    st.session_state.setdefault(pick_key(item["id"], cid), cid in existing.get("relevant", []))

with st.container(border=True):
    st.caption(f"Stack Overflow question by {item['author']} (CC BY-SA 4.0)")
    st.markdown(safe_md(item["question"]))

with st.container(horizontal=True):
    st.button(
        "Save selection",
        key="so_save",
        shortcut="S",
        type="primary",
        icon=":material/check:",
        on_click=save,
        args=(item, False),
    )
    st.button(
        "No match",
        key="so_none",
        shortcut="N",
        icon=":material/block:",
        on_click=save,
        args=(item, True),
    )

st.markdown("**Candidates.** Tick every chunk that answers the question.")
for rank, cid in enumerate(item["candidates"], start=1):
    with st.container(border=True):
        st.checkbox(f"{rank}. `{cid}` answers the question", key=pick_key(item["id"], cid))
        with st.expander("Show chunk", expanded=rank <= 2):
            show_chunk(cid, border=False)
