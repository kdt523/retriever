SHELL := /bin/sh
.DEFAULT_GOAL := help

UV  ?= uv
RUN := $(UV) run

.PHONY: help setup check-env lint format typecheck test cov check fetch inspect \
        cluster-up cluster-down faults \
        corpus data review freeze baseline-val baseline train evaluate export serve

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-12s %s\n", $$1, $$2}'

# --- Setup & quality ------------------------------------------------------------------

setup: ## Install Python 3.12 env (CUDA torch + dev tools)
	$(UV) sync --extra ml --extra label --python 3.12

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

# --- Phase 1: corpus -----------------------------------------------------------------

N ?= 20
SEED ?=

fetch: ## Sparse-clone kubernetes/website at the pinned commit
	$(RUN) python -m runbook_retriever.fetch_docs

corpus: fetch ## Build data/corpus.jsonl (k8s docs + runbooks)
	$(RUN) python -m runbook_retriever.build_corpus

inspect: ## Print N random chunks as embedded (N=20 SEED=...)
	$(RUN) python -m runbook_retriever.inspect_corpus -n $(N) $(if $(SEED),--seed $(SEED))

# --- Phase 1b: verify runbooks against a real cluster --------------------------------

CLUSTER ?= rr-faults
FAULT_IMAGES := busybox:1.36 python:3.12-alpine nginx:1.27-alpine
ONLY ?=

cluster-up: ## Create the throwaway k3d cluster used by `make faults`
	k3d cluster create $(CLUSTER) --agents 1 --k3s-arg "--disable=traefik@server:0" --wait --timeout 300s
	@# Docker Desktop: k3d writes host.docker.internal, which can resolve to a firewalled LAN IP.
	kubectl config set-cluster k3d-$(CLUSTER) \
	  --server=https://127.0.0.1:$$(docker port k3d-$(CLUSTER)-serverlb 6443/tcp | head -1 | cut -d: -f2)
	@# Pull per node: `k3d image import` fails on multi-platform images under Docker Desktop.
	for node in server-0 agent-0; do for img in $(FAULT_IMAGES); do \
	  docker exec k3d-$(CLUSTER)-$$node ctr -n k8s.io images pull --platform linux/amd64 docker.io/library/$$img >/dev/null; \
	done; done
	kubectl --context k3d-$(CLUSTER) get nodes

cluster-down: ## Delete the k3d cluster
	k3d cluster delete $(CLUSTER)

faults: ## Inject faults and record real output to data/incidents/ (ONLY=id1,id2)
	$(RUN) python -m runbook_retriever.fault_capture --context k3d-$(CLUSTER) $(if $(ONLY),--only $(ONLY))

# --- Phase 2: training and evaluation data ------------------------------------------

splits: ## Assign docs to train/val/test (once; frozen afterwards)
	$(RUN) python -m runbook_retriever.splits

queries: ## Generate queries with Gemini (cached + resumable; rerun until complete)
	$(RUN) python -m runbook_retriever.gen_queries

data: queries ## Queries -> filtered pairs, incident queries, hard negatives, review queues
	$(RUN) python -m runbook_retriever.filter_pairs
	$(RUN) python -m runbook_retriever.incident_queries
	$(RUN) python -m runbook_retriever.mine_negatives
	$(RUN) python -m runbook_retriever.build_review_sets

review: ## Open the labeling app (hand-check test set, SO mapping, audits)
	$(RUN) streamlit run review/streamlit_app.py

freeze: ## Freeze test/val/ood sets from reviewed labels (once)
	$(RUN) python -m runbook_retriever.freeze_testset

# --- Phase 3: baselines --------------------------------------------------------------

baseline-val: ## Score all baselines on val (no labels needed) -> results/baseline_val.csv
	$(RUN) python -m runbook_retriever.evaluate --split val

baseline: ## Score all baselines on the frozen test set -> results/baseline.csv
	$(RUN) python -m runbook_retriever.evaluate --split test

# --- Later phases --------------------------------------------------------------------

train evaluate export serve:
	@echo "'make $@' is not implemented yet (see docs/PLAN.md for its phase)" >&2; exit 1
