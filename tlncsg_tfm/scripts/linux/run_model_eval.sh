#!/bin/bash
cd "$(dirname "$0")/../.."
python3 -u model_eval/model_eval.py 2>&1 | ts '%Y-%m-%d %H:%M:%S' | tee -a model_eval.log
