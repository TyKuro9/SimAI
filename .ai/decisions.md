# Decisions

## Decision Log

### 2026-06-15: Establish `.ai` Knowledge Base

- Created `.ai/` as the persistent project knowledge base.
- Purpose: future development should start from `.ai/current_context.md` and relevant module docs instead of rescanning the full repository.
- Rationale: this repository is large, multi-backend, and contains external backend dependencies; persistent context reduces repeated expensive exploration.

### 2026-06-15: Treat FlowSim as a First-Class Backend Path

- FlowSim is documented as distinct from NS-3.
- Current project stores FlowSim experiment scripts, topology/workload inputs, and outputs.
- FlowSim implementation and binary are external under `/home/zty/Topo/m4/SimAI`.
- Rationale: user explicitly clarified that FlowSim is a separate backend analysis tool and must be analyzed alongside NS-3.

### 2026-06-15: Keep Vidur Out of Current Analysis

- Vidur-related content is not analyzed in this knowledge base unless explicitly requested.
- Rationale: original project-understanding request asked to skip vidur-related content.

### 2026-06-15: Do Not Modify Business Code During Knowledge-Base Phase

- Only documentation and `.ai` files are created/updated.
- Rationale: current goal is project understanding, not feature development.

### 2026-06-15: Repair Local Build Permissions Without Sudo Builds

- Added `scripts/fix_local_permissions.sh` to repair ownership and write/execute bits on targeted SimAI/FlowSim build and binary paths.
- Included the NS-3 `astra-sim-alibabacloud/extern/network_backend` path because `scripts/build.sh -c ns3` removes and recreates `ns3-interface`.
- Included the whole external FlowSim `astra-sim-alibabacloud/build/simai_flowsim` subtree because the FlowSim sub-build script creates/removes both `build/` and `result/`.
- Normal SimAI and FlowSim compilation/execution should run as the current user, not through `sudo`.
- The script uses `sudo chown` only for one-time repair of historical artifacts owned by `nobody`, `root`, or another user.
- Rationale: keeping sudo out of build/run commands avoids creating new root-owned artifacts and keeps experiment scripts reproducible for the regular user.

## Ongoing Rule

After each future development change, update:

- `.ai/current_context.md`
- `.ai/decisions.md`
- relevant `.ai/modules/*.md`

Each post-change response should include:

- modification summary
- affected modules
- potential risks
- follow-up recommendations
