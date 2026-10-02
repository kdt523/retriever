"""Sparse-clone kubernetes/website at the pinned commit into ``data/raw/k8s-website``.

Only the configured doc directories and the examples tree are checked out, so the
download stays small. Re-running is idempotent: an existing checkout is moved to
the pinned commit instead of re-cloned.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
from pathlib import Path

from runbook_retriever.config import get_settings
from runbook_retriever.corpus_config import K8sDocsConfig, load_corpus_config
from runbook_retriever.logging_setup import setup_logging

log = logging.getLogger(__name__)


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


def sparse_patterns(cfg: K8sDocsConfig) -> list[str]:
    """Non-cone sparse-checkout patterns: ``/dir/`` for directories, ``/file.md`` for files."""
    paths = [f"{cfg.docs_root}/{p}" for p in cfg.include] + [cfg.examples_root]
    return [f"/{p}" if p.endswith(".md") else f"/{p}/" for p in paths]


def fetch(cfg: K8sDocsConfig, dest: Path) -> str:
    if not (dest / ".git").exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        log.info("cloning %s (sparse, blobless) into %s", cfg.repo, dest)
        _git("clone", "--filter=blob:none", "--no-checkout", "--sparse", cfg.repo, str(dest))
    _git("sparse-checkout", "set", "--no-cone", *sparse_patterns(cfg), cwd=dest)
    try:
        _git("cat-file", "-e", f"{cfg.commit}^{{commit}}", cwd=dest)
    except RuntimeError:
        log.info("fetching pinned commit %s", cfg.commit[:12])
        _git("fetch", "--filter=blob:none", "origin", cfg.commit, cwd=dest)
    # Always check out: a fresh --no-checkout clone already has HEAD == commit but no files.
    _git("-c", "advice.detachedHead=false", "checkout", "--force", cfg.commit, cwd=dest)
    head = _git("rev-parse", "HEAD", cwd=dest)
    if head != cfg.commit:
        raise RuntimeError(f"checkout is at {head}, expected {cfg.commit}")
    log.info("k8s docs at %s in %s", head[:12], dest)
    return head


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)
    setup_logging()
    paths = get_settings().paths
    cfg = load_corpus_config(args.config or paths.configs / "corpus.yaml")
    fetch(cfg.k8s_docs, paths.raw / "k8s-website")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
