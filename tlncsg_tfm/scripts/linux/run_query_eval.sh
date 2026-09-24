#!/bin/bash
cd "$(dirname "$0")/../.."
python3 -u -m query_eval.query_eval 2>&1 | ts '%Y-%m-%d %H:%M:%S' | tee -a query_eval.log
