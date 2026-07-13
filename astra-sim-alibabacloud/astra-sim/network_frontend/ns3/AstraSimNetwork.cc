/* 
*Copyright (c) 2024, Alibaba Group;
*Licensed under the Apache License, Version 2.0 (the "License");
*you may not use this file except in compliance with the License.
*You may obtain a copy of the License at

*   http://www.apache.org/licenses/LICENSE-2.0

*Unless required by applicable law or agreed to in writing, software
*distributed under the License is distributed on an "AS IS" BASIS,
*WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
*See the License for the specific language governing permissions and
*limitations under the License.
*/

#include "astra-sim/system/AstraNetworkAPI.hh"
#include "astra-sim/system/Sys.hh"
#include "astra-sim/system/RecvPacketEventHadndlerData.hh"
#include "astra-sim/system/Common.hh"
#include "astra-sim/system/MockNcclLog.h"
#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/csma-module.h"
#include "ns3/internet-module.h"
#include "ns3/network-module.h"
#include "entry.h"
#include <algorithm>
#include <execinfo.h>
#include <fstream>
#include <functional>
#include <iostream>
#include <queue>
#include <cstdlib>
#include <stdio.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <string>
#include <thread>
#include <unistd.h>
#include <vector>
#ifdef NS3_MTP
#include "ns3/mtp-interface.h"
#endif
#ifdef NS3_MPI
#include "ns3/mpi-interface.h"
#include <mpi.h>
#endif

#define DEFAULT_RESULT_PATH "./experiments/ns3_results/csv/"

using namespace std;
using namespace ns3;

extern std::map<ReceiverPendingKey, ReceiverPendingArrivals>
    receiver_pending_queue;
extern uint32_t node_num, switch_num, link_num, trace_num, nvswitch_num, gpus_per_server;
extern GPUType gpu_type;
extern std::vector<int>NVswitchs;

int ns3_treeflow_tag(
    const AstraSim::ncclFlowTag& flow_tag,
    int api_tag) {
  return flow_tag.tag_id < 0 ? api_tag : flow_tag.tag_id;
}

struct sim_event {
  void *buffer;
  uint64_t count;
  int type;
  int dst;
  int tag;
  string fnType;
};

