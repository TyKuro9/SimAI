# Known Issues and Technical Debt

## Known Issues

- FlowSim binary/source is external to this project, but experiment scripts depend on `/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim`.
- Several experiment scripts contain absolute paths, reducing portability.
- The worktree contains many pre-existing uncommitted and untracked files; future changes must avoid reverting user-owned work.
- Some scripts and files use inconsistent spelling, e.g. `simulaiton_order.sh`.
- FlowSim and NS-3 share upper-stack concepts but use different backend completion semantics; confusing them can lead to incorrect analysis.
- `myconfig` files contain output paths that may be machine-specific.
- FlowSim output uses NS-3-like `fct.txt` format, which is useful but may hide semantic differences between flow/chunk completion and RDMA QP completion.

## Technical Debt

- Centralize backend selection and binary paths.
- Parameterize paths like `/home/zty/Topo/m4/SimAI`.
- Clarify ownership boundary between `SimAI_TyKuro9` and external m4 FlowSim project.
- Add a lightweight validation script for workload/topology/config/output path consistency.
- Add documentation for expected result directory layouts.
- Consider adding a local wrapper that checks FlowSim binary version/source commit.

## Future Optimization Ideas

- Introduce a config file for experiment matrix definitions instead of hardcoded bash arrays.
- Generate batch scripts from declarative topology/workload matrices.
- Add comparison reports between FlowSim and NS-3 outputs for the same workload/topology.
- Add knowledge-base update checklist to PR or commit workflow.

