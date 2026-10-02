from typing import Any

import streamlit as st
from common import advance, nav_bar, require_queue, show_chunk, show_query, store

from runbook_retriever.labeling import Task

TASK: Task = "negatives_audit"
items = require_queue(TASK)
i = nav_bar(TASK, items)
if i >= len(items):
    st.success("Spot check complete.", icon=":material/task_alt:")
    st.stop()
item = items[i]


def save(item: dict[str, Any], verdict: str) -> None:
    store(TASK).put(
        item["id"],
        {
            "verdict": verdict,
            "query": item["query"],
            "chunk_id": item["chunk_id"],
            "negative_id": item["negative_id"],
        },
    )
    advance(TASK, items)


show_query(item["query"])
with st.expander("Positive chunk (the labeled answer)"):
    show_chunk(item["chunk_id"], border=False)
st.markdown("**Mined hard negative.** Does this chunk *also* answer the query?")
show_chunk(item["negative_id"])
with st.container(horizontal=True):
    st.button(
        "Not an answer",
        key="n_true",
        shortcut="1",
        type="primary",
        icon=":material/check:",
        on_click=save,
        args=(item, "true_negative"),
    )
    st.button(
        "Also answers (false negative)",
        key="n_false",
        shortcut="2",
        icon=":material/warning:",
        on_click=save,
        args=(item, "false_negative"),
    )