class ASTRASimNetwork : public AstraSim::AstraNetworkAPI {
private:
  int npu_offset;

public:
  queue<sim_event> sim_event_queue;
  ASTRASimNetwork(int rank, int npu_offset) : AstraNetworkAPI(rank) {
    this->npu_offset = npu_offset;
  }
  ~ASTRASimNetwork() {}
  int sim_comm_size(AstraSim::sim_comm comm, int *size) { return 0; }
  int sim_finish() {
    for (auto it = nodeHash.begin(); it != nodeHash.end(); it++) {
      pair<int, int> p = it->first;
      if (p.second == 0) {
        std::cout << "sim_finish on sent, " << " Thread id: " << pthread_self() << std::endl;
        cout << "All data sent from node " << p.first << " is " << it->second
             << "\n";
      } else {
        std::cout << "sim_finish on received, " << " Thread id: " << pthread_self() << std::endl;
        cout << "All data received by node " << p.first << " is " << it->second
             << "\n";
      }
    }
    // Gracefully stop NS3 so AstraSim can finish report/csv flushing.
    Simulator::Stop();
    return 0;
  }
  double sim_time_resolution() { return 0; }
  int sim_init(AstraSim::AstraMemoryAPI *MEM) { return 0; }
  AstraSim::timespec_t sim_get_time() {
    AstraSim::timespec_t timeSpec;
    timeSpec.time_val = Simulator::Now().GetNanoSeconds();
    return timeSpec;
  }
  virtual void sim_schedule(AstraSim::timespec_t delta,
                            void (*fun_ptr)(void *fun_arg), void *fun_arg) {
    task1 t;
    t.type = 2;
    t.fun_arg = fun_arg;
    t.msg_handler = fun_ptr;
    t.schTime = delta.time_val;
    Simulator::Schedule(NanoSeconds(t.schTime), t.msg_handler, t.fun_arg);
    return;
  }
  virtual int sim_send(void *buffer,   
                       uint64_t count, 
                       int type,       
                       int dst,
                       int tag,                       
                       AstraSim::sim_request *request, 
                       void (*msg_handler)(void *fun_arg), void *fun_arg) {
    dst += npu_offset;
    task1 t;
    t.src = rank;
    t.dest = dst;
    t.count = count;
    t.type = 0;
    t.fun_arg = fun_arg;
    t.msg_handler = msg_handler;
    int network_tag;
    {
      #ifdef NS3_MTP
      MtpInterface::explicitCriticalSection cs;
      #endif
      network_tag = ns3_treeflow_tag(request->flowTag, tag);
      if (request->flowTag.tag_id >= 0) {
        request->flowTag.tag_id = network_tag;
      }
      sentHash[make_pair(network_tag, make_pair(t.src, t.dest))] = t;
      #ifdef NS3_MTP
      cs.ExitSection();
      #endif
    }
    SendFlow(rank, dst, count, msg_handler, fun_arg, network_tag, request);
    return 0;
  }
  virtual int sim_recv(void *buffer, uint64_t count, int type, int src, int tag,
                       AstraSim::sim_request *request,
                       void (*msg_handler)(void *fun_arg), void *fun_arg) {
    #ifdef NS3_MTP
    MtpInterface::explicitCriticalSection cs;
    #endif
    MockNcclLog* NcclLog = MockNcclLog::getInstance();
    AstraSim::ncclFlowTag flowTag = request->flowTag;
    src += npu_offset;
    task1 t;
    t.src = src;
    t.dest = rank;
    t.count = count;
    t.type = 1;
    t.fun_arg = fun_arg;
    t.msg_handler = msg_handler;
    AstraSim::RecvPacketEventHadndlerData* ehd = (AstraSim::RecvPacketEventHadndlerData*) t.fun_arg;
#ifdef NS3_MTP
    if (ehd != nullptr && ehd->owner != nullptr) {
      ehd->owner->pending_receives.fetch_add(1, std::memory_order_acq_rel);
    }
#endif
    AstraSim::EventType event = ehd->event;
    tag = ns3_treeflow_tag(ehd->flowTag, tag);
    if (ehd->flowTag.tag_id >= 0) {
      ehd->flowTag.tag_id = tag;
    }
    NcclLog->writeLog(NcclLogLevel::DEBUG,"[Receive event registration] src %d sim_recv on rank %d tag_id %d channdl id %d",src,rank,tag,ehd->flowTag.channel_id);
    
    auto recv_key = make_pair(tag, make_pair(t.src, t.dest));
    auto arrived = recvHash.find(recv_key);
    auto pending = receiver_pending_queue.find(
        make_pair(make_pair(t.dest, t.src), tag));
    bool exact_arrival_compatible =
        arrived != recvHash.end() &&
        pending != receiver_pending_queue.end() &&
        !pending->second.empty();
    if (exact_arrival_compatible) {
      uint64_t arrived_count = arrived->second;
      AstraSim::ncclFlowTag pending_tag;
      uint64_t consumed_count = std::min(arrived_count, t.count);
      if (!consume_receiver_pending_arrival(
              t.src,
              t.dest,
              tag,
              consumed_count,
              pending_tag)) {
        enqueue_expected_receive(recv_key, t);
        #ifdef NS3_MTP
        cs.ExitSection();
        #endif
        goto sim_recv_end_section;
      }
      if (arrived_count >= t.count) {
        assert(ehd->flowTag.child_flow_id == -1 && ehd->flowTag.current_flow_id == -1);
        ehd->flowTag = pending_tag;
        #ifdef NS3_MTP
        cs.ExitSection();
        #endif
        dispatch_receiver_callback(t);
        goto sim_recv_end_section;
      }
      t.count -= arrived_count;
      enqueue_expected_receive(recv_key, t);
    } else {
      enqueue_expected_receive(recv_key, t);
      NcclLog->writeLog(NcclLogLevel::DEBUG," [Packet arrived late, registering] recvHash do not find expeRecvHash.push make src  %d dest  %d t.count:  %llu channel_id  %d current_flow_id  %d",t.src,t.dest,t.count,tag,flowTag.current_flow_id);
    }
    #ifdef NS3_MTP
    cs.ExitSection();
    #endif

sim_recv_end_section:    
    return 0;
  }
  void handleEvent(int dst, int cnt) {
  }
};

