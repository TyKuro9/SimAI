#!/usr/bin/env bash
set -uo pipefail

if [[ "$#" -lt 5 ]]; then
  echo "usage: $0 <label> <session> <log> <out_dir> <monitor_log> [interval_sec]" >&2
  exit 2
fi

LABEL="$1"
SESSION="$2"
LOG="$3"
OUT_DIR="$4"
MONITOR_LOG="$5"
INTERVAL="${6:-3600}"

mkdir -p "$(dirname "${MONITOR_LOG}")"

while true; do
  {
    echo "===== $(date '+%F %T %z') ${LABEL} ====="
    if tmux has-session -t "${SESSION}" 2>/dev/null; then
      echo "tmux: ${SESSION} running"
    else
      echo "tmux: ${SESSION} missing"
    fi

    if [[ -f "${LOG}" ]]; then
      stat -c 'log_mtime: %y, size: %s bytes' "${LOG}"
      grep 'simulator_pid=' "${LOG}" | tail -n 1 || true
      grep 'layer_num' "${LOG}" | tail -n 1 || true
      grep 'NS3 progress' "${LOG}" | tail -n 1 || true
      grep -E '\[fullrun.*\] (exit=|interrupted_or_exited)' "${LOG}" | tail -n 3 || true
      sim_pid="$(grep 'simulator_pid=' "${LOG}" | tail -n 1 | sed -E 's/.*simulator_pid=([0-9]+).*/\1/')"
      if [[ "${sim_pid}" =~ ^[0-9]+$ ]]; then
        ps -p "${sim_pid}" -o pid,ppid,stat,pcpu,pmem,etime,comm,args || true
      fi
    else
      echo "log: ${LOG} missing"
    fi

    if [[ -d "${OUT_DIR}" ]]; then
      find "${OUT_DIR}" -maxdepth 1 -type f -printf '%f: %s bytes, mtime: %TY-%Tm-%Td %TH:%TM:%TS %TZ\n' | sort
    else
      echo "out_dir: ${OUT_DIR} missing"
    fi
    echo "next_sleep: ${INTERVAL}s"
    echo
  } >> "${MONITOR_LOG}" 2>&1

  sleep "${INTERVAL}"
done
