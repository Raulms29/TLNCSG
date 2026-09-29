#!/bin/bash
cd "$(dirname "$0")/../.."
docker run --rm \
  --name autoresearch \
  -v "$PWD:/opt/project" \
  -w /opt/project/autoresearch \
  virtualuser/tlncsg:latest \
  bash -c 'python3 -u main.py 2>&1 | ts "%Y-%m-%d %H:%M:%S" | tee -a autoresearch.log'