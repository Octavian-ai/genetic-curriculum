#!/bin/bash

floyd run --gpu --env tensorflow-1.7 "python -m src.train --output-dir /output --model-dir /output/checkpoint --micro-step 10000"