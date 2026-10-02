SHELL := /bin/sh
.DEFAULT_GOAL := help

UV  ?= uv
RUN := $(UV) run

.PHONY: help setup check-env lint format typecheck test cov check \
        corpus data baseline train evaluate export serve

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-12s %s\n", $$1, $$2}'

# --- Setup & quality ------------------------------------------------------------------

setup: ## Install Python 3.12 env (CUDA torch + dev tools)
	$(UV) sync --extra ml --python 3.12

check-env: ## Print Python/torch/GPU/settings; fails without a GPU
	$(RUN) python -m runbook_retriever.env_check --require-gpu

lint: ## Ruff lint + format check
	$(RUN) ruff check .
	$(RUN) ruff format --check .

format: ## Auto-format and fix lint
	$(RUN) ruff format .
	$(RUN) ruff check --fix .

typecheck: ## mypy --strict
	$(RUN) mypy

test: ## Unit tests (offline)
	$(RUN) pytest

cov: ## Unit tests with coverage
	$(RUN) pytest --cov=runbook_retriever --cov-report=term-missing

check: lint typecheck test ## Everything CI would run

# --- Pipeline (filled in phase by phase) ---------------------------------------------

corpus data baseline train evaluate export serve:
	@echo "'make $@' is not implemented yet (see docs/PLAN.md for its phase)" >&2; exit 1
