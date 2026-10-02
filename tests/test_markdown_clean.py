from __future__ import annotations

import pytest

from runbook_retriever.markdown_clean import (
    Section,
    clean_markdown,
    drop_sections,
    split_front_matter,
    split_sections,
    strip_shortcodes,
)


def no_examples(_: str) -> str | None:
    return None


def test_front_matter() -> None:
    meta, body = split_front_matter("---\ntitle: Debug Pods\nweight: 10\n---\n\nBody\n")
    assert meta == {"title": "Debug Pods", "weight": 10}
    assert body.strip() == "Body"
    assert split_front_matter("no front matter") == ({}, "no front matter")


def test_front_matter_must_be_mapping() -> None:
    with pytest.raises(ValueError):
        split_front_matter("---\n- a\n---\nx")


def test_shortcodes() -> None:
    src = (
        'A {{< glossary_tooltip text="Pod" term_id="pod" >}} runs. '
        '{{< glossary_tooltip term_id="node" text="nodes" >}}\n'
        '{{< feature-state for_k8s_version="v1.25" state="stable" >}}\n'
        "{{< note >}}\nBe careful.\n{{< /note >}}\n"
        "{{< comment >}}\nhidden\n{{< /comment >}}\n"
        "{{< mermaid >}}\ngraph TD; A-->B\n{{< /mermaid >}}\n"
        '{{% heading "prerequisites" %}}\n'
        '{{< highlight yaml "hl_lines=9" >}}\nkey: v\n{{< /highlight >}}\n'
        '{{< link text="services" url="/docs/x/" >}}'
    )
    out = strip_shortcodes(src, no_examples)
    assert "A Pod runs. nodes" in out
    assert "Note: \nBe careful." in out
    assert "hidden" not in out and "graph TD" not in out
    assert "Before you begin" in out
    assert "```yaml\nkey: v\n```" in out
    assert "services" in out
    assert "{{" not in out and "}}" not in out


def test_code_sample_is_inlined() -> None:
    def load(path: str) -> str | None:
        return "apiVersion: v1\nkind: Pod\n" if path == "pods/a.yaml" else None

    out = strip_shortcodes('{{% code_sample file="pods/a.yaml" %}}', load)
    assert "```yaml\napiVersion: v1\nkind: Pod\n```" in out
    assert strip_shortcodes('{{% code_sample file="missing.yaml" %}}', load).strip() == ""


def test_prose_cleanup_spares_code() -> None:
    src = (
        "<!-- overview -->\nSee [the guide](/docs/x/#y) and ![img](/a.png).\n"
        "## Heading {#anchor}\nuse <br> kubectl  logs &amp; more\n"
        "```shell\nkubectl get pods  # [keep](this) <b>raw</b>\n```\n"
    )
    out = clean_markdown(src, no_examples)
    assert "See the guide and ." in out
    assert "## Heading\n" in out
    assert "use kubectl logs & more" in out
    assert "kubectl get pods  # [keep](this) <b>raw</b>" in out
    assert "<!--" not in out


def test_split_sections_ignores_headings_in_code() -> None:
    src = "intro\n## A\ntext a\n```\n# not a heading\n```\n### A1\ntext a1\n## B\ntext b\n"
    sections = split_sections(src)
    assert [s.path for s in sections] == [(), ("A",), ("A", "A1"), ("B",)]
    assert "# not a heading" in sections[1].body


def test_drop_sections_removes_subsections() -> None:
    secs = [
        Section(("What's next",), "x"),
        Section(("What's next", "More"), "y"),
        Section(("A",), "z"),
    ]
    assert drop_sections(secs, ["what's NEXT"]) == [Section(("A",), "z")]
