#!/bin/bash

python -m experiment.k8 --n-workers 10 --micro-step 1 --macro-step 1 --print-secs 5 --run local-david-20 --master-works
