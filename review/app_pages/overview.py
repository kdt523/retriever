import streamlit as st
from common import queue, store

from runbook_retriever.labeling import rate, summarize

st.caption(
    "Hand-check the data before the test set is frozen. Labels save on every click to "
    "`data/labels/`; stop and resume any time. Keys: `1` `2` `3` verdicts, `←` `→` move, "
    "`U` next unlabeled."
)

test = summarize(queue("test_pairs"), store("test_pairs").all())
so = summarize(queue("so_questions"), store("so_questions").all())
train = summarize(queue("train_audit"), store("train_audit").all())
negs = summarize(queue("negatives_audit"), store("negatives_audit").all())


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


with st.container(horizontal=True):
    st.metric("Test pairs labeled", f"{test.labeled} / {test.total}", border=True)
    st.metric("Test labels correct", pct(rate(test, "correct")), border=True)
    st.metric("SO questions mapped", f"{so.counts.get('mapped', 0)} (goal 50)", border=True)
with st.container(horizontal=True):
    st.metric("Train pairs audited", f"{train.labeled} / {train.total}", border=True)
    st.metric("Train label error rate", pct(rate(train, "wrong")), border=True)
    st.metric("False-negative rate", pct(rate(negs, "false_negative")), border=True)

st.subheader("What each task needs", anchor=False)
st.markdown(
    """
- **Test pairs**: is the labeled chunk a correct answer for the query? Tick other candidate
  chunks that also answer it. *Ambiguous* = query too vague to have one answer; it is dropped.
- **Stack Overflow**: tick every candidate chunk that answers the real question, or press
  **No match** (those become out-of-scope queries for the "no runbook matches" threshold).
- **Train audit**: is the training pair correct? Gives the label error rate for the README.
- **Negatives**: is the mined "hard negative" actually a valid answer (a false negative)?
"""
)