struct user_param {
  int thread;
  string workload;
  string network_topo;
  string network_conf;
  string result_dir;
  user_param() {
    thread = 1;
    workload = "";
    network_topo = "";
    network_conf = "";
    result_dir = DEFAULT_RESULT_PATH;
  };
  ~user_param(){};
};

static string NormalizeResultDir(string path) {
  if (path.empty()) {
    return DEFAULT_RESULT_PATH;
  }
  if (path.back() != '/') {
    path.push_back('/');
  }
  return path;
}

static bool EnsureResultDir(const string& path) {
  string command = "mkdir -p \"" + path + "\"";
  int ret = system(command.c_str());
  return ret == 0;
}

static int user_param_prase(int argc,char * argv[],struct user_param* user_param){
  int opt;
  while ((opt = getopt(argc,argv,"ht:w:g:s:n:c:o:"))!=-1){
    switch (opt)
    {
    case 'h':
      /* code */
      std::cout<<"-t    number of threads,default 1"<<std::endl;
      std::cout<<"-w    workloads default none "<<std::endl;
      std::cout<<"-n    network topo"<<std::endl;
      std::cout<<"-c    network_conf"<<std::endl;
      std::cout<<"-o    result directory for EndToEnd.csv"<<std::endl;
      return 1;
      break;
    case 't':
      user_param->thread = stoi(optarg);
      break;
    case 'w':
      user_param->workload = optarg;
      break;
    case 'n':
      user_param->network_topo = optarg;
      break;
    case 'c':
      user_param->network_conf = optarg;
      break;
    case 'o':
      user_param->result_dir = NormalizeResultDir(optarg);
      break;
    default:
      std::cerr<<"-h    help message"<<std::endl;
      return 1;
    }
  }
  return 0 ;
}

