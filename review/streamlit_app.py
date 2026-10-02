"""RunbookRetriever review app: `make review` (or `streamlit run review/streamlit_app.py`)."""

import streamlit as st

st.set_page_config(page_title="RunbookRetriever review", page_icon=":material/fact_check:")

page = st.navigation(
    [
        st.Page("app_pages/overview.py", title="Overview", icon=":material/dashboard:"),
        st.Page("app_pages/test_pairs.py", title="Test pairs", icon=":material/rule:"),
        st.Page("app_pages/so_questions.py", title="Stack Overflow", icon=":material/forum:"),
        st.Page("app_pages/train_audit.py", title="Train audit", icon=":material/fact_check:"),
        st.Page("app_pages/negatives.py", title="Negatives", icon=":material/do_not_disturb_on:"),
    ],
    position="top",
)
st.title(page.title, anchor=False)
page.run()
