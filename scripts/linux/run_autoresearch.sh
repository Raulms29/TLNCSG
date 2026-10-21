#!/bin/bash
#
# ./scripts/linux/run_autoresearch.sh run
# ./scripts/linux/run_autoresearch.sh reset
#
# Each run writes its log to autoresearch/archive/run_<timestamp>/autoresearch.log.

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
      -w /opt/project \
      virtualuser/tlncsg:latest \
      bash -c 'python3 -u -m autoresearch.main "$@"' _ "$@"
    ;;
  reset)
    docker run --rm \
      --name autoresearch \
      -v "$PWD:/opt/project" \
      -w /opt/project \
      virtualuser/tlncsg:latest \
      bash -c 'python3 -u -m autoresearch.main --reset "$@"' _ "$@"
    ;;
  *)
    echo "Unknown command: $COMMAND"
    echo "Commands: run, reset"
    exit 1
    ;;
esac