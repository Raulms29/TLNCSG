#!/bin/bash
cd "$(dirname "$0")/../.."
python3 -u autoresearch/main.py --reset 2>&1 | ts '%Y-%m-%d %H:%M:%S' | tee autoresearch.log
