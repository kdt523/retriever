#!/bin/sh
# Phase 5: train the ablation and seed variants one after another (about 6-8 min each on the GPU).
# Each model lands in models/ablations/<name>; every run is logged to results/runs.csv.
set -eu

RUN="uv run python -m runbook_retriever.train --phase 5"
OUT=models/ablations

$RUN --name seed43 --seed 43 --output-dir $OUT/seed43
$RUN --name seed44 --seed 44 --output-dir $OUT/seed44
$RUN --name no-hard-negatives --no-hard-negatives --output-dir $OUT/no-hard-negatives
$RUN --name data-25pct --train-fraction 0.25 --output-dir $OUT/data-25pct
$RUN --name data-50pct --train-fraction 0.5 --output-dir $OUT/data-50pct
$RUN --name epochs-1 --epochs 1 --output-dir $OUT/epochs-1
