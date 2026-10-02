"""Print N random chunks exactly as they will be embedded (Phase 1 gate: do they read cleanly?)."""

from __future__ import annotations

import argparse
import random
import sys

from runbook_retriever.config import get_settings
from runbook_retriever.corpus import load_corpus


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-n", type=int, default=20)
    parser.add_argument("--seed", type=int, default=None, help="default: random each run")
    parser.add_argument("--source", choices=["k8s_docs", "runbook"], default=None)
    args = parser.parse_args(argv)

    chunks = load_corpus(get_settings().paths.corpus)
    if args.source:
        chunks = [c for c in chunks if c.source == args.source]
    seed = args.seed if args.seed is not None else random.randrange(10**6)
    sample = random.Random(seed).sample(chunks, min(args.n, len(chunks)))
    # Docs contain non-ASCII (arrows, quotes); don't crash on legacy Windows consoles.
    sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]
    print(f"# {len(sample)} of {len(chunks)} chunks (seed={seed})\n")
    for c in sample:
        print("=" * 100)
        print(f"{c.chunk_id}  [{c.source}, {c.n_tokens} tokens]  {c.url or c.source_path}")
        print("-" * 100)
        print(c.passage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
