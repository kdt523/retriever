from __future__ import annotations

from pathlib import Path

from runbook_retriever.ablation_report import COLS, load_all_rows, render


def test_render_reports_seed_mean_and_sd(tmp_path: Path) -> None:
    header = "split,retriever,slice,n," + ",".join(COLS)
    rows = [
        header,
        *(
            f"test,{name},all,10,{v},{v},{v},{v},{v}"
            for name, v in (("tuned", 0.5), ("models/ablations/seed43", 0.6), ("seed44", 0.7))
        ),
        "test,tuned,stackoverflow,3,0,0,0,0,0",
    ]
    path = tmp_path / "a.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    loaded = load_all_rows(path)
    assert set(loaded) == {"tuned", "seed43", "seed44"}
    text = "\n".join(render(loaded, "t"))
    assert "0.600 ± 0.100" in text
