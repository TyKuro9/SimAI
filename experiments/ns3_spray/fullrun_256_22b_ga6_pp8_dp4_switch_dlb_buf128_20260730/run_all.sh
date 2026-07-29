#!/usr/bin/env bash

set -uo pipefail

ROOT="/home/zty/Topo/SimAI_TyKuro9_spray_packet_dlb"
EXP_ROOT="${ROOT}/experiments/ns3_spray/fullrun_256_22b_ga6_pp8_dp4_switch_dlb_buf128_20260730"
RUNNER="${ROOT}/scripts/run_ns3_ecmp_spray_256.py"
BINARY="${ROOT}/bin/SimAI_simulator"

DENSE_WORKLOAD="${ROOT}/my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs24-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-True-GA6.txt"
MOE_WORKLOAD="${ROOT}/my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep4-gbs24-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True-GA6.txt"

POLICY="spray_switch_dlb"
THREADS="${THREADS:-4}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-43200}"
FCT_IDLE_GRACE_SECONDS="${FCT_IDLE_GRACE_SECONDS:-15}"
TOPOLOGIES=(Zcube HPN DeepSeek P2R)

mkdir -p "${EXP_ROOT}/runs"

{
  printf 'started_at=%s\n' "$(date --iso-8601=seconds)"
  printf 'root=%s\n' "${ROOT}"
  printf 'policy=%s\n' "${POLICY}"
  printf 'threads_per_run=%s\n' "${THREADS}"
  printf 'parallel_runs=%s\n' "$((2 * ${#TOPOLOGIES[@]}))"
  printf 'buffer_size_mib=128\n'
  printf 'pxn_policy=off\n'
  printf 'send_window=enabled\n'
  printf 'selective_lane_credit=enabled\n'
  printf 'link_delay_us=5\n'
  printf 'nvlink_delay_us=1\n'
  printf 'timeout_seconds=%s\n' "${TIMEOUT_SECONDS}"
  printf 'fct_idle_grace_seconds=%s\n' "${FCT_IDLE_GRACE_SECONDS}"
  printf 'dense_workload=%s\n' "${DENSE_WORKLOAD}"
  printf 'moe_workload=%s\n' "${MOE_WORKLOAD}"
  printf 'binary=%s\n' "$(readlink -f "${BINARY}")"
  git -C "${ROOT}" rev-parse HEAD | sed 's/^/git_commit=/'
  sha256sum "${DENSE_WORKLOAD}" "${MOE_WORKLOAD}" | sed 's/^/workload_sha256=/'
} > "${EXP_ROOT}/run_manifest.txt"

run_task() {
  local workload_kind="$1"
  local topology="$2"
  local workload="$3"
  local task_root="${EXP_ROOT}/runs/${workload_kind}/${topology}"
  local run_dir="${task_root}/${topology}/${POLICY}"
  local launcher_log="${task_root}/launcher.log"
  local runner_rc=0
  local archive_rc=0

  mkdir -p "${task_root}"
  printf '%s\n' "$(date --iso-8601=seconds)" > "${task_root}/started_at.txt"

  {
    printf '[START] workload=%s topology=%s at=%s\n' \
      "${workload_kind}" "${topology}" "$(date --iso-8601=seconds)"
    python3 "${RUNNER}" \
      --binary "${BINARY}" \
      --workload "${workload}" \
      --output-dir "${task_root}" \
      --topologies "${topology}" \
      --policies "${POLICY}" \
      --threads "${THREADS}" \
      --buffer-size-mib 128 \
      --pxn-policy off \
      --timeout "${TIMEOUT_SECONDS}" \
      --fct-only \
      --fct-idle-grace-seconds "${FCT_IDLE_GRACE_SECONDS}"
    runner_rc=$?
    printf '[RUNNER_EXIT] rc=%s at=%s\n' \
      "${runner_rc}" "$(date --iso-8601=seconds)"

    if [[ -s "${run_dir}/fct.txt" ]]; then
      gzip -9 -f "${run_dir}/fct.txt"
      archive_rc=$?
      if [[ "${archive_rc}" -eq 0 ]]; then
        gzip -t "${run_dir}/fct.txt.gz"
        archive_rc=$?
      fi
      if [[ "${archive_rc}" -eq 0 ]]; then
        sha256sum "${run_dir}/fct.txt.gz" > "${run_dir}/fct.txt.gz.sha256"
        printf '[FCT_ARCHIVE] status=success bytes=%s path=%s\n' \
          "$(stat -c %s "${run_dir}/fct.txt.gz")" \
          "${run_dir}/fct.txt.gz"
      else
        printf '[FCT_ARCHIVE] status=failed rc=%s\n' "${archive_rc}"
      fi
    else
      archive_rc=1
      printf '[FCT_ARCHIVE] status=missing path=%s\n' "${run_dir}/fct.txt"
    fi

    printf '[DONE] workload=%s topology=%s runner_rc=%s archive_rc=%s at=%s\n' \
      "${workload_kind}" "${topology}" "${runner_rc}" "${archive_rc}" \
      "$(date --iso-8601=seconds)"
  } >> "${launcher_log}" 2>&1

  printf '%s\n' "${runner_rc}" > "${task_root}/runner.exit"
  printf '%s\n' "${archive_rc}" > "${task_root}/archive.exit"
  printf '%s\n' "$(date --iso-8601=seconds)" > "${task_root}/finished_at.txt"

  if [[ "${runner_rc}" -ne 0 || "${archive_rc}" -ne 0 ]]; then
    return 1
  fi
  return 0
}

pids=()
names=()

for topology in "${TOPOLOGIES[@]}"; do
  run_task Dense "${topology}" "${DENSE_WORKLOAD}" &
  pids+=("$!")
  names+=("Dense/${topology}")

  run_task MoE "${topology}" "${MOE_WORKLOAD}" &
  pids+=("$!")
  names+=("MoE/${topology}")
done

overall_rc=0
for index in "${!pids[@]}"; do
  if wait "${pids[$index]}"; then
    printf '[COMPLETE] %s\n' "${names[$index]}"
  else
    printf '[FAILED] %s\n' "${names[$index]}"
    overall_rc=1
  fi
done

printf '%s\n' "${overall_rc}" > "${EXP_ROOT}/overall.exit"
printf '%s\n' "$(date --iso-8601=seconds)" > "${EXP_ROOT}/finished_at.txt"
exit "${overall_rc}"
