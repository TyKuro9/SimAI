# Flow

## Build Flow

### Analytical

```text
./scripts/build.sh -c analytical
  -> astra-sim-alibabacloud/build.sh -c analytical
  -> build/simai_analytical/CMakeLists.txt
  -> AstraSim library + network_frontend/analytical
  -> bin/SimAI_analytical
```

### NS-3

```text
./scripts/build.sh -c ns3
  -> copy ns-3-alibabacloud into astra-sim extern backend
  -> astra-sim-alibabacloud/build.sh -c ns3
  -> NS-3 scratch binary
  -> bin/SimAI_simulator
```

### Physical/RDMA

```text
./scripts/build.sh -c phy
  -> astra-sim-alibabacloud/build.sh -c phy
  -> build/simai_phy/CMakeLists.txt
  -> MPI/libibverbs linked binary
  -> bin/SimAI_phynet
```

### FlowSim

FlowSim is currently built outside this project:

```text
cd /home/zty/Topo/m4/SimAI
./scripts/build.sh -c flowsim
  -> astra-sim-alibabacloud/build/simai_flowsim
  -> astra-sim/network_frontend/flowsim
  -> bin/SimAI_flowsim
```

## Startup Flows

### Analytical

```text
AnalyticalAstra.cc::main
  -> UserParam::parse()
  -> construct GPU/NVSwitch dimensions
  -> new AnalyticalNetWork
  -> new AstraSim::Sys
  -> workload->fire()
  -> AnaSim::Run()
```

### NS-3

```text
AstraSimNetwork.cc::main
  -> parse -t/-w/-n/-c/-o
  -> main1(network_topo, network_conf)
       -> ReadConf()
       -> SetConfig()
       -> SetupNetwork(qp_finish, send_finish)
  -> create ASTRASimNetwork + Sys for each node
  -> workload->fire() for each system
  -> ns3::Simulator::Run()
```

### FlowSim

```text
run_256moe_flowsim.sh
  -> choose workload/topology/output
  -> /home/zty/Topo/m4/SimAI/bin/SimAI_flowsim -t ... -w ... -n ... -o ...
  -> FlowsimAstra.cc::main
       -> RoutingFramework::ParseTopology()
       -> PrecalculateRoutingTables()
       -> PrecalculateFlowPathsForFlowSim()
       -> construct_fat_tree_topology()
       -> create FlowSimNetWork + Sys for each node
       -> FlowSim::Init(EventQueue, Topology)
       -> workload->fire()
       -> FlowSim::Run()
```

### Physical/RDMA

```text
SimAiMain.cc::main
  -> BootStrapNet()
  -> optional FlowPhyRdma::ibv_init()
  -> set_simai_network_callback()
  -> new SimAiPhyNetWork
  -> new AstraSim::Sys
  -> workload->fire()
  -> PhyNetSim::Run()
  -> notify_all_thread_finished()
  -> MPI_Finalize()
```

## Common Workload Call Chain

```text
Workload::fire()
  -> Workload::call()
  -> iterate_* based on ParallelismPolicy
  -> Layer::issue_*_comm()
  -> Sys creates/schedules stream and collective algorithm
  -> MockNCCL generates flow model
  -> NcclTreeFlowModel executes dependency graph
  -> Sys::front_end_sim_send / front_end_sim_recv
  -> backend AstraNetworkAPI implementation
  -> callback returns to Layer
  -> Workload::check_for_sim_end()
  -> Workload::report()
```

## Backend Send/Receive Flows

### NS-3 Send

```text
Sys::sim_send()
  -> ASTRASimNetwork::sim_send()
  -> SendFlow()
  -> RdmaClientHelper.Install()
  -> NS-3 RDMA/QBB simulation
  -> send_finish() / qp_finish()
  -> notify sender/receiver
  -> original ASTRA-sim msg_handler
```

### FlowSim Send

```text
Sys::sim_send()
  -> FlowSimNetWork::sim_send()
  -> store sentHash and flow_start_times
  -> FlowSim::Schedule(AS_SEND_LAT)
  -> FlowSim::Send()
       -> RoutingFramework::GetFlowSimPathByNodeIds()
       -> new Chunk(size, route, callback)
       -> Topology::send_with_batching()
       -> update_link_states()
       -> schedule_next_min_completion_set()
  -> flowsim_completion_callback()
  -> WriteFlowFct()
  -> notify_sender_sending_finished()
  -> notify_receiver_packet_arrived()
```

### Receive Matching

Both NS-3 and FlowSim use the same conceptual matching model:

- `expeRecvHash`: receive registered before data arrives.
- `recvHash`: data arrives before receive is registered, or partial bytes remain.
- `receiver_pending_queue`: flow tag arrives before receiver handler data is available.
- `sentHash`: send completion lookup.

## Outputs

- `EndToEnd.csv`: end-to-end workload timing.
- `detailed_<nodes>.csv`: layer-level statistics.
- `*_dimension_utilization_*.csv`: dimension utilization.
- `fct.txt` or `*_fct.txt`: flow completion timing.
- logs under `experiments/*_results` or configured output paths.

