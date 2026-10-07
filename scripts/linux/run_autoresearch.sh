#!/bin/bash
#
# ./scripts/linux/run_autoresearch.sh run
# ./scripts/linux/run_autoresearch.sh reset

cd "$(dirname "$0")/../.." || exit

COMMAND=$1
shift

if [ -z "$COMMAND" ]; then
  echo "Usage: $0 <command> [args...]"
  echo "Commands: run, reset"
  exit 1
fi

case $COMMAND in
  run)
    docker run --rm \
      --name autoresearch \
      -v "$PWD:/opt/project" \
      -w /opt/project/autoresearch \
      virtualuser/tlncsg:latest \
      bash -c 'python3 -u main.py "$@" 2>&1 | ts "%Y-%m-%d %H:%M:%S" | tee -a autoresearch.log' _ "$@"
    ;;
  reset)
    docker run --rm \
      --name autoresearch \
      -v "$PWD:/opt/project" \
      -w /opt/project/autoresearch \
      virtualuser/tlncsg:latest \
      bash -c 'python3 -u main.py --reset "$@" 2>&1 | ts "%Y-%m-%d %H:%M:%S" | tee -a autoresearch.log' _ "$@"
    ;;
  *)
    echo "Unknown command: $COMMAND"
    echo "Commands: run, reset"
    exit 1
    ;;
esac