int main(int argc, char *argv[]) {
  struct user_param user_param;
  MockNcclLog::set_log_name("SimAI.log");
  MockNcclLog* NcclLog = MockNcclLog::getInstance();
  NcclLog->writeLog(NcclLogLevel::INFO," init SimAI.log ");
  if(user_param_prase(argc,argv,&user_param)){
    return 0;
  }
  user_param.result_dir = NormalizeResultDir(user_param.result_dir);
  if (!EnsureResultDir(user_param.result_dir)) {
    std::cerr << "failed to create result directory: " << user_param.result_dir << std::endl;
    return 1;
  }
  #ifdef NS3_MTP
  MtpInterface::Enable(user_param.thread);
  #endif
  
  main1(user_param.network_topo,user_param.network_conf);
  int gpu_num = node_num - nvswitch_num - switch_num;
  int nodes_num = gpu_num;

  std::map<int, int> node2nvswitch; 
  for(int i = 0; i < gpu_num; ++ i) {
    node2nvswitch[i] = gpu_num + i / gpus_per_server;
  }
  for(int i = gpu_num; i < gpu_num + nvswitch_num; ++ i){
    node2nvswitch[i] = i;
    NVswitchs.push_back(i);
  } 

  LogComponentEnable("OnOffApplication", LOG_LEVEL_INFO);
  LogComponentEnable("PacketSink", LOG_LEVEL_INFO);
  LogComponentEnable("GENERIC_SIMULATION", LOG_LEVEL_INFO);

  std::vector<ASTRASimNetwork *> networks(nodes_num, nullptr);
  std::vector<AstraSim::Sys *> systems(nodes_num, nullptr);

  for (int j = 0; j < nodes_num; j++) {
    networks[j] =
        new ASTRASimNetwork(j ,0);
    systems[j ] = new AstraSim::Sys(
        networks[j], 
        nullptr,                  
        j,                        
        0,               
        1,                        
        {gpu_num},
        {1},          
        "", 
        user_param.workload, 
        1, 
        1,          
        1,          
        1,
        0,                 
        user_param.result_dir, 
        "test1",            
        true,               
        false,               
        gpu_type,
        {gpu_num},
        NVswitchs,
        gpus_per_server
    );
    systems[j ]->nvswitch_id = node2nvswitch[j];
    systems[j ]->num_gpus = gpu_num;
  }
  for (int i = 0; i < nodes_num; i++) {
    systems[i]->workload->fire();
  }
  std::cout << "simulator run " << std::endl;

  // Stop time must be configured before Run().
  Simulator::Stop(Seconds(2000000000));
  auto simulation_complete = [&systems]() {
    if (systems.empty() || systems[0] == nullptr ||
        !systems[0]->workload_reported) {
      return false;
    }
    bool network_idle = false;
    {
      #ifdef NS3_MTP
      MtpInterface::explicitCriticalSection cs;
      #endif
      network_idle = sender_src_port_map.empty() &&
          sentHash.empty() &&
          waiting_to_sent_callback.empty() &&
          waiting_to_notify_receiver.empty() &&
          recvHash.empty() &&
          expeRecvHash.empty() &&
          receiver_pending_queue.empty();
      #ifdef NS3_MTP
      cs.ExitSection();
      #endif
    }
    if (!network_idle) {
      return false;
    }
    return std::all_of(
        systems.begin(), systems.end(), [](const AstraSim::Sys* system) {
          return system != nullptr &&
              system->streams_finished == system->streams_injected &&
              system->total_running_streams == 0;
        });
  };
  auto run_in_system_context = [](
                                   AstraSim::Sys* system,
                                   const std::function<int()>& action) {
    #ifdef NS3_MTP
    auto* previous_system = MtpInterface::GetSystem();
    uint32_t previous_system_id = previous_system == nullptr
        ? 0
        : previous_system->GetSystemId();
    uint32_t target_system_id =
        NodeList::GetNode(system->id)->GetSystemId();
    MtpInterface::SetSystem(target_system_id);
    int result = action();
    MtpInterface::SetSystem(previous_system_id);
    return result;
    #else
    return action();
    #endif
  };
  std::function<void()> final_drain_pump;
  final_drain_pump = [
                         &systems,
                         &simulation_complete,
                         &run_in_system_context,
                         &final_drain_pump]() {
    if (simulation_complete()) {
      Simulator::Stop();
      return;
    }
    bool waiting_for_final_streams = !systems.empty() &&
        systems[0] != nullptr && systems[0]->workload != nullptr &&
        systems[0]->workload->current_state ==
            AstraSim::Workload::LoopState::Wait_For_Sim_Finish;
    static std::tuple<size_t, size_t, size_t> last_reconcile_snapshot =
        std::make_tuple(
            static_cast<size_t>(-1),
            static_cast<size_t>(-1),
            static_cast<size_t>(-1));
    bool network_quiescent = false;
    std::tuple<size_t, size_t, size_t> reconcile_snapshot;
    {
      #ifdef NS3_MTP
      MtpInterface::explicitCriticalSection cs;
      #endif
      network_quiescent = sender_src_port_map.empty() &&
          waiting_to_notify_receiver.empty();
      reconcile_snapshot = std::make_tuple(
          recvHash.size(),
          expected_receive_count(),
          receiver_pending_queue.size());
      #ifdef NS3_MTP
      cs.ExitSection();
      #endif
    }
    int reconciled_receives = 0;
    if (network_quiescent &&
        reconcile_snapshot != last_reconcile_snapshot) {
      last_reconcile_snapshot = reconcile_snapshot;
      reconciled_receives = reconcile_pending_receives();
    }
    int drained_streams = 0;
    int scheduled_streams = 0;
    int started_streams = 0;
    for (auto* system : systems) {
      if (system != nullptr) {
        drained_streams += run_in_system_context(system, [system]() {
          return system->drain_finished_streams();
        });
      }
    }
    for (auto* system : systems) {
      if (system != nullptr) {
        scheduled_streams += run_in_system_context(system, [system]() {
          return system->schedule_ready_list_streams();
        });
      }
    }
    for (auto* system : systems) {
      if (system != nullptr) {
        started_streams += run_in_system_context(system, [system]() {
          return system->start_ready_streams();
        });
      }
    }
    int progressed_streams =
        reconciled_receives + drained_streams + scheduled_streams +
        started_streams;
    static int stagnant_pumps = 0;
    if (progressed_streams == 0) {
      stagnant_pumps++;
      if (stagnant_pumps == 1000) {
        std::cerr << "[NS3] Final drain receive mismatch snapshot"
                  << std::endl;
        dump_receive_mismatch(12);
      }
    } else {
      stagnant_pumps = 0;
    }
    if (progressed_streams > 0) {
      std::cout << "[NS3] "
                << (waiting_for_final_streams ? "Final drain" : "Recovery")
                << " pump: reconciled " << reconciled_receives
                << ", drained " << drained_streams
                << ", scheduled " << scheduled_streams
                << ", started " << started_streams << std::endl;
    }
    if (simulation_complete()) {
      Simulator::Stop();
      return;
    }
    Simulator::Schedule(
        waiting_for_final_streams || progressed_streams > 0
            ? MicroSeconds(100)
            : MilliSeconds(10),
        final_drain_pump);
  };
  Simulator::Schedule(MilliSeconds(10), final_drain_pump);
  bool final_drain_failed = false;
  Simulator::Run();
  while (!simulation_complete()) {
    int drained_streams = 0;
    int scheduled_streams = 0;
    int started_streams = 0;
    for (auto* system : systems) {
      if (system != nullptr) {
        drained_streams += run_in_system_context(system, [system]() {
          return system->drain_finished_streams();
        });
      }
    }
    if (drained_streams > 0) {
      std::cout << "[NS3] Drained " << drained_streams
                << " finished streams after simulator event queue became empty"
                << std::endl;
      Simulator::Run();
    }
    for (auto* system : systems) {
      if (system != nullptr) {
        scheduled_streams += run_in_system_context(system, [system]() {
          return system->schedule_ready_list_streams();
        });
      }
    }
    if (scheduled_streams > 0) {
      std::cout << "[NS3] Scheduled " << scheduled_streams
                << " ready-list streams after simulator event queue became empty"
                << std::endl;
      Simulator::Run();
    }
    for (auto* system : systems) {
      if (system != nullptr) {
        started_streams += run_in_system_context(system, [system]() {
          return system->start_ready_streams();
        });
      }
    }
    if (started_streams > 0) {
      std::cout << "[NS3] Started " << started_streams
                << " ready streams after simulator event queue became empty"
                << std::endl;
      Simulator::Run();
    }
    if (simulation_complete()) {
      break;
    }
    if (drained_streams == 0 && scheduled_streams == 0 &&
        started_streams == 0) {
      std::cerr << "[NS3] Final drain stalled before workload report"
                << std::endl;
      if (!systems.empty() && systems[0] != nullptr) {
        systems[0]->dump_unfinished_streams(12);
      }
      final_drain_failed = true;
      break;
    }
  }

  std::cout << "[NS3 flow accounting] receiver_notifications="
            << receiver_notified_logical_flows.size()
            << " receiver_callbacks="
            << receiver_callbacks_dispatched.load(std::memory_order_relaxed)
            << " sender_callbacks="
            << sender_callbacks_dispatched.load(std::memory_order_relaxed)
            << " sender_active=" << sender_src_port_map.size()
            << " receiver_waiting=" << waiting_to_notify_receiver.size()
            << " recv_pending=" << recvHash.size()
            << " expected_pending=" << expected_receive_count() << std::endl;

  Simulator::Destroy();
  
  #ifdef NS3_MPI
  MpiInterface::Disable ();
  #endif
  return final_drain_failed ? 2 : 0;
}
