#!/bin/bash
#
# ./scripts/linux/run_pipeline.sh execution
# ./scripts/linux/run_pipeline.sh grouping --execution-dir outputs/execution/300926_300926_0001
# ./scripts/linux/run_pipeline.sh evaluation --grouping-dir outputs/grouping/011026_011026_0001
# ./scripts/linux/run_pipeline.sh review

cd "$(dirname "$0")/../.." || exit

MODULE=$1
shift

if [ -z "$MODULE" ]; then
  echo "Usage: $0 <module> [args...]"
  echo "Modules: execution, grouping, evaluation, review"
  exit 1
fi

case $MODULE in
  execution)
    docker run --rm \
      --name execution \
      -v "$PWD:/opt/project" \
      -w /opt/project \
      virtualuser/tlncsg:latest \
      bash -c 'python3 -u -m pipeline.execution.main --config execution_config.json "$@"' _ "$@"
    ;;
  grouping)
    docker run --rm \
      --name grouping \
      -v "$PWD:/opt/project" \
      -w /opt/project \
      virtualuser/tlncsg:latest \
      bash -c 'python3 -u -m pipeline.grouping.main --config grouping_config.json "$@"' _ "$@"
    ;;
  evaluation)
    docker run --rm \
      --name evaluation \
      -v "$PWD:/opt/project" \
      -w /opt/project \
      virtualuser/tlncsg:latest \
      bash -c 'python3 -u -m pipeline.evaluation.main --config evaluation_config.json "$@"' _ "$@"
    ;;
  review)
    docker run --rm \
      --name review \
      -p 8501:8501 \
      -v "$PWD:/opt/project" \
      -w /opt/project \
      virtualuser/tlncsg:latest \
      bash -c 'python3 -m streamlit run pipeline/review/app.py "$@"' _ "$@"
    ;;
  *)
    echo "Unknown module: $MODULE"
    echo "Modules: execution, grouping, evaluation, review"
    exit 1
    ;;
esac
