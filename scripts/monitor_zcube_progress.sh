#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="${1:-/tmp/zcube_full_deadstream.log}"
OUT_FILE="${2:-/tmp/zcube_full_deadstream_30m.log}"
INTERVAL="${3:-1800}"
SESSION_NAME="${4:-zcube_full_deadstream}"
RESULT_DIR="${5:-}"
FAST_INTERVAL="${MONITOR_FAST_INTERVAL:-300}"
VERY_FAST_INTERVAL="${MONITOR_VERY_FAST_INTERVAL:-120}"
NEAR_LAYER="${MONITOR_NEAR_LAYER:-1100}"
VERY_NEAR_LAYER="${MONITOR_VERY_NEAR_LAYER:-1180}"
NEAR_PERCENT_X100="${MONITOR_NEAR_PERCENT_X100:-8500}"
VERY_NEAR_PERCENT_X100="${MONITOR_VERY_NEAR_PERCENT_X100:-9500}"

PATTERN='phase: forward|phase: input_grad|phase: weight_grad|pass: 0 finished|\[NS3\] Drained|\[NS3\] Started|\[NS3\] Flushed|fatal signal|Program received signal|Segmentation|could not find|no free RDMA|all passes finished|Zcube256 done|全部选定'

while true; do
  sleep_interval="${INTERVAL}"
  {
    echo "===== $(date '+%F %T %z') ====="
    if tmux list-sessions 2>/dev/null | rg -q "^${SESSION_NAME}:"; then
      echo "tmux: ${SESSION_NAME} running"
    else
      echo "tmux: ${SESSION_NAME} not found"
    fi

    if [[ -f "${LOG_FILE}" ]]; then
      stat -c 'log_mtime: %y, size: %s bytes' "${LOG_FILE}"
      rg "${PATTERN}" "${LOG_FILE}" | tail -20 || true
      latest_progress="$(rg --color never 'phase_progress: [0-9]+/[0-9]+' "${LOG_FILE}" | tail -1 || true)"
      if [[ -n "${latest_progress}" ]]; then
        echo "latest_progress: ${latest_progress}"
      fi
      current_layer="$(printf '%s\n' "${latest_progress}" | sed -E 's/.*phase_progress: ([0-9]+)\/([0-9]+).*/\1/')"
      total_layers="$(printf '%s\n' "${latest_progress}" | sed -E 's/.*phase_progress: ([0-9]+)\/([0-9]+).*/\2/')"
      if [[ "${current_layer}" =~ ^[0-9]+$ ]]; then
        if [[ "${total_layers}" =~ ^[0-9]+$ ]] && (( total_layers > 0 )); then
          progress_x100=$(( current_layer * 10000 / total_layers ))
          echo "progress_x100: ${progress_x100}"
          if (( progress_x100 >= VERY_NEAR_PERCENT_X100 )); then
            sleep_interval="${VERY_FAST_INTERVAL}"
          elif (( progress_x100 >= NEAR_PERCENT_X100 )); then
            sleep_interval="${FAST_INTERVAL}"
          fi
        elif (( current_layer >= VERY_NEAR_LAYER )); then
          sleep_interval="${VERY_FAST_INTERVAL}"
        elif (( current_layer >= NEAR_LAYER )); then
          sleep_interval="${FAST_INTERVAL}"
        fi
      fi
    else
      echo "log_missing: ${LOG_FILE}"
    fi
    if [[ -n "${RESULT_DIR}" ]]; then
      for csv in EndToEnd.csv detailed_256.csv; do
        csv_path="${RESULT_DIR%/}/${csv}"
        if [[ -f "${csv_path}" ]]; then
          stat -c "${csv}: %s bytes, mtime: %y" "${csv_path}"
        else
          echo "${csv}: missing"
        fi
      done
    fi
    echo "next_sleep: ${sleep_interval}s"
    echo
  } >> "${OUT_FILE}" 2>&1

  sleep "${sleep_interval}"
done
