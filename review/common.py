"""Shared loaders and widgets for the review pages."""

from __future__ import annotations

from typing import Any

import streamlit as st

from runbook_retriever.config import get_settings
from runbook_retriever.corpus import Chunk, load_corpus
from runbook_retriever.labeling import LabelStore, Task, first_unlabeled, load_queue

PATHS = get_settings().paths


@st.cache_resource
def corpus() -> dict[str, Chunk]:
    return {c.chunk_id: c for c in load_corpus(PATHS.corpus)}


@st.cache_resource
def store(task: Task) -> LabelStore:
    return LabelStore(PATHS.data / "labels" / f"{task}.jsonl")


@st.cache_data
def queue(task: Task) -> list[dict[str, Any]]:
    return load_queue(PATHS.data / "review" / f"{task}.jsonl")


def require_queue(task: Task) -> list[dict[str, Any]]:
    items = queue(task)
    if not items:
        st.info("This queue is empty. Run `make data` first.", icon=":material/info:")
        st.stop()
    return items


def _idx_key(task: Task) -> str:
    return f"{task}_idx"


def _go(task: Task, index: int, n: int) -> None:
    st.session_state[_idx_key(task)] = max(0, min(index, n))


def advance(task: Task, items: list[dict[str, Any]]) -> None:
    """Move to the next unlabeled item after the current one (wrapping to the first)."""
    labeled = store(task).labeled_ids()
    cur = st.session_state[_idx_key(task)]
    order = list(range(cur + 1, len(items))) + list(range(cur + 1))
    nxt = next((i for i in order if items[i]["id"] not in labeled), len(items))
    st.session_state[_idx_key(task)] = nxt


def nav_bar(task: Task, items: list[dict[str, Any]]) -> int:
    """Progress, position and prev/next controls. Returns the current index."""
    labels = store(task)
    labeled = labels.labeled_ids()
    st.session_state.setdefault(_idx_key(task), first_unlabeled(items, labeled))
    i = st.session_state[_idx_key(task)]
    done = sum(item["id"] in labeled for item in items)
    st.progress(done / len(items), text=f"{done} of {len(items)} labeled")
    with st.container(horizontal=True, vertical_alignment="center"):
        st.button(
            "Previous",
            icon=":material/arrow_back:",
            shortcut="Left",
            on_click=_go,
            args=(task, i - 1, len(items)),
            disabled=i == 0,
        )
        st.button(
            "Next",
            icon=":material/arrow_forward:",
            shortcut="Right",
            on_click=_go,
            args=(task, i + 1, len(items) - 1),
            disabled=i >= len(items) - 1,
        )
        st.button(
            "Next unlabeled",
            icon=":material/skip_next:",
            shortcut="U",
            on_click=advance,
            args=(task, items),
        )
        if i < len(items):
            st.caption(f"Item {i + 1} of {len(items)}")
    if i < len(items) and (existing := labels.get(items[i]["id"])):
        verdict = (
            existing.get("verdict") or f"{len(existing.get('relevant', []))} chunk(s) selected"
        )
        st.caption(
            f":material/history: Already labeled: **{verdict}**. Labeling again replaces it."
        )
    return int(i)


def safe_md(text: str) -> str:
    """Escape ``$`` so kubectl output and shell snippets are not rendered as LaTeX."""
    return text.replace("$", "\\$")


def show_query(text: str) -> None:
    st.code(text, language=None, wrap_lines=True)


def show_chunk(chunk_id: str, *, border: bool = True) -> None:
    chunk = corpus().get(chunk_id)
    with st.container(border=border):
        if chunk is None:
            st.warning(f"Chunk `{chunk_id}` is not in the corpus.")
            return
        where = f" · [source]({chunk.url})" if chunk.url else ""
        st.caption(f"`{chunk.chunk_id}`{where}")
        st.markdown(safe_md(chunk.passage))
