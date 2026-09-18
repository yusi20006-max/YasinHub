#!/usr/bin/env bash
# Run the complete YasinHub pytest suite in resource-bounded chunks.
#
# Default: one test module per Python process. No tests are skipped.
# A non-zero result is retained and reported at the end.
#
# Optional:
#   YASINHUB_TERMUX_BATCH_SIZE=N  run N test modules per pytest process
#   YASINHUB_TERMUX_LOG=PATH     write a timestamped execution log

set -u

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT" || exit 1

BATCH_SIZE="${YASINHUB_TERMUX_BATCH_SIZE:-1}"
LOG_FILE="${YASINHUB_TERMUX_LOG:-termux-pytest.log}"

case "$BATCH_SIZE" in
  ''|*[!0-9]*|0) echo "YASINHUB_TERMUX_BATCH_SIZE must be a positive integer" >&2; exit 2 ;;
esac

mapfile -t TEST_FILES < <(find tests -maxdepth 1 -type f -name 'test_*.py' -print | LC_ALL=C sort)

if [ "${#TEST_FILES[@]}" -eq 0 ]; then
  echo "No test files discovered under tests/" >&2
  exit 2
fi

: > "$LOG_FILE"
printf 'YasinHub Termux full-suite verification\nroot=%s\ntest_files=%s\nbatch_size=%s\n\n' \
  "$ROOT" "${#TEST_FILES[@]}" "$BATCH_SIZE" | tee -a "$LOG_FILE"

failures=0
environment_terminations=0
batch_index=0

run_batch() {
  local -a files=("$@")
  local start end rc
  start="$(date +%s)"
  printf '\n[%s] batch %d (%d file(s))\n' "$(date -Iseconds)" "$batch_index" "${#files[@]}" | tee -a "$LOG_FILE"
  printf 'files: %s\n' "${files[*]}" | tee -a "$LOG_FILE"

  set +e
  python -m pytest -q --tb=short -ra "${files[@]}" 2>&1 | tee -a "$LOG_FILE"
  rc="${PIPESTATUS[0]}"
  set -e

  end="$(date +%s)"
  if [ "$rc" -eq 0 ]; then
    printf '[%s] PASS batch=%d duration=%ss\n' "$(date -Iseconds)" "$batch_index" "$((end-start))" | tee -a "$LOG_FILE"
  elif [ "$rc" -ge 128 ]; then
    printf '[%s] ENVIRONMENT TERMINATION batch=%d exit=%d signal=%d duration=%ss\n' \
      "$(date -Iseconds)" "$batch_index" "$rc" "$((rc-128))" "$((end-start))" | tee -a "$LOG_FILE"
    environment_terminations=$((environment_terminations+1))
    failures=$((failures+1))
  else
    printf '[%s] TEST FAILURE batch=%d exit=%d duration=%ss\n' \
      "$(date -Iseconds)" "$batch_index" "$rc" "$((end-start))" | tee -a "$LOG_FILE"
    failures=$((failures+1))
  fi
}

set -e
for ((i=0; i<${#TEST_FILES[@]}; i+=BATCH_SIZE)); do
  batch_index=$((batch_index+1))
  batch=("${TEST_FILES[@]:i:BATCH_SIZE}")
  run_batch "${batch[@]}"
done

printf '\n[%s] SUMMARY files=%d batches=%d failures=%d environment_terminations=%d log=%s\n' \
  "$(date -Iseconds)" "${#TEST_FILES[@]}" "$batch_index" "$failures" "$environment_terminations" "$LOG_FILE" | tee -a "$LOG_FILE"

if [ "$failures" -ne 0 ]; then
  exit 1
fi
exit 0
