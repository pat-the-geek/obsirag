#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

LOG_FILE="logs/obsirag.log"
MODE="quick"
SKIP_RESTART="false"
REPORT_DIR="logs/validation"

while [ $# -gt 0 ]; do
  case "$1" in
    --full)
      MODE="full"
      ;;
    --smoke)
      MODE="smoke"
      ;;
    --nrt)
      MODE="nrt"
      ;;
    --no-restart)
      SKIP_RESTART="true"
      ;;
    --report-dir)
      if [ $# -lt 2 ]; then
        echo "Option --report-dir attend un chemin"
        exit 1
      fi
      REPORT_DIR="$2"
      shift
      ;;
    -h|--help)
      echo "Usage: ./scripts/validate_local.sh [--full|--smoke|--nrt] [--no-restart] [--report-dir DIR]"
      echo "  (default) lance la validation rapide UI"
      echo "  --full         lance la suite complete pytest --no-cov"
      echo "  --smoke        lance un sous-ensemble critique en boucle rapide"
      echo "  --nrt          lance la suite ultra-courte de non-regression UI heritee (< 10 tests)"
      echo "  --no-restart   saute le redemarrage controle"
      echo "  --report-dir   dossier de sortie des rapports JUnit/JSON"
      exit 0
      ;;
    *)
      echo "Argument non reconnu: $1"
      echo "Usage: ./scripts/validate_local.sh [--full|--smoke|--nrt] [--no-restart] [--report-dir DIR]"
      exit 1
      ;;
  esac
  shift
done

mkdir -p "$REPORT_DIR"
RUN_STAMP="$(date +"%Y%m%d_%H%M%S")"
RUN_STARTED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
RUN_START_EPOCH="$(date +%s)"
JUNIT_REPORT_PATH="${REPORT_DIR}/validate_local_${MODE}_${RUN_STAMP}.junit.xml"
JSON_REPORT_PATH="${REPORT_DIR}/validate_local_${MODE}_${RUN_STAMP}.json"

if [ "$SKIP_RESTART" = "true" ]; then
  echo "==> Validation locale: redémarrage contrôlé sauté (--no-restart)"
else
  echo "==> Validation locale: redémarrage contrôlé"
  ./scripts/post_restart_check.sh
fi

echo "==> Validation locale: tests (${MODE})"
source .venv/bin/activate
echo "    Rapport JUnit: ${JUNIT_REPORT_PATH}"
echo "    Rapport JSON : ${JSON_REPORT_PATH}"

PYTEST_EXIT_CODE=0
if [ "$MODE" = "full" ]; then
  set +e
  pytest --no-cov --junitxml "$JUNIT_REPORT_PATH"
  PYTEST_EXIT_CODE=$?
  set -e
elif [ "$MODE" = "smoke" ]; then
  set +e
  pytest --no-cov --junitxml "$JUNIT_REPORT_PATH" -q \
    tests/test_services_cache.py \
    tests/test_chroma_compat.py \
    tests/test_chat_navigation.py \
    tests/test_chat_ui_fragments.py \
    tests/test_conversation_store.py \
    tests/test_runtime_state_store.py
  PYTEST_EXIT_CODE=$?
  set -e
elif [ "$MODE" = "nrt" ]; then
  set +e
  pytest --no-cov --junitxml "$JUNIT_REPORT_PATH" -q -m nrt
  PYTEST_EXIT_CODE=$?
  set -e
else
  set +e
  pytest --no-cov --junitxml "$JUNIT_REPORT_PATH" -q \
    tests/test_chat_ui_fragments.py \
    tests/test_note_ui_fragments.py \
    tests/test_brain_ui_fragments.py \
    tests/test_conversation_store.py \
    tests/test_query_history_store.py \
    tests/test_note_viewer.py \
    tests/test_chat_navigation.py \
    tests/test_insights_browser.py
  PYTEST_EXIT_CODE=$?
  set -e
fi

CHROMA_REPORT_PATH=""
OBS_WEEKLY_REPORT_PATH=""
if [ "$PYTEST_EXIT_CODE" -eq 0 ]; then
  echo "==> Export observabilite perf Chroma (local/CI)"
  set +e
  CHROMA_REPORT_PATH="$(python scripts/export_chroma_perf_report.py 2>/dev/null | tail -n 1)"
  CHROMA_EXPORT_EXIT_CODE=$?
  set -e
  if [ "$CHROMA_EXPORT_EXIT_CODE" -ne 0 ]; then
    echo "    Export perf Chroma ignoré (non bloquant)"
    CHROMA_REPORT_PATH=""
  else
    echo "    Rapport perf Chroma: ${CHROMA_REPORT_PATH}"
  fi

  echo "==> Export observabilite hebdomadaire compacte"
  set +e
  OBS_WEEKLY_REPORT_PATH="$(python scripts/export_observability_weekly.py 2>/dev/null | tail -n 1)"
  OBS_WEEKLY_EXIT_CODE=$?
  set -e
  if [ "$OBS_WEEKLY_EXIT_CODE" -ne 0 ]; then
    echo "    Export hebdomadaire ignoré (non bloquant)"
    OBS_WEEKLY_REPORT_PATH=""
  else
    echo "    Rapport hebdomadaire: ${OBS_WEEKLY_REPORT_PATH}"
  fi
fi

RUN_ENDED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
RUN_END_EPOCH="$(date +%s)"
RUN_DURATION_SECONDS="$((RUN_END_EPOCH - RUN_START_EPOCH))"

PYTEST_STATUS="passed"
if [ "$PYTEST_EXIT_CODE" -ne 0 ]; then
  PYTEST_STATUS="failed"
fi

cat > "$JSON_REPORT_PATH" <<EOF
{
  "mode": "${MODE}",
  "skip_restart": ${SKIP_RESTART},
  "status": "${PYTEST_STATUS}",
  "pytest_exit_code": ${PYTEST_EXIT_CODE},
  "chroma_perf_report": "${CHROMA_REPORT_PATH}",
  "observability_weekly_report": "${OBS_WEEKLY_REPORT_PATH}",
  "started_at_utc": "${RUN_STARTED_AT}",
  "ended_at_utc": "${RUN_ENDED_AT}",
  "duration_seconds": ${RUN_DURATION_SECONDS},
  "junit_report": "${JUNIT_REPORT_PATH}",
  "log_file": "${LOG_FILE}"
}
EOF

cp "$JUNIT_REPORT_PATH" "${REPORT_DIR}/latest.junit.xml"
cp "$JSON_REPORT_PATH" "${REPORT_DIR}/latest.json"

echo "==> Validation locale: synthèse logs"
if [ -f "$LOG_FILE" ]; then
  tail -n 30 "$LOG_FILE"
else
  echo "    Aucun log trouvé (${LOG_FILE})"
fi

echo "==> Rapports machine-readable"
echo "    JUnit: ${JUNIT_REPORT_PATH}"
echo "    JSON : ${JSON_REPORT_PATH}"
echo "    Latest JUnit: ${REPORT_DIR}/latest.junit.xml"
echo "    Latest JSON : ${REPORT_DIR}/latest.json"

echo "==> Validation locale terminée"

if [ "$PYTEST_EXIT_CODE" -ne 0 ]; then
  exit "$PYTEST_EXIT_CODE"
fi