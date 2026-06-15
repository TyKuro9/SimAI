# Current Context

## Current Project State

- Project understanding phase is complete for README/config/build/entry/core modules.
- Non-vidur architecture has been documented in `docs/Architecture.md`, `docs/Modules.md`, and `docs/Flow.md`.
- `.ai/` now serves as the persistent maintenance knowledge base.
- There are pre-existing uncommitted changes in the worktree outside this knowledge-base work. Treat them as user-owned unless explicitly told otherwise.
- FlowSim is an important backend path, but its source and binary live in `/home/zty/Topo/m4/SimAI`; this project invokes it through scripts.
- Local SimAI/FlowSim build and run paths should not require `sudo`; if historical artifacts are owned by `nobody`/`root`, use `scripts/fix_local_permissions.sh` once to repair targeted build, binary, NS-3 `extern/network_backend`, and external FlowSim `build/simai_flowsim` paths.

## Current Focus Modules

- `build_and_scripts`: because project execution is script-driven and contains absolute paths.
- `flowsim_backend`: because it is easy to confuse with NS-3 but is a distinct backend.
- `ns3_backend`: high-fidelity simulation path.
- `system` and `collective_mocknccl`: shared upper-stack logic.

## Later Development Direction

- Keep `.ai/` updated before and after changes.
- When modifying a backend, verify whether the change affects common `Sys`/MockNCCL semantics or only backend callback behavior.
- When changing experiment scripts, preserve topology/workload/output conventions and document any absolute path changes.
- When adding support for new topology/workload variants, update `topology_config_results.md` and related backend docs.

## Current Open Questions

- Should FlowSim eventually be vendored or submoduled into `SimAI_TyKuro9`, or remain an external dependency on `/home/zty/Topo/m4/SimAI`?
- Should absolute paths in scripts be parameterized for portability?
- Should `scripts/fix_local_permissions.sh` eventually cover additional backend build directories if analytical/physical builds hit the same ownership issue?
- Should vidur-related paths remain excluded from this knowledge base until a dedicated analysis request?

## Development Rule Reminder

For future development requests:

1. Read `.ai/current_context.md`.
2. Read relevant `.ai/modules/*.md`.
3. Check source only if needed.
4. Propose/choose implementation plan.
5. Implement.
6. Update `.ai/current_context.md`, `.ai/decisions.md`, and relevant module docs.
