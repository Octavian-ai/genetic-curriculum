#!/bin/bash

python -m src.baseline --output-dir ./output_baseline  --model-dir ./output_baseline/checkpoint \
	--disable-load \
	--single-threaded \
	--group baseline \
	--micro-step 100