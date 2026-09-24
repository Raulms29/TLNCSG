#!/bin/bash
cd "$(dirname "$0")/../.."
python3 -u -m grammar_eval.grammar_eval 2>&1 | ts '%Y-%m-%d %H:%M:%S' | tee -a grammar_eval.log
