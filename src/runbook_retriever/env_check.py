"""Print the environment the pipeline will run in: ``python -m runbook_retriever.env_check``."""

from __future__ import annotations

import argparse
import platform
import sys

import psutil

from runbook_retriever.config import BASE_MODEL, MAX_SEQ_LENGTH, QUERY_PREFIX, get_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-gpu", action="store_true", help="exit 1 if CUDA is unavailable")
    args = parser.parse_args(argv)

    settings = get_settings()
    print(f"python        {platform.python_version()} ({sys.executable})")
    print(f"platform      {platform.platform()}")
    print(f"ram           {psutil.virtual_memory().total / 2**30:.1f} GiB")
    print(f"repo root     {settings.root}")
    print(f"base model    {BASE_MODEL} (max_seq_length={MAX_SEQ_LENGTH})")
    print(f"query prefix  {QUERY_PREFIX!r}")
    key_state = "set" if settings.gemini_api_key else "NOT SET"
    models = " -> ".join(settings.gemini_models)
    print(f"gemini        {models}, key {key_state}")
    print(f"llm mode      {settings.llm_mode}, rpm={settings.llm_rpm}")

    try:
        import torch
    except ImportError:
        print("torch         not installed (run `make setup`)")
        return 1 if args.require_gpu else 0

    print(f"torch         {torch.__version__} (cuda build {torch.version.cuda})")
    if not torch.cuda.is_available():
        print("gpu           none: training will run on CPU")
        return 1 if args.require_gpu else 0
    props = torch.cuda.get_device_properties(0)
    vram_gib = props.total_memory / 2**30
    print(f"gpu           {props.name}, {vram_gib:.1f} GiB, sm_{props.major}{props.minor}")
    x = torch.randn(512, 512, device="cuda", dtype=torch.float16)
    torch.cuda.synchronize()
    print(f"gpu smoke     fp16 matmul ok ({float((x @ x).float().abs().mean()):.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
