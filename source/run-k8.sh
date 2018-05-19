#!/bin/sh

pipenv run python -m experiment.k8 $@ \
	--gcs-dir k8 \
	--bucket octavian-training \
	--model-dir gs://octavian-training/k8/checkpoint \
	--n-workers 3 \
	--group k8_r0 \
	--micro-step 500 \
	--macro-step 10 \
	--disable-load
