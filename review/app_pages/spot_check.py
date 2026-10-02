"""Blind human re-check of a random sample of Claude-labeled test pairs.

Claude's verdict is deliberately not shown. `make label-agreement` compares the two; for these
items the human verdict wins when the test set is frozen.
"""

from typing import Any

import streamlit as st
from common import advance, nav_bar, queue, show_chunk, show_query, store

from runbook_retriever.labeling import Task

TASK: Task = "spot_check"
items = queue(TASK)
if not items:
    st.info(
        "No spot check yet. After importing Claude's labels, run `make label-spot-check`.",
        icon=":material/info:",
    )
    st.stop()
i = nav_bar(TASK, items)
if i >= len(items):
    st.success("Spot check complete. Run `make label-agreement`.", icon=":material/task_alt:")
    st.stop()
item = items[i]


def save(item: dict[str, Any], verdict: str) -> None:
    store(TASK).put(
        item["id"], {"verdict": verdict, "query": item["query"], "chunk_id": item["chunk_id"]}
    )
    advance(TASK, items)


st.caption("Judge on your own: the other labeler's answer is hidden on purpose.")
show_query(item["query"])
st.markdown("**Labeled chunk.** Does it answer the query?")
show_chunk(item["chunk_id"])
with st.container(horizontal=True):
    for verdict, key, icon in (
        ("correct", "1", ":material/check:"),
        ("wrong", "2", ":material/close:"),
        ("ambiguous", "3", ":material/help:"),
    ):
        st.button(
            verdict.capitalize(),
            key=f"s_{verdict}",
            shortcut=key,
            type="primary" if verdict == "correct" else "secondary",
            icon=icon,
            on_click=save,
            args=(item, verdict),
        )
