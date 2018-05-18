#!/bin/sh

pipenv run python -m experiment.k8 \
	--gcs-dir k8 \
	--bucket octavian-training \
	--model-dir gs://octavian-training/k8/checkpoint \
	--n-workers 10 \
	--group k8 \
	--floyd-metrics