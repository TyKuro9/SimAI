/*
 * Copyright (c) 2024, Alibaba Group;
 * Licensed under the Apache License, Version 2.0.
 */

#ifndef __HTSIM_NETWORK_HH__
#define __HTSIM_NETWORK_HH__

#include "astra-sim/system/AstraNetworkAPI.hh"
#include "astra-sim/system/Common.hh"

#include <cstddef>
#include <cstdint>
#include <functional>
#include <map>
#include <queue>
#include <string>
#include <utility>
#include <vector>

struct htsim_task {
  int src;
  int dest;
  int type;
  uint64_t count;
  void* fun_arg;
  void (*msg_handler)(void* fun_arg);
  double schTime;
};

class HtsimNetwork : public AstraSim::AstraNetworkAPI {
 public:
  HtsimNetwork(int rank, int npu_offset);
  ~HtsimNetwork() override;

  AstraSim::AstraNetworkAPI::BackendType get_backend_type() override;
  int sim_comm_size(AstraSim::sim_comm comm, int* size) override;
  int sim_finish() override;
  double sim_time_resolution() override;
  int sim_init(AstraSim::AstraMemoryAPI* MEM) override;
  AstraSim::timespec_t sim_get_time() override;
  void sim_schedule(
      AstraSim::timespec_t delta,
      void (*fun_ptr)(void* fun_arg),
      void* fun_arg) override;
  int sim_send(
      void* buffer,
      uint64_t count,
      int type,
      int dst,
      int tag,
      AstraSim::sim_request* request,
      void (*msg_handler)(void* fun_arg),
      void* fun_arg) override;
  int sim_recv(
      void* buffer,
      uint64_t count,
      int type,
      int src,
      int tag,
      AstraSim::sim_request* request,
      void (*msg_handler)(void* fun_arg),
      void* fun_arg) override;
  void pass_front_end_report(AstraSim::AstraSimDataAPI astraSimDataAPI)
      override;

 private:
  int npu_offset;
};

bool htsim_load_topology_summary(const std::string& topology_file);
void htsim_set_result_dir(const std::string& result_dir);
void htsim_set_route_strategy(const std::string& strategy);
const std::string& htsim_route_strategy();
bool htsim_packet_level_enabled();
void htsim_schedule_flow_completion(
    int src,
    int dst,
    uint64_t count,
    const AstraSim::ncclFlowTag& flowTag);
bool htsim_run(
    const std::function<void()>& watchdog_callback = nullptr,
    const std::function<bool()>& stall_allowed_callback = nullptr);
void htsim_stop();
void htsim_destroy();
void htsim_dump_pending_state(std::size_t limit = 16);
std::size_t htsim_recover_stalled_flows(std::size_t limit = 0);
std::size_t htsim_prepare_final_recovery();
uint64_t htsim_completed_flow_count();

extern std::map<std::pair<std::pair<int, int>, int>, AstraSim::ncclFlowTag>
    receiver_pending_queue;
extern std::map<std::pair<int, std::pair<int, int>>, htsim_task> expeRecvHash;
extern std::map<std::pair<int, std::pair<int, int>>, uint64_t> recvHash;
extern std::map<std::pair<int, std::pair<int, int>>, htsim_task> sentHash;
extern std::map<std::pair<int, int>, int64_t> nodeHash;
extern uint32_t node_num;
extern uint32_t switch_num;
extern uint32_t link_num;
extern uint32_t nvswitch_num;
extern uint32_t gpus_per_server;
extern GPUType gpu_type;
extern std::vector<int> NVswitchs;

#endif
