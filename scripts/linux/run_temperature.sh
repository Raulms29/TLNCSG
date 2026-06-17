#!/bin/bash
cd "$(dirname "$0")/../.."
python3 -u model_eval/temperature.py 2>&1 | ts '%Y-%m-%d %H:%M:%S' | tee -a temperature.log
