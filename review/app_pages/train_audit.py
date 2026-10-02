from typing import Any

import streamlit as st
from common import advance, nav_bar, require_queue, show_chunk, show_query, store

from runbook_retriever.labeling import Task

TASK: Task = "train_audit"
items = require_queue(TASK)
i = nav_bar(TASK, items)
if i >= len(items):
    st.success("Audit complete.", icon=":material/task_alt:")
    st.stop()
item = items[i]


def save(item: dict[str, Any], verdict: str) -> None:
    store(TASK).put(
        item["id"], {"verdict": verdict, "query": item["query"], "chunk_id": item["chunk_id"]}
    )
    advance(TASK, items)


st.caption(f"Style **{item['style']}**")
show_query(item["query"])
st.markdown("**Positive chunk.** Is this a correct answer for the query?")
show_chunk(item["chunk_id"])
with st.container(horizontal=True):
    st.button(
        "Correct",
        key="a_correct",
        shortcut="1",
        type="primary",
        icon=":material/check:",
        on_click=save,
        args=(item, "correct"),
    )
    st.button(
        "Wrong",
        key="a_wrong",
        shortcut="2",
        icon=":material/close:",
        on_click=save,
        args=(item, "wrong"),
    )
