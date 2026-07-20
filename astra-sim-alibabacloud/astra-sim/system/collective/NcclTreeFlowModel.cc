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

#ifdef PHY_MTP
#include<mpi.h>
#include "astra-sim/system/PhyMultiThread.hh"
#endif
#include<chrono>

#include "NcclTreeFlowModel.hh"
#include "astra-sim/system/PacketBundle.hh"
#include "astra-sim/system/RecvPacketEventHadndlerData.hh"
#include "astra-sim/system/MockNcclLog.h"
#include <cstdlib>
#ifdef PHY_RDMA
#include "astra-sim/system/SimAiFlowModelRdma.hh"
extern FlowPhyRdma flow_rdma;
#endif


namespace AstraSim {
namespace {
int map_value_or_zero(const std::map<int, int>& values, int key) {
  auto it = values.find(key);
  if (it == values.end()) {
    return 0;
  }
  return it->second;
}

int map_value_or_zero(
    const std::map<std::pair<int, int>, int>& values,
    const std::pair<int, int>& key) {
  auto it = values.find(key);
  if (it == values.end()) {
    return 0;
  }
  return it->second;
}

int packed_treeflow_tag_id(int layer, int stream, int intra) {
  constexpr int kIntraBits = 8;
  constexpr int kStreamBits = 12;
  constexpr int kMaxIntra = (1 << kIntraBits) - 1;
  constexpr int kMaxStream = (1 << kStreamBits) - 1;
  constexpr int kMaxLayer = (1 << (31 - kStreamBits - kIntraBits)) - 1;
  if (layer >= 0 && layer <= kMaxLayer && stream >= 0 &&
      stream <= kMaxStream && intra >= 0 && intra <= kMaxIntra) {
    return (layer << (kStreamBits + kIntraBits)) |
        (stream << kIntraBits) | intra;
  }

  uint32_t hash = 2166136261u;
  auto mix = [&hash](uint32_t value) {
    hash ^= value;
    hash *= 16777619u;
  };
  mix(static_cast<uint32_t>(layer));
  mix(static_cast<uint32_t>(stream));
  mix(static_cast<uint32_t>(intra));
  return static_cast<int>(hash & 0x7fffffffu);
}

#ifdef NS3_MTP
int ns3_treeflow_tag_id(int flow_id) {
  // NS3's sent/receive maps require one tag per logical edge. Chunk ids are
  // reused by multiple ring steps, while MockNcclGroup assigns flow_id from a
  // process-global monotonic counter. Reserve the positive high-bit namespace
  // for NCCL logical flows so they cannot alias ordinary API tags.
  constexpr int kTreeFlowNamespace = 1 << 30;
  if (flow_id < 0 || flow_id >= kTreeFlowNamespace) {
    std::cerr << "NS3 tree-flow id exceeds tag namespace: " << flow_id
              << std::endl;
    std::abort();
  }
  return kTreeFlowNamespace | flow_id;
}
#endif

#ifdef NS3_MTP
std::atomic<int> ns3_tree_flow_trace_count{0};
std::atomic<int> ns3_tree_receive_trace_count{0};
std::atomic<int> ns3_receive_gate_trace_count{0};

bool ns3_receive_gate_trace_enabled() {
  static const bool enabled = []() {
    const char* value = std::getenv("AS_NS3_TREE_GATE_DIAG");
    return value != nullptr && value[0] == '1';
  }();
  return enabled;
}

void trace_ns3_tree_flow(
    const char* phase,
    int rank,
    int layer,
    int stream_num,
    int channel_id,
    const MockNccl::SingleFlow& flow,
    const std::vector<int>& recv_prevs) {
  if (!ns3_receive_gate_trace_enabled() || layer != 0 || stream_num != 49 ||
      flow.chunk_id < 14) {
    return;
  }
  int sequence = ns3_tree_flow_trace_count.fetch_add(1);
  if (sequence >= 500) {
    return;
  }
  std::cerr << "[NS3 tree diag] " << phase
            << " rank=" << rank
            << " layer=" << layer
            << " stream=" << stream_num
            << " channel=" << channel_id
            << " flow=" << flow.flow_id
            << " edge=" << flow.src << "->" << flow.dest
            << " chunk=" << flow.chunk_id << "/" << flow.chunk_count
            << " prev=";
  for (size_t i = 0; i < flow.prev.size(); ++i) {
    if (i != 0) {
      std::cerr << ",";
    }
    std::cerr << flow.prev[i];
  }
  std::cerr << " parent=";
  for (size_t i = 0; i < flow.parent_flow_id.size(); ++i) {
    if (i != 0) {
      std::cerr << ",";
    }
    std::cerr << flow.parent_flow_id[i];
  }
  std::cerr << " child=";
  for (size_t i = 0; i < flow.child_flow_id.size(); ++i) {
    if (i != 0) {
      std::cerr << ",";
    }
    std::cerr << flow.child_flow_id[i];
  }
  std::cerr << " recv_prevs=";
  for (size_t i = 0; i < recv_prevs.size(); ++i) {
    if (i != 0) {
      std::cerr << ",";
    }
    std::cerr << recv_prevs[i];
  }
  std::cerr << std::endl;
}

void trace_ns3_receive_gate(
    const char* phase,
    int rank,
    int layer,
    int stream_num,
    int channel_id,
    const MockNccl::SingleFlow& flow,
    int recv_prev,
    int free_count,
    int recv_remaining) {
  if (!ns3_receive_gate_trace_enabled()) {
    return;
  }
  int sequence = ns3_receive_gate_trace_count.fetch_add(1);
  if (sequence >= 1000) {
    return;
  }
  std::cerr << "[NS3 receive gate] " << phase
            << " rank=" << rank
            << " layer=" << layer
            << " stream=" << stream_num
            << " channel=" << channel_id
            << " flow=" << flow.flow_id
            << " edge=" << flow.src << "->" << flow.dest
            << " chunk=" << flow.chunk_id << "/" << flow.chunk_count
            << " recv_prev=" << recv_prev
            << " free_before_or_after=" << free_count
            << " recv_remaining=" << recv_remaining << std::endl;
}

#endif
} // namespace

std::atomic<bool> NcclTreeFlowModel::g_flow_inCriticalSection(false);
NcclTreeFlowModel::NcclTreeFlowModel(
    ComType type,
    int id,
    int layer_num,
    RingTopology* ring_topology,
    uint64_t data_size,
    RingTopology::Direction direction,
    InjectionPolicy injection_policy,
    bool boost_mode,
    std::shared_ptr<MockNccl::FlowModels> ptr_flow_models,
    int treechannels)
    : Algorithm(layer_num){
  this->start_time = std::chrono::high_resolution_clock::now();
  this->end_time = std::chrono::high_resolution_clock::now();
  this->comType = type;
  this->id = id;
  this->logicalTopology = ring_topology;
  this->data_size = data_size;
  this->nodes_in_ring = ring_topology->get_nodes_in_ring();
  this->parallel_reduce = 1;
  this->toggle = false;
  this->processed = false;
  this->send_back = false;
  this->NPU_to_MA = false;
  this->name = Name::Ring;
  this->enabled = true;
  this->exited.store(false);
  this->m_channels = treechannels;
  this->judge_exit_flag.store(false);
  this->judge_exit_mutex.unlock();
  this->judge_mutex.unlock();
  this->send_packets = 0;
  this->recv_packets = 0;
  pQps = new MockNccl::NcclQps();
  zero_latency_packets = new std::map<int, int>();
  non_zero_latency_packets = new std::map<int, int>();
  if (boost_mode) {
    this->enabled = ring_topology->is_enabled();
  }
  if (ring_topology->dimension == RingTopology::Dimension::Local) {
    transmition = MemBus::Transmition::Fast;
  } else {
    transmition = MemBus::Transmition::Usual;
  }
  if(ptr_flow_models){
    if(id == 0)
    {
      MockNcclLog* NcclLog = MockNcclLog::getInstance();
    }
    for(auto f : *ptr_flow_models) {
      if(f.second.dest == id) {
          this->free_packets[std::make_pair(f.second.channel_id,f.second.src)]++;
          this->_flow_models[f.first] = f.second;
      recv_packets++;
        }
      if(f.second.src == id) {
        if(pQps->peer_qps.count(std::make_pair(f.second.channel_id,std::make_pair(f.second.src,f.second.dest)))==0){
          pQps->peer_qps[std::make_pair(f.second.channel_id,std::make_pair(f.second.src,f.second.dest))]=1;
        }
        NcclTreeFlowModel::FlowCriticalSection cs;
        this->_stream_count[f.second.channel_id] += 1;
        cs.ExitSection();
        assert(this->_flow_models.count(f.first) == 0);
        this->_flow_models[f.first] = f.second;
        send_packets++;
      }
    }
  }
  if (!ptr_flow_models || ptr_flow_models->empty() || m_channels == 0) {
    this->enabled = false;
  }
  for(int channel_id = 0 ;channel_id<m_channels;channel_id++){
    assert(zero_latency_packets->find(channel_id) == zero_latency_packets->end());
    (*zero_latency_packets)[channel_id] = 0;
    assert(non_zero_latency_packets->find(channel_id) == non_zero_latency_packets->end());
    (*non_zero_latency_packets)[channel_id] = 0;
  }
  init_indegree_mapping();
  switch (type) {
    case ComType::All_Reduce:
      this->final_data_size = data_size;
      break;
    case ComType::All_Gather:
      this->final_data_size = data_size * nodes_in_ring;
      break;
    case ComType::Reduce_Scatter:
      this->final_data_size = data_size / nodes_in_ring;
      break;
    case ComType::All_to_All:
      this->final_data_size = data_size;
      break;
    default:;
  }
}

void NcclTreeFlowModel::init_indegree_mapping(){
  MockNccl::FlowModels::iterator tree_it;
  for(tree_it = _flow_models.begin();tree_it != _flow_models.end();tree_it++) {
    if(tree_it->second.src!=id) continue;
    indegree_mapping[tree_it->first.second] = tree_it->second.parent_flow_id.size();
  }
}

int NcclTreeFlowModel::get_non_zero_latency_packets() {
  return (nodes_in_ring - 1) * parallel_reduce * 1;
}

int NcclTreeFlowModel::tag_id_for_flow(
    const MockNccl::SingleFlow& flow_model,
    bool receive) const {
#ifdef NS3_MTP
  (void)receive;
  return ns3_treeflow_tag_id(flow_model.flow_id);
#else
  int stream_tag = stream == nullptr ? layer_num : stream->stream_num;
  int intra_tag =
      flow_model.chunk_count * flow_model.channel_id + flow_model.chunk_id;
  if (receive && flow_model.parent_flow_id.size() != 0 &&
      flow_model.conn_type != "RING") {
    intra_tag += 1;
  }
  return packed_treeflow_tag_id(layer_num, stream_tag, intra_tag);
#endif
}

int NcclTreeFlowModel::tag_id_for_receive_from(
    const MockNccl::SingleFlow& flow_model,
    int recv_prev) const {
#ifdef NS3_MTP
  // Sending one ring step posts the receive for the sibling edge entering
  // this rank in the same step. The dependency parent belongs to the previous
  // step and therefore has a different logical-flow tag.
  const MockNccl::SingleFlow* matched_flow = nullptr;
  for (const auto& entry : _flow_models) {
    const MockNccl::SingleFlow& candidate = entry.second;
    if (candidate.channel_id == flow_model.channel_id &&
        candidate.src == recv_prev && candidate.dest == id &&
        candidate.chunk_id == flow_model.chunk_id &&
        candidate.chunk_count == flow_model.chunk_count &&
        candidate.flow_size == flow_model.flow_size) {
      if (matched_flow != nullptr) {
        matched_flow = nullptr;
        break;
      }
      matched_flow = &candidate;
    }
  }
  if (matched_flow != nullptr) {
    return tag_id_for_flow(*matched_flow, false);
  }
#else
  (void)recv_prev;
#endif

  return tag_id_for_flow(flow_model, true);
}

std::vector<int> NcclTreeFlowModel::acceptable_flow_ids_for_channel(
    int channel_id) const {
  std::vector<int> flow_ids;
  NcclTreeFlowModel::FlowCriticalSection cs;
  for (const auto& entry : _flow_models) {
    if (entry.first.first == channel_id) {
      flow_ids.push_back(entry.first.second);
    }
  }
  return flow_ids;
}

void NcclTreeFlowModel::run(EventType event, CallData* data) {
  BasicEventHandlerData* ehd = (BasicEventHandlerData*)data;
  MockNcclLog* NcclLog = MockNcclLog::getInstance();
  if (event == EventType::General) {
    int channel_id = ehd->channel_id;
    int flow_id = ehd->flow_id;
    #ifndef PHY_MTP
    ready(channel_id, flow_id);
    #else
    phy_ready(channel_id, flow_id);
    #endif
  } else if (event == EventType::PacketReceived) {
    MockNcclLog* NcclLog = MockNcclLog::getInstance();
    RecvPacketEventHadndlerData* rcehd = (RecvPacketEventHadndlerData*)ehd;
    AstraSim::ncclFlowTag flowTag = rcehd->flowTag;
    int received_flow_id = flowTag.current_flow_id;
    int channel_id = flowTag.channel_id;
    std::vector<int> next_flow_list = flowTag.tree_flow_list;
#ifdef NS3_MTP
    bool trace_receive = ns3_receive_gate_trace_enabled() &&
        layer_num == 0 && stream != nullptr &&
        stream->stream_num == 49 && flowTag.tag_id >= 12558 &&
        ns3_tree_receive_trace_count.fetch_add(1) < 500;
    if (trace_receive) {
      std::cerr << "[NS3 tree rx] rank=" << id
                << " stream=" << stream->stream_num
                << " channel=" << channel_id
                << " flow=" << received_flow_id
                << " edge=" << flowTag.sender_node << "->"
                << flowTag.receiver_node
                << " tag=" << flowTag.tag_id
                << " children=";
      for (size_t i = 0; i < next_flow_list.size(); ++i) {
        if (i != 0) {
          std::cerr << ",";
        }
        std::cerr << next_flow_list[i];
      }
      std::cerr << std::endl;
    }
#endif
    int sender_free_packets = 0;
    #ifdef PHY_MTP
    recv_packets--;
    if(!phy_iteratable(channel_id)){
      return;
    }
    #else
    if (recv_packets.load(std::memory_order_acquire) > 0) {
      recv_packets.fetch_sub(1, std::memory_order_acq_rel);
    }
    bool flow_exist = next_flow_list.size() == 0 ? true : false;
    {
      NcclTreeFlowModel::FlowCriticalSection cs;
      for(int i = 0; i < next_flow_list.size(); ++ i) {
        int next_flow_id = next_flow_list[i];
        if (next_flow_id == -1 ||
            _flow_models.find(std::make_pair(channel_id, next_flow_id)) !=
                _flow_models.end()) {
          flow_exist = true;
        } else {
          flow_exist = false;
          break;
        }
      }
    }
    assert(flow_exist == true);
    bool tag = true;
    {
      NcclTreeFlowModel::FlowCriticalSection cs;
      auto sender_key = std::make_pair(channel_id, flowTag.sender_node);
      int free_before = map_value_or_zero(free_packets, sender_key);
      free_packets[sender_key]--;
      sender_free_packets = free_packets[sender_key];
#ifdef NS3_MTP
      if (free_before <= 1 || sender_free_packets < 0) {
        auto received_it = _flow_models.find(
            std::make_pair(channel_id, received_flow_id));
        if (received_it != _flow_models.end()) {
          trace_ns3_receive_gate(
              "packet_received", id, layer_num,
              stream == nullptr ? -1 : stream->stream_num, channel_id,
              received_it->second, flowTag.sender_node, sender_free_packets,
              recv_packets.load(std::memory_order_acquire));
        }
      }
#endif
      for (uint32_t i = 0; i < m_channels; i++) {
        if (map_value_or_zero(_stream_count, i) != 0) {
          tag = false;
          break;
        }
      }
    }
#ifdef NS3_MTP
    // A completed local sender can still receive a parent that unlocks a child.
    if (tag && next_flow_list.empty()) {
#else
    if (tag) {
#endif
      ready(channel_id, -1);
      iteratable(channel_id);
      return;
    }
    #endif
    NcclLog->writeLog(NcclLogLevel::DEBUG,"PacketReceived sender_node:  %d recevier  %d current_flow id:  %d channel_id:  %d tag_id  %d free_packets  %d next_flow_list.size %d",flowTag.sender_node,flowTag.receiver_node,flowTag.current_flow_id,flowTag.channel_id,flowTag.tag_id,sender_free_packets,next_flow_list.size());
    #ifdef PHY_MTP
    for (int next_flow_id : next_flow_list){
      if (--indegree_mapping[next_flow_id] == 0) {
        phy_ready(channel_id, next_flow_id);
      }
    }
    #else
    flow_exist = true;
    NcclLog->writeLog(NcclLogLevel::DEBUG,"next_flow_list.size %d",next_flow_list.size());
    std::vector<int> ready_flow_ids;
    {
      NcclTreeFlowModel::FlowCriticalSection cs;
      for (int next_flow_id : next_flow_list) {
        if (next_flow_id == -1) {
          continue;
        }
        auto indegree_it = indegree_mapping.find(next_flow_id);
        if (indegree_it == indegree_mapping.end()) {
          flow_exist = false;
          break;
        }
        int indegree_before = indegree_it->second;
        if (--indegree_it->second == 0) {
          ready_flow_ids.push_back(next_flow_id);
        }
#ifdef NS3_MTP
        if (trace_receive) {
          auto child_it = _flow_models.find(
              std::make_pair(channel_id, next_flow_id));
          std::cerr << "[NS3 tree rx child] rank=" << id
                    << " stream=" << stream->stream_num
                    << " child=" << next_flow_id
                    << " indegree=" << indegree_before << "->"
                    << indegree_it->second;
          if (child_it != _flow_models.end()) {
            std::cerr << " edge=" << child_it->second.src << "->"
                      << child_it->second.dest
                      << " chunk=" << child_it->second.chunk_id
                      << " parent=";
            for (size_t i = 0; i < child_it->second.parent_flow_id.size(); ++i) {
              if (i != 0) {
                std::cerr << ",";
              }
              std::cerr << child_it->second.parent_flow_id[i];
            }
          } else {
            std::cerr << " missing_local_flow";
          }
          std::cerr << std::endl;
        }
#endif
      }
    }
    for (int next_flow_id : ready_flow_ids) {
      insert_packets(channel_id, next_flow_id);
    }
    assert(flow_exist == true);
    #endif
  } else if (event == EventType::StreamInit) {
    #ifdef PHY_MTP
    MPI_Barrier(MPI_COMM_WORLD);
    for(auto single_flow: _flow_models){
      if((single_flow.second.src==id||single_flow.second.dest==id)){
        #ifdef PHY_RDMA
        flow_rdma.ibv_create_peer_qp(id,single_flow.second.channel_id,single_flow.second.src,single_flow.second.dest,single_flow.second.chunk_count + 1 ,single_flow.second.chunk_id,single_flow.second.flow_size);
        #endif
      }
    }
    MPI_Barrier(MPI_COMM_WORLD);
    auto now = std::chrono::system_clock::now();
    auto now_us = std::chrono::duration_cast<std::chrono::microseconds>(now.time_since_epoch()).count();
    NcclLog->writeLog(NcclLogLevel::DEBUG,"streamInit time %lld",now_us);
    start_time = std::chrono::high_resolution_clock::now();
    #endif
    for (int i = 0; i < parallel_reduce; i++) {
      #ifndef PHY_MTP
      init_recv_ready();
      #endif
      for(int j = 0; j < m_channels; j ++) {
        for(const auto flow_model : _flow_models) {
          if(flow_model.second.src!=id)continue;
          std::vector<int> parent_list = flow_model.second.parent_flow_id;
          if((parent_list.size() == 0 ) && flow_model.second.channel_id == j ) {
            #ifdef PHY_MTP
            if(flow_model.second.chunk_id == 0){
              phy_ready(j, flow_model.second.flow_id);
            }
            #else
            if (flow_model.second.chunk_id == 0) {
              pQps->peer_qps[std::make_pair(
                  flow_model.second.channel_id,
                  std::make_pair(
                      flow_model.second.src, flow_model.second.dest))] = 0;
              insert_packets(j,flow_model.second.flow_id);
            } else {
              pQps->peer_wating_tasks[std::make_pair(
                      flow_model.second.channel_id,
                      std::make_pair(
                          flow_model.second.src, flow_model.second.dest))]
                  .push(flow_model.second.flow_id);
            }
            #endif
          }
        }
      }
      #ifdef PHY_MTP
      waiting_to_exit();
      NcclLog->writeLog(NcclLogLevel::DEBUG, "NcclTreeFlowModel::waiting_to_exit end ");
      #endif
    }
  } else if(event == EventType::PacketSentFinshed){
    SendPacketEventHandlerData* rcehd = (SendPacketEventHandlerData*)ehd;
    AstraSim::ncclFlowTag flowTag = rcehd->flowTag;
    int sent_flow_id = flowTag.current_flow_id;
    int channel_id = flowTag.channel_id;
    std::vector<int> next_flow_list = flowTag.tree_flow_list;
    NcclLog->writeLog(NcclLogLevel::DEBUG,"PacketSentFinshed src %d dst %d channel_id %d flow_id %d",flowTag.sender_node,flowTag.receiver_node,flowTag.channel_id,flowTag.current_flow_id);
    reduce(channel_id,sent_flow_id);
    bool flow_exist = next_flow_list.size() == 0 ? true : false;
    #ifndef PHY_MTP
    int cur_flow_id = -1;
    bool has_waiting_task = false;
    auto qp_key = std::make_pair(
        flowTag.channel_id,
        std::make_pair(flowTag.sender_node, flowTag.receiver_node));
    {
      NcclTreeFlowModel::FlowCriticalSection cs;
      pQps->peer_qps[qp_key] = 1;
      auto waiting_it = pQps->peer_wating_tasks.find(qp_key);
      if (waiting_it != pQps->peer_wating_tasks.end() &&
          !waiting_it->second.empty()) {
        cur_flow_id = waiting_it->second.front();
        waiting_it->second.pop();
        pQps->peer_qps[qp_key] = 0;
        has_waiting_task = true;
      }
    }
    if (has_waiting_task) {
      insert_packets(channel_id,cur_flow_id);
    }
    iteratable(channel_id);
    #else
    phy_iteratable(channel_id);
    #endif
  }
}

bool NcclTreeFlowModel::init_recv_ready() {
  std::map<std::pair<int,std::vector<int>>,std::vector<int>> recv_ready_flows;
  for(auto flow : _flow_models){
    if(flow.second.src!=id)  continue;
    if(flow.second.chunk_id!=0 && flow.second.conn_type != "PXN_REMOTE")continue; 
    if (flow.second.parent_flow_id.size() == 0)
      continue;
    std::pair<int, std::vector<int>> cur =
        std::make_pair(flow.second.channel_id, flow.second.prev);
    if (recv_ready_flows.count(cur) == 0) {
      recv_ready_flows[cur] = {flow.second.flow_id};
    } else {
      std::vector<int> flow_ids = recv_ready_flows[cur];
      bool flag = true;
      for (int flow_id : flow_ids) {
        auto old_flow_it =
            _flow_models.find(std::make_pair(flow.second.channel_id, flow_id));
        if (old_flow_it == _flow_models.end()) {
          continue;
        }
        MockNccl::SingleFlow old_flow = old_flow_it->second;
        if (old_flow.parent_flow_id == flow.second.parent_flow_id) {
          flag = false;
          break;
        }
      }
      if (flag) {
        recv_ready_flows[cur].push_back(flow.second.flow_id);
      }
    }
  }
  std::map<std::pair<int,std::vector<int>>,std::vector<int>>::iterator recv_ready_flow_it;
    for(recv_ready_flow_it = recv_ready_flows.begin();recv_ready_flow_it!=recv_ready_flows.end();recv_ready_flow_it++){
      for(int flow_id: recv_ready_flow_it->second){
      recv_ready(recv_ready_flow_it->first.first,flow_id);
      }
    }
  return true;
}

bool NcclTreeFlowModel::recv_ready(int channel_id, int flow_id) {
  std::vector<int>recv_prevs;
  MockNccl::SingleFlow flow_model;
  {
    NcclTreeFlowModel::FlowCriticalSection cs;
    auto flow_it = _flow_models.find(std::make_pair(channel_id,flow_id));
    assert(flow_it != _flow_models.end());
    flow_model = flow_it->second;
  }
  recv_prevs = flow_model.prev;
#ifdef NS3_MTP
  trace_ns3_tree_flow(
      "recv_ready", id, layer_num, stream == nullptr ? -1 : stream->stream_num,
      channel_id, flow_model, recv_prevs);
#endif
  MockNcclLog* NcclLog = MockNcclLog::getInstance();

  for (int recv_prev : recv_prevs) {
    bool can_recv = false;
    int free_count = 0;
    {
      NcclTreeFlowModel::FlowCriticalSection cs;
      free_count = map_value_or_zero(
          free_packets, std::make_pair(channel_id, recv_prev));
      can_recv = free_count > 0;
    }
    if (!can_recv) {
#ifdef NS3_MTP
      trace_ns3_receive_gate(
          "recv_ready_skip", id, layer_num,
          stream == nullptr ? -1 : stream->stream_num, channel_id,
          flow_model, recv_prev, free_count,
          recv_packets.load(std::memory_order_acquire));
#endif
      continue;
    }
    int receive_tag = tag_id_for_receive_from(flow_model, recv_prev);
#ifdef NS3_MTP
    {
      NcclTreeFlowModel::FlowCriticalSection cs;
      if (!posted_receive_tags
               .insert(std::make_tuple(channel_id, recv_prev, receive_tag))
               .second) {
        trace_ns3_tree_flow(
            "dedup_skip", id, layer_num,
            stream == nullptr ? -1 : stream->stream_num, channel_id,
            flow_model, std::vector<int>{recv_prev});
        continue;
      }
    }
    trace_ns3_tree_flow(
        "post_recv", id, layer_num,
        stream == nullptr ? -1 : stream->stream_num, channel_id, flow_model,
        std::vector<int>{recv_prev});
#endif
    sim_request rcv_req;
    rcv_req.vnet = this->stream->current_queue_id;
    rcv_req.layerNum = layer_num;

    RecvPacketEventHadndlerData* ehd = new RecvPacketEventHadndlerData(
        stream,
        stream->owner->id,
        EventType::PacketReceived,
        recv_prev,
        1);
    ehd->flowTag.child_flow_id = -1;
    ehd->flowTag.current_flow_id = -1;
    ehd->flow_id = flow_model.flow_id;
    ehd->flowTag.channel_id = channel_id;
    ehd->flowTag.chunk_id = flow_model.chunk_id;
    ehd->flowTag.tag_id = receive_tag;
    ehd->flowTag.sender_node = recv_prev;
    ehd->flowTag.receiver_node = id;
    ehd->flowTag.flow_size = flow_model.flow_size;
    ehd->flowTag.pQps = nullptr;
    ehd->flowTag.tree_flow_list = acceptable_flow_ids_for_channel(channel_id);
      stream->owner->front_end_sim_recv(
          0,
          Sys::dummy_data,
          flow_model.flow_size,
          UINT8,
          recv_prev,
          channel_id,
          &rcv_req,
          &Sys::handleEvent,
          ehd);
  }
  return true;
}

void NcclTreeFlowModel::release_packets(
    int channel_id,
    int flow_id,
    uint64_t message_size,
    bool packet_npu_to_ma,
    bool packet_processed,
    bool packet_send_back) {
  MockNcclLog* NcclLog = MockNcclLog::getInstance();
  if (packet_npu_to_ma == true) {
    (new PacketBundle(
         stream->owner,
         stream,
         {},
         packet_processed,
         packet_send_back,
         message_size,
         transmition,
         channel_id,
         flow_id))
        ->send_to_MA();
  } else {
    (new PacketBundle(
         stream->owner,
         stream,
         {},
         packet_processed,
         packet_send_back,
         message_size,
         transmition,
         channel_id,
         flow_id))
        ->send_to_NPU();
  }
  NcclLog->writeLog(NcclLogLevel::DEBUG,"id:  %d finish release_packets",id);
}

void NcclTreeFlowModel::process_stream_count(int channel_id) {
  MockNcclLog*NcclLog = MockNcclLog::getInstance();
  #ifdef PHY_MTP
    send_packets--;
  #else
  int stream_count = 0;
  bool should_mark_zombie = false;
  {
    NcclTreeFlowModel::FlowCriticalSection cs;
    auto stream_it = _stream_count.find(channel_id);
    if (stream_it != _stream_count.end() && stream_it->second > 0) {
      stream_it->second--;
      stream_count = stream_it->second;
    } else if (stream_it != _stream_count.end()) {
      stream_count = stream_it->second;
    }
    bool all_channels_finished = std::all_of(
        _stream_count.begin(),
        _stream_count.end(),
        [](const std::pair<const int, int>& channel) {
          return channel.second == 0;
        });
    should_mark_zombie =
        all_channels_finished && stream->state != StreamState::Dead;
  }
  if (send_packets.load(std::memory_order_acquire) > 0) {
    send_packets.fetch_sub(1, std::memory_order_acq_rel);
  }
  NcclLog->writeLog(NcclLogLevel::DEBUG,"NcclTreeFlowModel::process_stream_count channel_id %d _stream_count %d",channel_id,stream_count);
  if (should_mark_zombie) {
    stream->changeState(StreamState::Zombie);
  }
  #endif
}

void NcclTreeFlowModel::reduce(int channel_id, int flow_id) {
  process_stream_count(channel_id);
  #ifndef PHY_MTP
  {
    NcclTreeFlowModel::FlowCriticalSection cs;
    auto packet_it = packets.find(std::make_pair(channel_id, flow_id));
    if(packet_it != packets.end() && !packet_it->second.empty()){
      packet_it->second.pop_front();
    }
  }
  iteratable(channel_id);
  #endif
}

bool NcclTreeFlowModel::iteratable(int channel_id) {
  MockNcclLog* NcclLog = MockNcclLog::getInstance();
  bool all_channel_finished = true, all_packets_freed = true;
  NcclTreeFlowModel::FlowCriticalSection cs;
  for(int i = 0; i < m_channels; ++ i) {
    if(map_value_or_zero(_stream_count, i) != 0) all_channel_finished = false;
  }
  for (auto it = free_packets.begin(); it != free_packets.end(); it++) {
    if (it->second != 0) {
      all_packets_freed = false;
      break;
    }
  }
  cs.ExitSection();
  if (all_channel_finished == true &&
      all_packets_freed == true &&
      send_packets.load(std::memory_order_acquire) == 0 &&
      recv_packets.load(std::memory_order_acquire) == 0) {
    exit();
    return false;
  }
  return true;
}

void NcclTreeFlowModel::insert_packets(int channel_id, int flow_id) {
  MockNcclLog* NcclLog = MockNcclLog::getInstance();
  assert(channel_id < m_channels);
  if (!enabled) {
    return;
  }

  bool should_release = false;
  bool packet_npu_to_ma = false;
  bool packet_processed = false;
  bool packet_send_back = false;
  bool used_zero_latency = false;
  uint64_t message_size = 0;
  int packets_left = 0;
  {
    NcclTreeFlowModel::FlowCriticalSection cs;
    auto flow_it = _flow_models.find(std::make_pair(channel_id, flow_id));
    assert(flow_it != _flow_models.end());
    MockNccl::SingleFlow f = flow_it->second;
    auto zero_it = zero_latency_packets->find(channel_id);
    auto non_zero_it = non_zero_latency_packets->find(channel_id);
    assert(zero_it != zero_latency_packets->end() &&
           non_zero_it != non_zero_latency_packets->end());
    if (zero_it->second == 0 && non_zero_it->second == 0) {
      zero_it->second = parallel_reduce * 1;
      non_zero_it->second = get_non_zero_latency_packets();
      toggle = !toggle;
    }
    int current_receiver = f.dest;
    std::vector<int> current_sender = f.prev;
    assert(!current_sender.empty());
    message_size = f.flow_size;
    auto packet_key = std::make_pair(channel_id, flow_id);
    if (zero_it->second > 0) {
      packets[packet_key].push_back(MyPacket(
          stream->current_queue_id,
          current_sender[0],
          current_receiver,
          message_size,
          channel_id,
          flow_id));
      packets[packet_key].back().set_flow_id(flow_id);
      packets[packet_key].back().sender = nullptr;
      packet_processed = false;
      packet_send_back = false;
      packet_npu_to_ma = true;
      zero_it->second--;
      packets_left = zero_it->second;
      used_zero_latency = true;
      should_release = true;
    } else if (non_zero_it->second > 0) {
      packets[packet_key].push_back(MyPacket(
          stream->current_queue_id,
          current_sender[0],
          current_receiver,
          message_size,
          channel_id,
          flow_id));
      packets[packet_key].back().set_flow_id(flow_id);
      packets[packet_key].back().sender = nullptr;
      packet_processed = comType == ComType::Reduce_Scatter ||
          (comType == ComType::All_Reduce && toggle);
      packet_send_back = non_zero_it->second > parallel_reduce * 1;
      packet_npu_to_ma = false;
      non_zero_it->second--;
      packets_left = non_zero_it->second;
      should_release = true;
    }
  }

  if (should_release) {
    if (used_zero_latency) {
      NcclLog->writeLog(NcclLogLevel::DEBUG,"id:  %d (*zero_latency_packets)[channel_id] : %d ",id,packets_left);
    } else {
      NcclLog->writeLog(NcclLogLevel::DEBUG,"id:  %d (*non_zero_latency_packets)[channel_id] : %d ",id,packets_left);
    }
    release_packets(
        channel_id,
        flow_id,
        message_size,
        packet_npu_to_ma,
        packet_processed,
        packet_send_back);
    return;
  }
  Sys::sys_panic("should not inject nothing!");
}

bool NcclTreeFlowModel::ready(int channel_id, int flow_id) {
  MockNcclLog* NcclLog = MockNcclLog::getInstance();
  MyPacket packet;
  MockNccl::SingleFlow flow_model;
  std::vector<int> ready_recv_prevs;
  if (stream->state == StreamState::Created ||
      stream->state == StreamState::Ready) {
    stream->changeState(StreamState::Executing);
  }
  {
    NcclTreeFlowModel::FlowCriticalSection cs;
    auto packet_it = packets.find(std::make_pair(channel_id, flow_id));
#ifdef NS3_MTP
    // A late child can be inserted after the last root send completes.
    if (!enabled ||
        packet_it == packets.end() ||
        packet_it->second.empty()) {
#else
    if (!enabled ||
        packet_it == packets.end() ||
        packet_it->second.empty() ||
        map_value_or_zero(_stream_count, channel_id) == 0) {
#endif
      NcclLog->writeLog(NcclLogLevel::DEBUG,"NcclTreeFlowModel not ready!");
      return false;
    }
    auto flow_it = _flow_models.find(std::make_pair(channel_id, flow_id));
    assert(flow_it != _flow_models.end());
    packet = packet_it->second.front();
    flow_model = flow_it->second;
    for (int recv_prev : flow_model.prev) {
      int free_count = map_value_or_zero(
          free_packets, std::make_pair(channel_id, recv_prev));
      if (free_count > 0) {
        ready_recv_prevs.push_back(recv_prev);
      } else {
#ifdef NS3_MTP
        trace_ns3_receive_gate(
            "ready_skip", id, layer_num,
            stream == nullptr ? -1 : stream->stream_num, channel_id,
            flow_model, recv_prev, free_count,
            recv_packets.load(std::memory_order_acquire));
#endif
      }
    }
  }
  for (int recv_prev : ready_recv_prevs) {
    int receive_tag = tag_id_for_receive_from(flow_model, recv_prev);
#ifdef NS3_MTP
    {
      NcclTreeFlowModel::FlowCriticalSection cs;
      if (!posted_receive_tags
               .insert(std::make_tuple(channel_id, recv_prev, receive_tag))
               .second) {
        trace_ns3_tree_flow(
            "dedup_skip", id, layer_num,
            stream == nullptr ? -1 : stream->stream_num, channel_id,
            flow_model, std::vector<int>{recv_prev});
        continue;
      }
    }
    trace_ns3_tree_flow(
        "post_recv", id, layer_num,
        stream == nullptr ? -1 : stream->stream_num, channel_id, flow_model,
        std::vector<int>{recv_prev});
#endif
    sim_request rcv_req;
    rcv_req.vnet = this->stream->current_queue_id;
    rcv_req.layerNum = layer_num;
    rcv_req.reqCount = packet.msg_size;
    rcv_req.tag = channel_id;
    RecvPacketEventHadndlerData* ehd = new RecvPacketEventHadndlerData(
        stream,
        stream->owner->id,
        EventType::PacketReceived,
        stream->current_queue_id,
        stream->stream_num);
    ehd->flowTag.child_flow_id = -1;
    ehd->flowTag.current_flow_id = -1;
    ehd->flow_id = flow_model.flow_id;
    ehd->flowTag.tag_id = receive_tag;
    ehd->flowTag.channel_id = channel_id;
    ehd->flowTag.chunk_id = flow_model.chunk_id;
    ehd->flowTag.sender_node = recv_prev;
    ehd->flowTag.receiver_node = id;
    ehd->flowTag.flow_size = packet.msg_size;
    ehd->flowTag.pQps = nullptr;
    ehd->flowTag.tree_flow_list = acceptable_flow_ids_for_channel(channel_id);
    stream->owner->front_end_sim_recv(
        0,
        Sys::dummy_data,
        rcv_req.reqCount,
        UINT8,
        recv_prev,
        rcv_req.tag,
        &rcv_req,
        &Sys::handleEvent,
        ehd);
  }
#ifdef NS3_MTP
  trace_ns3_tree_flow(
      "ready", id, layer_num, stream == nullptr ? -1 : stream->stream_num,
      channel_id, flow_model, ready_recv_prevs);
#endif
  sim_request snd_req;
  snd_req.srcRank = id;
  snd_req.dstRank = packet.preferred_dest;
  snd_req.tag = channel_id;
  snd_req.reqType = UINT8;
  snd_req.vnet = this->stream->current_queue_id;
  snd_req.layerNum = layer_num;
  snd_req.reqCount = packet.msg_size;
  snd_req.flowTag.tag_id = tag_id_for_flow(flow_model, false);
  snd_req.flowTag.channel_id = channel_id;
  snd_req.flowTag.flow_size = flow_model.flow_size;
  snd_req.flowTag.current_flow_id = flow_id;
  snd_req.flowTag.chunk_id = flow_model.chunk_id;
  snd_req.flowTag.child_flow_id = -1;
  snd_req.flowTag.tree_flow_list = flow_model.child_flow_id;
  snd_req.flowTag.sender_node = id;
  snd_req.flowTag.receiver_node = packet.preferred_dest;
  snd_req.flowTag.pQps = this->pQps;
  if (this->comType == ComType::All_Reduce_NVLS)
    snd_req.flowTag.nvls_on = true;
  else
    snd_req.flowTag.nvls_on = false;
  SendPacketEventHandlerData* send_ehd = new SendPacketEventHandlerData(
      stream,
      id,
      packet.preferred_dest,
      snd_req.flowTag.tag_id,
      EventType::PacketSentFinshed);
  stream->owner->front_end_sim_send(
      0,
      Sys::dummy_data,
      snd_req.reqCount,
      UINT8,
      packet.preferred_dest,
      snd_req.flowTag.tag_id,
      &snd_req,
      &Sys::handleEvent,
      send_ehd);
  return true;
}

void NcclTreeFlowModel::exit() {
#ifdef NS3_MTP
  if (stream != nullptr &&
      stream->pending_receives.load(std::memory_order_acquire) != 0) {
    stream->changeState(StreamState::Zombie);
    return;
  }
#endif
  if (exited.exchange(true)) {
    return;
  }
  enabled = false;
  MockNcclLog* NcclLog = MockNcclLog::getInstance();
  #ifdef PHY_MTP
  auto now = std::chrono::system_clock::now();
  auto now_us =
      std::chrono::duration_cast<std::chrono::microseconds>(
          now.time_since_epoch())
          .count();
  NcclLog->writeLog(
      NcclLogLevel::DEBUG,
      "NcclTreeFlowModel exit time %lld",
      now_us);
  end_time = std::chrono::high_resolution_clock::now();
  auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end_time - start_time);
  NcclLog->writeLog(NcclLogLevel::DEBUG,"Communication Latency：%lld us",duration.count());
  MPI_Barrier(MPI_COMM_WORLD);
  sleep(1);
  #else
  {
    NcclTreeFlowModel::FlowCriticalSection cs;
    for(auto& packet: packets) {
      if(packet.second.size() != 0)
        packet.second.clear();
    }
  }
  #endif
  if (stream->state != StreamState::Dead) {
    stream->owner->proceed_to_next_vnet_baseline((StreamBaseline*)stream);
  }
  return;
}

#ifdef PHY_RDMA
bool NcclTreeFlowModel::phy_iteratable(int channel_id){
  MockNcclLog* NcclLog = MockNcclLog::getInstance();
  bool all_send_finished = true, all_recv_finished = true;
  bool exit_flag = true;
  if(send_packets!=0||recv_packets!=0){
    exit_flag=false;
  }
  if(exit_flag){
    judge_exit_flag.store(true);
    return false;
  } else{
    return true;
  }
}

bool NcclTreeFlowModel::phy_ready(int channel_id,int flow_id) {
  MockNcclLog* NcclLog = MockNcclLog::getInstance();
  if (stream->state == StreamState::Created ||
      stream->state == StreamState::Ready) {
    stream->changeState(StreamState::Executing);
  }
  MockNccl::SingleFlow flow = _flow_models[std::make_pair(channel_id, flow_id)];
  std::vector<int>recv_prevs;
  recv_prevs = _flow_models[std::make_pair(channel_id, flow_id)].prev;
  for (int recv_prev : recv_prevs) {
    sim_request rcv_req;
    rcv_req.vnet = this->stream->current_queue_id;
    rcv_req.layerNum = layer_num;
    rcv_req.reqCount = flow.flow_size;
    rcv_req.tag = channel_id;
    RecvPacketEventHadndlerData* ehd = new RecvPacketEventHadndlerData(
        stream,
        stream->owner->id,
        EventType::PacketReceived,
        stream->current_queue_id,
        1);
    ehd->flowTag.child_flow_id = -1;
    ehd->flowTag.current_flow_id = -1;
    auto flow_model = this->_flow_models[std::make_pair(channel_id,flow_id)];
    ehd->flowTag.tag_id = tag_id_for_flow(flow_model, true);
    ehd->flowTag.channel_id = flow.channel_id;
    ehd->flowTag.sender_node = recv_prev;
    ehd->flowTag.receiver_node = id;
    ehd->flowTag.flow_size = rcv_req.reqCount;
    ehd->flowTag.pQps = nullptr;
    ehd->flowTag.tree_flow_list =
        acceptable_flow_ids_for_channel(channel_id);
    if (free_packets[std::make_pair(channel_id, recv_prev)] > 0) {
      stream->owner->front_end_sim_recv(
          0,
          Sys::dummy_data,
          rcv_req.reqCount,
          UINT8,
          recv_prev,
          rcv_req.tag,
          &rcv_req,
          &Sys::handleEvent,
          ehd);
    }
  }
  sim_request snd_req;
  snd_req.srcRank = id;
  snd_req.dstRank = flow.dest;
  snd_req.tag = channel_id;
  snd_req.reqType = UINT8;
  snd_req.vnet = this->stream->current_queue_id;
  snd_req.layerNum = layer_num;
  snd_req.reqCount = flow.flow_size;
  MockNccl::SingleFlow flow_model =
      this->_flow_models[std::make_pair(channel_id, flow_id)];
  snd_req.flowTag.tag_id = tag_id_for_flow(flow_model, false);
  snd_req.flowTag.channel_id = channel_id;
  snd_req.flowTag.flow_size = flow_model.flow_size;
  snd_req.flowTag.current_flow_id = flow_id;
  snd_req.flowTag.chunk_id = flow_model.chunk_id;
  snd_req.flowTag.child_flow_id = -1;
  snd_req.flowTag.tree_flow_list =
      flow_model.child_flow_id;
  snd_req.flowTag.sender_node = id;
  snd_req.flowTag.receiver_node = flow.dest;
  snd_req.flowTag.pQps = this->pQps;
  if (this->comType == ComType::All_Reduce_NVLS)
    snd_req.flowTag.nvls_on = true;
  else
    snd_req.flowTag.nvls_on = false;
  SendPacketEventHandlerData* send_ehd = new SendPacketEventHandlerData(
      stream,
      id,
      flow.dest,
      snd_req.flowTag.tag_id,
      EventType::PacketSentFinshed);
  stream->owner->front_end_sim_send(
      0,
      Sys::dummy_data,
      snd_req.reqCount,
      UINT8,
      flow.dest,
      snd_req.flowTag.tag_id,
      &snd_req,
      &Sys::handleEvent,
      send_ehd);
  return true;
}

void NcclTreeFlowModel::waiting_to_exit() {
  MockNcclLog* NcclLog = MockNcclLog::getInstance();
  NcclLog->writeLog(
      NcclLogLevel::DEBUG, "NcclTreeFlowModel::waiting_to_exit begin ");
  while (!judge_exit_flag) {
  };
  exit();
  return;
}
#endif
} // namespace AstraSim
