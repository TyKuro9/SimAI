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

#ifndef __ENTRY_H__
#define __ENTRY_H__

#undef PGO_TRAINING
#define PATH_TO_PGO_CONFIG "path_to_pgo_config"
#include "common.h"
#include "routing_policy.h"
#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/error-model.h"
#include "ns3/global-route-manager.h"
#include "ns3/internet-module.h"
#include "ns3/ipv4-static-routing-helper.h"
#include "ns3/packet.h"
#include "ns3/point-to-point-helper.h"
#include "ns3/qbb-helper.h"
#include <fstream>
#include <iostream>
#include <ns3/rdma-client-helper.h>
#include <ns3/rdma-client.h>
#include <ns3/rdma-driver.h>
#include <ns3/rdma.h>
#include <ns3/sim-setting.h>
#include <ns3/switch-node.h>
#include <time.h>
#include <unordered_map>
#include <mutex>
#include <vector>
#include <cstdlib>
#include <cstring>
#include <algorithm>
#include <atomic>
#include <cctype>
#include <string>
#ifdef NS3_MTP
#include "ns3/mtp-interface.h"
#endif
#include <map>
#include"astra-sim/system/MockNcclQps.h"
#include "astra-sim/system/MockNcclLog.h"
using namespace ns3;
using namespace std;


std::map<std::pair<std::pair<int, int>,int>, AstraSim::ncclFlowTag> receiver_pending_queue;


std::map<std::pair<int, std::pair<int, int>>, AstraSim::ncclFlowTag> sender_src_port_map; 
struct task1 {
  int src;
  int dest;
  int type;
  uint64_t count;
  void *fun_arg;
  void (*msg_handler)(void *fun_arg);
  double schTime; 
};
map<std::pair<int, std::pair<int, int>>, struct task1> expeRecvHash;
map<std::pair<int, std::pair<int, int>>, uint64_t> recvHash;
map<std::pair<int, std::pair<int, int>>, struct task1> sentHash;
map<std::pair<int, int>, int64_t> nodeHash;
map<std::pair<int,std::pair<int,int>>,int> waiting_to_sent_callback;  
map<std::pair<int,std::pair<int,int>>,int>waiting_to_notify_receiver;
map<std::pair<int,std::pair<int,int>>,uint64_t>received_chunksize;  
map<std::pair<int,std::pair<int,int>>,uint64_t>sent_chunksize;  

enum class PxnLegKind {
  None,
  Local,
  Remote,
};

enum class PxnPolicy {
  Off,
  Force,
  Fallback,
  Aggregate,
};

struct PxnLegContext {
  PxnLegKind kind;
  int original_src;
  int original_dst;
  int tag;
  uint64_t count;
  void *fun_arg;
  void (*msg_handler)(void *fun_arg);
  AstraSim::sim_request request;
  std::vector<std::pair<int, int>> legs;
  size_t next_leg_index;
};

struct Ns3PhysicalFlowSpec {
  int src;
  int dst;
  uint64_t logical_bytes;
  void *fun_arg;
  void (*msg_handler)(void *fun_arg);
  int tag;
  AstraSim::sim_request request;
  PxnLegKind leg_kind;
  int original_src;
  int original_dst;
  std::vector<std::pair<int, int>> pxn_legs;
  size_t next_leg_index;
};

struct Ns3DynamicChunkPlan {
  Ns3PhysicalFlowSpec flow;
  std::vector<uint64_t> chunk_bytes;
  size_t concurrency = 1;
  size_t send_finished = 0;
  size_t receive_finished = 0;
};

struct Ns3SubflowContext {
  size_t stripe_index = 0;
  size_t stripe_count = 1;
  uint64_t dynamic_plan_id = 0;
  bool send_finished = false;
  bool receive_finished = false;
};

map<std::pair<int, std::pair<int, int>>, PxnLegContext> pxn_leg_context;
map<std::pair<int, std::pair<int, int>>, Ns3SubflowContext>
    ns3_subflow_context;
std::mutex ns3_subflow_context_mutex;
std::map<uint64_t, Ns3DynamicChunkPlan> ns3_dynamic_chunk_plans;
std::mutex ns3_dynamic_chunk_mutex;
std::atomic<uint64_t> ns3_next_dynamic_plan_id{1};
uint64_t ns3_pxn_split_count = 0;
uint64_t ns3_pxn_direct_cross_rail_count = 0;
std::atomic<uint64_t> ns3_routing_fabric_leg_count{0};
std::atomic<uint64_t> ns3_routing_sprayed_leg_count{0};
std::atomic<uint64_t> ns3_routing_subflow_count{0};
std::atomic<uint64_t> ns3_routing_fabric_bytes{0};

struct PxnLogFields {
  int original_src;
  int original_dst;
  const char* leg_kind;
  size_t leg_index;
  size_t leg_count;
  int flow_id;
};

struct Ns3PxnPlan {
  bool use_pxn = false;
  std::vector<std::pair<int, int>> legs;
};

AstraSim::Ns3RoutingPolicy ns3_routing_policy() {
  static AstraSim::Ns3RoutingPolicy policy = []() {
    const char* value = std::getenv("AS_NS3_ROUTING_POLICY");
    if (value == nullptr || value[0] == '\0') {
      value = std::getenv("NS3_ROUTING_POLICY");
    }
    try {
      return AstraSim::ParseNs3RoutingPolicy(value);
    } catch (const std::invalid_argument& error) {
      MockNcclLog::getInstance()->writeLog(
          NcclLogLevel::ERROR,
          "Unknown AS_NS3_ROUTING_POLICY=%s: %s",
          value ? value : "", error.what());
      std::exit(-1);
    }
  }();
  return policy;
}

uint32_t ns3_spray_width() {
  static uint32_t width = []() {
    const char* value = std::getenv("AS_NS3_SPRAY_WIDTH");
    if (value == nullptr || value[0] == '\0') {
      value = std::getenv("NS3_SPRAY_WIDTH");
    }
    try {
      return AstraSim::ParseNs3SprayWidth(value);
    } catch (const std::invalid_argument& error) {
      MockNcclLog::getInstance()->writeLog(
          NcclLogLevel::ERROR,
          "Invalid AS_NS3_SPRAY_WIDTH=%s: %s",
          value ? value : "", error.what());
      std::exit(-1);
    }
  }();
  return width;
}

uint32_t ns3_dynamic_chunk_count() {
  static uint32_t count = []() {
    const char* value = std::getenv("AS_NS3_DYNAMIC_CHUNKS");
    if (value == nullptr || value[0] == '\0') {
      value = std::getenv("NS3_DYNAMIC_CHUNKS");
    }
    try {
      return AstraSim::ParseNs3DynamicChunkCount(value);
    } catch (const std::invalid_argument& error) {
      MockNcclLog::getInstance()->writeLog(
          NcclLogLevel::ERROR,
          "Invalid AS_NS3_DYNAMIC_CHUNKS=%s: %s",
          value ? value : "", error.what());
      std::exit(-1);
    }
  }();
  return count;
}

bool ns3_completion_log_enabled() {
  static bool enabled = []() {
    const char* value = std::getenv("AS_NS3_COMPLETION_LOG");
    return value == nullptr || value[0] == '\0' || std::string(value) != "0";
  }();
  return enabled;
}

uint64_t ns3_env_u64(const char* name, uint64_t fallback) {
  const char* value = std::getenv(name);
  if (value == nullptr || value[0] == '\0') {
    return fallback;
  }
  try {
    return std::stoull(value);
  } catch (const std::exception&) {
    return fallback;
  }
}

bool ns3_should_log_fct(const AstraSim::ncclFlowTag& flow_tag) {
  static const std::string filter = []() {
    const char* value = std::getenv("AS_NS3_FCT_FILTER");
    return value == nullptr ? std::string() : std::string(value);
  }();
  if (filter != "dp") {
    return true;
  }
  static const uint64_t dp_group_count =
      ns3_env_u64("AS_NS3_DP_GROUP_COUNT", 0);
  if (dp_group_count == 0 || flow_tag.sender_node < 0 ||
      flow_tag.receiver_node < 0 ||
      flow_tag.sender_node == flow_tag.receiver_node) {
    return false;
  }
  return static_cast<uint64_t>(flow_tag.sender_node) % dp_group_count ==
      static_cast<uint64_t>(flow_tag.receiver_node) % dp_group_count;
}

const char* ns3_routing_policy_name(AstraSim::Ns3RoutingPolicy policy) {
  switch (policy) {
    case AstraSim::Ns3RoutingPolicy::Spray:
      return "spray";
    case AstraSim::Ns3RoutingPolicy::SprayDynamic:
      return "spray_dynamic";
    case AstraSim::Ns3RoutingPolicy::SprayPathAware:
      return "spray_path";
    case AstraSim::Ns3RoutingPolicy::SprayFlowlet:
      return "spray_flowlet";
    case AstraSim::Ns3RoutingPolicy::SprayDualTable:
      return "spray_dual_table";
    case AstraSim::Ns3RoutingPolicy::SprayAdaptive:
      return "spray_adaptive";
    case AstraSim::Ns3RoutingPolicy::SprayDynamicChunk:
      return "spray_dynamic_chunk";
    case AstraSim::Ns3RoutingPolicy::Ecmp:
      return "ecmp";
  }
  return "unknown";
}

bool ns3_is_same_server_transfer(int src, int dst) {
  return gpus_per_server > 0 &&
         src / static_cast<int>(gpus_per_server) ==
             dst / static_cast<int>(gpus_per_server);
}

FILE* ns3_subflow_output() {
  static FILE* output = []() -> FILE* {
    const char* path = std::getenv("AS_NS3_SUBFLOW_OUTPUT_FILE");
    if (path == nullptr || path[0] == '\0') {
      return nullptr;
    }
    FILE* file = fopen(path, "w");
    if (file == nullptr) {
      perror("AS_NS3_SUBFLOW_OUTPUT_FILE");
      std::exit(-1);
    }
    fprintf(
        file,
        "orig_src,orig_dst,physical_src,physical_dst,flow_id,tag_id,channel_id,"
        "leg_kind,leg_index,leg_count,stripe_index,stripe_count,sip_hex,"
        "dip_hex,sport,dport,bytes\n");
    fflush(file);
    return file;
  }();
  return output;
}

FILE* ns3_stripe_metrics_output() {
  static FILE* output = []() -> FILE* {
    const char* path = std::getenv("AS_NS3_STRIPE_METRICS_FILE");
    if (path == nullptr || path[0] == '\0') {
      return nullptr;
    }
    FILE* file = fopen(path, "w");
    if (file == nullptr) {
      perror("AS_NS3_STRIPE_METRICS_FILE");
      std::exit(-1);
    }
    fprintf(
        file,
        "orig_src,orig_dst,physical_src,physical_dst,flow_id,tag_id,"
        "channel_id,sport,dport,bytes,stripe_index,stripe_count,"
        "dynamic_chunk,source_nic,initial_source_nic,destination_nic,"
        "source_nic_ordinal_hint,source_nic_hint_fallback,"
        "nic_reassignments,path_signature,path_hops,candidate_count,"
        "path_score_ns,path_queue_delay_ns,path_propagation_ns,"
        "path_reserved_bytes,cnp_count,start_ns,finish_ns,fct_ns,"
        "standalone_fct_ns\n");
    fflush(file);
    return file;
  }();
  return output;
}

void ns3_register_subflow_context(
    const std::pair<int, std::pair<int, int>>& flow_key,
    const Ns3SubflowContext& context) {
  std::lock_guard<std::mutex> guard(ns3_subflow_context_mutex);
  ns3_subflow_context[flow_key] = context;
}

bool ns3_lookup_subflow_context(
    const std::pair<int, std::pair<int, int>>& flow_key,
    Ns3SubflowContext* context) {
  std::lock_guard<std::mutex> guard(ns3_subflow_context_mutex);
  auto found = ns3_subflow_context.find(flow_key);
  if (found == ns3_subflow_context.end()) {
    return false;
  }
  if (context != nullptr) {
    *context = found->second;
  }
  return true;
}

bool ns3_mark_subflow_send_finished(
    const std::pair<int, std::pair<int, int>>& flow_key,
    Ns3SubflowContext* context) {
  std::lock_guard<std::mutex> guard(ns3_subflow_context_mutex);
  auto found = ns3_subflow_context.find(flow_key);
  if (found == ns3_subflow_context.end()) {
    return false;
  }
  if (context != nullptr) {
    *context = found->second;
  }
  if (found->second.send_finished) {
    return false;
  }
  found->second.send_finished = true;
  return true;
}

void ns3_mark_subflow_receive_finished(
    const std::pair<int, std::pair<int, int>>& flow_key) {
  std::lock_guard<std::mutex> guard(ns3_subflow_context_mutex);
  auto found = ns3_subflow_context.find(flow_key);
  if (found == ns3_subflow_context.end()) {
    return;
  }
  found->second.receive_finished = true;
  if (found->second.send_finished) {
    ns3_subflow_context.erase(found);
  }
}

void ns3_write_stripe_metric(
    Ptr<RdmaQueuePair> q,
    uint32_t physical_src,
    uint32_t physical_dst,
    const AstraSim::ncclFlowTag& flow_tag,
    const PxnLogFields& log_fields,
    const Ns3SubflowContext& subflow,
    uint64_t standalone_fct) {
  FILE* output = ns3_stripe_metrics_output();
  if (output == nullptr) {
    return;
  }
  const uint64_t finish_ns = Simulator::Now().GetTimeStep();
  const uint64_t start_ns = q->startTime.GetTimeStep();
  const uint64_t fct_ns = (Simulator::Now() - q->startTime).GetTimeStep();
  fprintf(
      output,
      "%d,%d,%u,%u,%d,%d,%d,%u,%u,%lu,%zu,%zu,%u,%d,%d,%d,%u,%u,%lu,"
      "%016lx,%u,%u,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu\n",
      log_fields.original_src,
      log_fields.original_dst,
      physical_src,
      physical_dst,
      log_fields.flow_id,
      flow_tag.tag_id,
      flow_tag.channel_id,
      q->sport,
      q->dport,
      q->m_size,
      subflow.stripe_index,
      subflow.stripe_count,
      subflow.dynamic_plan_id == 0 ? 0U : 1U,
      q->m_selectedNicIdx,
      q->m_initialSelectedNicIdx,
      q->m_selectedDestinationNicIdx,
      q->m_sourceNicOrdinalHint,
      q->m_sourceNicHintFallback ? 1U : 0U,
      q->m_nicReassignments,
      q->m_bindPathSignature,
      q->m_bindPathHops,
      q->m_bindCandidateCount,
      q->m_bindPathScoreNs,
      q->m_bindPathQueueDelayNs,
      q->m_bindPathPropagationNs,
      q->m_bindPathReservedBytes,
      q->m_cnpCount,
      start_ns,
      finish_ns,
      fct_ns,
      standalone_fct);
  fflush(output);
}

void ns3_write_subflow_record(
    int src,
    int dst,
    uint16_t sport,
    uint16_t dport,
    uint64_t bytes,
    const AstraSim::ncclFlowTag& flowTag,
    const PxnLogFields& log_fields,
    size_t stripe_index,
    size_t stripe_count) {
  FILE* output = ns3_subflow_output();
  if (output == nullptr) {
    return;
  }
  fprintf(
      output,
      "%d,%d,%d,%d,%d,%d,%d,%s,%zu,%zu,%zu,%zu,%08x,%08x,%u,%u,%lu\n",
      log_fields.original_src,
      log_fields.original_dst,
      src,
      dst,
      log_fields.flow_id,
      flowTag.tag_id,
      flowTag.channel_id,
      log_fields.leg_kind,
      log_fields.leg_index,
      log_fields.leg_count,
      stripe_index,
      stripe_count,
      serverAddress[src].Get(),
      serverAddress[dst].Get(),
      sport,
      dport,
      bytes);
  fflush(output);
}

std::string ns3_normalize_env_value(const char* value) {
  std::string normalized = value ? value : "";
  std::transform(normalized.begin(), normalized.end(), normalized.begin(),
                 [](unsigned char c) { return std::tolower(c); });
  return normalized;
}

const char* pxn_leg_kind_name(PxnLegKind kind) {
  switch (kind) {
    case PxnLegKind::None:
      return "none";
    case PxnLegKind::Local:
      return "local";
    case PxnLegKind::Remote:
      return "remote";
  }
  return "unknown";
}

PxnLogFields build_pxn_log_fields(
    int physical_src,
    int physical_dst,
    const AstraSim::ncclFlowTag& flowTag,
    bool has_pxn_ctx,
    const PxnLegContext& pxn_ctx) {
  PxnLogFields fields;
  fields.original_src = physical_src;
  fields.original_dst = physical_dst;
  fields.leg_kind = pxn_leg_kind_name(PxnLegKind::None);
  fields.leg_index = 0;
  fields.leg_count = 1;
  fields.flow_id = flowTag.current_flow_id;
  if (has_pxn_ctx) {
    fields.original_src = pxn_ctx.original_src;
    fields.original_dst = pxn_ctx.original_dst;
    fields.leg_kind = pxn_leg_kind_name(pxn_ctx.kind);
    fields.leg_count = pxn_ctx.legs.empty() ? 1 : pxn_ctx.legs.size();
    fields.leg_index = pxn_ctx.next_leg_index > 0 ? pxn_ctx.next_leg_index - 1 : 0;
    if (fields.leg_index >= fields.leg_count) {
      fields.leg_index = fields.leg_count - 1;
    }
  }
  return fields;
}

PxnPolicy ns3_pxn_policy() {
  static PxnPolicy policy = []() {
    std::string policy_env = ns3_normalize_env_value(std::getenv("AS_PXN_POLICY"));
    if (!policy_env.empty()) {
      if (policy_env == "off" || policy_env == "0" ||
          policy_env == "disable" || policy_env == "disabled" ||
          policy_env == "none") {
        return PxnPolicy::Off;
      }
      if (policy_env == "force" || policy_env == "on" ||
          policy_env == "1" || policy_env == "enable" ||
          policy_env == "enabled") {
        return PxnPolicy::Force;
      }
      if (policy_env == "fallback") {
        return PxnPolicy::Fallback;
      }
      if (policy_env == "aggregate") {
        return PxnPolicy::Aggregate;
      }
      MockNcclLog::getInstance()->writeLog(
          NcclLogLevel::ERROR,
          "Unknown AS_PXN_POLICY=%s, expected off/force/fallback/aggregate",
          policy_env.c_str());
      exit(-1);
    }

    const char* enable_env = std::getenv("AS_PXN_ENABLE");
    if (enable_env && std::strcmp(enable_env, "1") == 0) {
      return PxnPolicy::Force;
    }
    return PxnPolicy::Off;
  }();
  return policy;
}

const char* ns3_pxn_policy_name(PxnPolicy policy) {
  switch (policy) {
    case PxnPolicy::Off:
      return "off";
    case PxnPolicy::Force:
      return "force";
    case PxnPolicy::Fallback:
      return "fallback";
    case PxnPolicy::Aggregate:
      return "aggregate";
  }
  return "unknown";
}

bool ns3_needs_pxn(int src, int dst) {
  return gpus_per_server > 0 &&
         src / static_cast<int>(gpus_per_server) != dst / static_cast<int>(gpus_per_server) &&
         src % static_cast<int>(gpus_per_server) != dst % static_cast<int>(gpus_per_server);
}

bool ns3_has_direct_route(int src, int dst) {
  if (src == dst) {
    return true;
  }

  auto src_bw_it = pairBw.find(src);
  if (src_bw_it != pairBw.end()) {
    auto dst_bw_it = src_bw_it->second.find(dst);
    if (dst_bw_it != src_bw_it->second.end() && dst_bw_it->second > 0) {
      return true;
    }
  }

  if (src >= 0 && dst >= 0 && src < static_cast<int>(n.GetN()) &&
      dst < static_cast<int>(n.GetN())) {
    auto src_nh_it = nextHop.find(n.Get(src));
    if (src_nh_it != nextHop.end()) {
      auto dst_nh_it = src_nh_it->second.find(n.Get(dst));
      if (dst_nh_it != src_nh_it->second.end() && !dst_nh_it->second.empty()) {
        return true;
      }
    }
  }

  return false;
}

bool ns3_should_use_pxn(int src, int dst) {
  if (!ns3_needs_pxn(src, dst)) {
    return false;
  }

  switch (ns3_pxn_policy()) {
    case PxnPolicy::Off:
      return false;
    case PxnPolicy::Force:
    case PxnPolicy::Aggregate:
      return true;
    case PxnPolicy::Fallback:
      return !ns3_has_direct_route(src, dst);
  }
  return false;
}

std::vector<int> ns3_local_gpu_candidates(int gpu) {
  std::vector<int> candidates;
  int gpus = static_cast<int>(gpus_per_server);
  if (gpus <= 0) {
    candidates.push_back(gpu);
    return candidates;
  }

  int gpu_count = static_cast<int>(node_num - nvswitch_num - switch_num);
  int base = (gpu / gpus) * gpus;
  candidates.push_back(gpu);
  for (int offset = 0; offset < gpus; ++offset) {
    int candidate = base + offset;
    if (candidate != gpu && candidate >= 0 && candidate < gpu_count) {
      candidates.push_back(candidate);
    }
  }
  return candidates;
}

Ns3PxnPlan ns3_make_plan_from_proxies(
    int src,
    int dst,
    int src_proxy,
    int dst_proxy) {
  Ns3PxnPlan plan;

  if (!ns3_has_direct_route(src, src_proxy) ||
      !ns3_has_direct_route(src_proxy, dst_proxy) ||
      !ns3_has_direct_route(dst_proxy, dst)) {
    return plan;
  }

  if (src != src_proxy) {
    plan.legs.emplace_back(src, src_proxy);
  }
  if (src_proxy != dst_proxy) {
    plan.legs.emplace_back(src_proxy, dst_proxy);
  }
  if (dst_proxy != dst) {
    plan.legs.emplace_back(dst_proxy, dst);
  }

  plan.use_pxn = !plan.legs.empty();
  return plan;
}

Ns3PxnPlan ns3_find_generic_pxn_plan(int src, int dst) {
  Ns3PxnPlan plan;
  std::vector<int> src_candidates = ns3_local_gpu_candidates(src);
  std::vector<int> dst_candidates = ns3_local_gpu_candidates(dst);

  for (int src_proxy : src_candidates) {
    for (int dst_proxy : dst_candidates) {
      if (src_proxy == src && dst_proxy == dst) {
        continue;
      }
      plan = ns3_make_plan_from_proxies(src, dst, src_proxy, dst_proxy);
      if (plan.use_pxn) {
        return plan;
      }
    }
  }

  return plan;
}

void ns3_print_pxn_summary() {
  std::cout << "[PXN SUMMARY] policy=" << ns3_pxn_policy_name(ns3_pxn_policy())
            << " split=" << ns3_pxn_split_count
            << " direct_cross_rail=" << ns3_pxn_direct_cross_rail_count
            << std::endl;
}

void ns3_print_routing_summary() {
  FILE* subflow_output = ns3_subflow_output();
  if (subflow_output != nullptr) {
    fflush(subflow_output);
  }
  FILE* stripe_metrics_output = ns3_stripe_metrics_output();
  if (stripe_metrics_output != nullptr) {
    fflush(stripe_metrics_output);
  }
  size_t pending_dynamic_plans = 0;
  {
    std::lock_guard<std::mutex> guard(ns3_dynamic_chunk_mutex);
    pending_dynamic_plans = ns3_dynamic_chunk_plans.size();
  }
  std::cout << "[NS3 ROUTING SUMMARY] policy="
            << ns3_routing_policy_name(ns3_routing_policy())
            << " width=" << ns3_spray_width()
            << " dynamic_chunks=" << ns3_dynamic_chunk_count()
            << " fabric_legs="
            << ns3_routing_fabric_leg_count.load(std::memory_order_relaxed)
            << " sprayed_legs="
            << ns3_routing_sprayed_leg_count.load(std::memory_order_relaxed)
            << " subflows="
            << ns3_routing_subflow_count.load(std::memory_order_relaxed)
            << " fabric_bytes="
            << ns3_routing_fabric_bytes.load(std::memory_order_relaxed)
            << " pending_contexts=" << pxn_leg_context.size()
            << " pending_dynamic_plans=" << pending_dynamic_plans
            << " pending_send_callbacks=" << waiting_to_sent_callback.size()
            << " pending_recv_callbacks=" << waiting_to_notify_receiver.size()
            << std::endl;
  SwitchNode::PrintFlowletRoutingSummary();
}

int ns3_pxn_proxy(int src, int dst) {
  int gpus = static_cast<int>(gpus_per_server);
  return (src / gpus) * gpus + (dst % gpus);
}

Ns3PxnPlan ns3_build_pxn_plan(int src, int dst) {
  Ns3PxnPlan plan;
  bool direct_available = ns3_has_direct_route(src, dst);
  bool cross_rail = ns3_needs_pxn(src, dst);
  PxnPolicy policy = ns3_pxn_policy();

  if (policy == PxnPolicy::Off) {
    return plan;
  }

  if (policy == PxnPolicy::Fallback && direct_available) {
    return plan;
  }

  if ((policy == PxnPolicy::Force || policy == PxnPolicy::Aggregate) &&
      cross_rail) {
    int src_proxy = ns3_pxn_proxy(src, dst);
    plan = ns3_make_plan_from_proxies(src, dst, src_proxy, dst);
    if (plan.use_pxn) {
      return plan;
    }
  }

  if (!direct_available) {
    return ns3_find_generic_pxn_plan(src, dst);
  }

  return plan;
}

bool is_sending_finished(int src,int dst,AstraSim::ncclFlowTag flowTag){
  int tag_id = flowTag.current_flow_id;
  if (waiting_to_sent_callback.count(
          std::make_pair(tag_id, std::make_pair(src, dst)))) {
    if (--waiting_to_sent_callback[std::make_pair(
            tag_id, std::make_pair(src, dst))] == 0) {
      waiting_to_sent_callback.erase(
          std::make_pair(tag_id, std::make_pair(src, dst)));
      return true;
    }
  }
  return false;
}

bool is_receive_finished(int src,int dst,AstraSim::ncclFlowTag flowTag){
  int tag_id = flowTag.current_flow_id;
  map<std::pair<int,std::pair<int,int>>,int>::iterator it;
  MockNcclLog* NcclLog = MockNcclLog::getInstance();
  if (waiting_to_notify_receiver.count(
          std::make_pair(tag_id, std::make_pair(src, dst)))) {
    NcclLog->writeLog(NcclLogLevel::DEBUG," is_receive_finished waiting_to_notify_receiver  tag_id  %d src  %d dst  %d count  %d",tag_id,src,dst,waiting_to_notify_receiver[std::make_pair(
                     tag_id, std::make_pair(src, dst))]);
    if (--waiting_to_notify_receiver[std::make_pair(
            tag_id, std::make_pair(src, dst))] == 0) {
      waiting_to_notify_receiver.erase(
          std::make_pair(tag_id, std::make_pair(src, dst)));
      return true;
    }
  }
  return false;
}

void ns3_launch_physical_subflow(
    const Ns3PhysicalFlowSpec& flow,
    uint64_t bytes,
    size_t stripe_index,
    size_t stripe_count,
    uint64_t dynamic_plan_id) {
  MockNcclLog* nccl_log = MockNcclLog::getInstance();
  uint64_t packet_count = bytes == 0 ? 1 : bytes;
  uint32_t port;
  {
    #ifdef NS3_MTP
    MtpInterface::explicitCriticalSection cs;
    #endif
    port = portNumber[flow.src][flow.dst]++;
    const auto flow_key = make_pair(port, make_pair(flow.src, flow.dst));
    sender_src_port_map[flow_key] = flow.request.flowTag;
    ns3_register_subflow_context(
        flow_key,
        Ns3SubflowContext{
            stripe_index, stripe_count, dynamic_plan_id, false, false});
    PxnLegContext pxn_log_context{};
    const bool has_pxn_context = flow.leg_kind != PxnLegKind::None;
    if (has_pxn_context) {
      PxnLegContext ctx;
      ctx.kind = flow.leg_kind;
      ctx.original_src = flow.original_src;
      ctx.original_dst = flow.original_dst;
      ctx.tag = flow.tag;
      ctx.count = flow.logical_bytes;
      ctx.fun_arg = flow.fun_arg;
      ctx.msg_handler = flow.msg_handler;
      ctx.request = flow.request;
      ctx.legs = flow.pxn_legs;
      ctx.next_leg_index = flow.next_leg_index;
      pxn_leg_context[flow_key] = ctx;
      pxn_log_context = ctx;
    }
    const PxnLogFields log_fields = build_pxn_log_fields(
        flow.src,
        flow.dst,
        flow.request.flowTag,
        has_pxn_context,
        pxn_log_context);
    ns3_write_subflow_record(
        flow.src,
        flow.dst,
        port,
        100,
        packet_count,
        flow.request.flowTag,
        log_fields,
        stripe_index,
        stripe_count);
    #ifdef NS3_MTP
    cs.ExitSection();
    #endif
  }

  int send_lat = 6000;
  const char* send_lat_env = std::getenv("AS_SEND_LAT");
  if (send_lat_env != nullptr) {
    try {
      send_lat = std::stoi(send_lat_env);
    } catch (const std::invalid_argument&) {
      nccl_log->writeLog(NcclLogLevel::ERROR, "send_lat set error");
      exit(-1);
    }
  }
  send_lat *= 1000;
  flow_input.idx++;
  nccl_log->writeLog(
      NcclLogLevel::DEBUG,
      "[Packet sending event] %d SendFlow to %d flow_id %d size %llu "
      "stripe %zu/%zu dynamic_plan %llu at tick %d",
      flow.src,
      flow.dst,
      flow.request.flowTag.current_flow_id,
      packet_count,
      stripe_index + 1,
      stripe_count,
      dynamic_plan_id,
      AstraSim::Sys::boostedTick());

  const int pg = 3;
  const int dport = 100;
  RdmaClientHelper client_helper(
      pg,
      serverAddress[flow.src],
      serverAddress[flow.dst],
      port,
      dport,
      packet_count,
      has_win
          ? (global_t == 1
                 ? maxBdp
                 : pairBdp[n.Get(flow.src)][n.Get(flow.dst)])
          : 0,
      global_t == 1 ? maxRtt : pairRtt[flow.src][flow.dst],
      flow.msg_handler,
      flow.fun_arg,
      flow.tag,
      flow.src,
      flow.dst);
  if (flow.request.flowTag.nvls_on) {
    client_helper.SetAttribute("NVLS_enable", UintegerValue(1));
  }
  if (dynamic_plan_id != 0) {
    client_helper.SetAttribute(
        "SourceNicOrdinalHint",
        UintegerValue(stripe_index % ns3_spray_width()));
  }
  {
    #ifdef NS3_MTP
    MtpInterface::explicitCriticalSection cs;
    #endif
    ApplicationContainer app_con = client_helper.Install(n.Get(flow.src));
    app_con.Start(Time(send_lat));
    if (flow.leg_kind != PxnLegKind::Local) {
      const auto logical_key = std::make_pair(
          flow.request.flowTag.current_flow_id,
          std::make_pair(flow.original_src, flow.original_dst));
      waiting_to_sent_callback[logical_key]++;
      waiting_to_notify_receiver[logical_key]++;
    }
    #ifdef NS3_MTP
    cs.ExitSection();
    #endif
  }
}

bool ns3_launch_dynamic_chunk(uint64_t plan_id, size_t stripe_index) {
  Ns3PhysicalFlowSpec flow;
  uint64_t bytes = 0;
  size_t stripe_count = 0;
  {
    std::lock_guard<std::mutex> guard(ns3_dynamic_chunk_mutex);
    auto found = ns3_dynamic_chunk_plans.find(plan_id);
    if (found == ns3_dynamic_chunk_plans.end() ||
        stripe_index >= found->second.chunk_bytes.size()) {
      return false;
    }
    Ns3DynamicChunkPlan& plan = found->second;
    stripe_count = plan.chunk_bytes.size();
    bytes = plan.chunk_bytes[stripe_index];
    flow = plan.flow;
  }
  ns3_launch_physical_subflow(
      flow, bytes, stripe_index, stripe_count, plan_id);
  return true;
}

void ns3_dynamic_chunk_send_finished(
    uint64_t plan_id, size_t finished_stripe_index) {
  if (plan_id == 0) {
    return;
  }
  bool launch_next = false;
  size_t next_stripe_index = 0;
  {
    std::lock_guard<std::mutex> guard(ns3_dynamic_chunk_mutex);
    auto found = ns3_dynamic_chunk_plans.find(plan_id);
    if (found == ns3_dynamic_chunk_plans.end()) {
      return;
    }
    Ns3DynamicChunkPlan& plan = found->second;
    ++plan.send_finished;
    next_stripe_index = finished_stripe_index + plan.concurrency;
    launch_next = next_stripe_index < plan.chunk_bytes.size();
    if (!launch_next && plan.send_finished == plan.chunk_bytes.size() &&
        plan.receive_finished == plan.chunk_bytes.size()) {
      ns3_dynamic_chunk_plans.erase(found);
      return;
    }
  }
  if (launch_next) {
    ns3_launch_dynamic_chunk(plan_id, next_stripe_index);
  }
}

void ns3_dynamic_chunk_receive_finished(uint64_t plan_id) {
  if (plan_id == 0) {
    return;
  }
  std::lock_guard<std::mutex> guard(ns3_dynamic_chunk_mutex);
  auto found = ns3_dynamic_chunk_plans.find(plan_id);
  if (found == ns3_dynamic_chunk_plans.end()) {
    return;
  }
  Ns3DynamicChunkPlan& plan = found->second;
  ++plan.receive_finished;
  if (plan.send_finished == plan.chunk_bytes.size() &&
      plan.receive_finished == plan.chunk_bytes.size()) {
    ns3_dynamic_chunk_plans.erase(found);
  }
}

void SendFlowPhysical(int src, int dst, uint64_t maxPacketCount,
              void (*msg_handler)(void *fun_arg), void *fun_arg, int tag, AstraSim::sim_request *request,
              PxnLegKind leg_kind, int original_src, int original_dst,
              const std::vector<std::pair<int, int>>& pxn_legs = {},
              size_t next_leg_index = 0) {
  const bool uses_fabric = !ns3_is_same_server_transfer(src, dst);
  const bool dynamic_chunk =
      uses_fabric && leg_kind == PxnLegKind::None &&
      AstraSim::IsNs3DynamicChunkPolicy(ns3_routing_policy());
  uint32_t stripe_count = 1;
  if (uses_fabric) {
    ns3_routing_fabric_leg_count.fetch_add(1, std::memory_order_relaxed);
    ns3_routing_fabric_bytes.fetch_add(maxPacketCount, std::memory_order_relaxed);
    if (dynamic_chunk) {
      stripe_count = AstraSim::EffectiveNs3SprayWidth(
          maxPacketCount, ns3_dynamic_chunk_count());
    } else if (AstraSim::IsNs3SprayPolicy(ns3_routing_policy())) {
      stripe_count =
          AstraSim::EffectiveNs3SprayWidth(maxPacketCount, ns3_spray_width());
    }
    ns3_routing_subflow_count.fetch_add(stripe_count, std::memory_order_relaxed);
    if (stripe_count > 1) {
      ns3_routing_sprayed_leg_count.fetch_add(1, std::memory_order_relaxed);
    }
  }

  Ns3PhysicalFlowSpec flow{
      src,
      dst,
      maxPacketCount,
      fun_arg,
      msg_handler,
      tag,
      *request,
      leg_kind,
      original_src,
      original_dst,
      pxn_legs,
      next_leg_index};
  const std::vector<uint64_t> stripe_bytes =
      AstraSim::SplitNs3SprayBytes(maxPacketCount, stripe_count);

  if (dynamic_chunk) {
    uint64_t plan_id = ns3_next_dynamic_plan_id.fetch_add(
        1, std::memory_order_relaxed);
    if (plan_id == 0) {
      plan_id = ns3_next_dynamic_plan_id.fetch_add(
          1, std::memory_order_relaxed);
    }
    {
      std::lock_guard<std::mutex> guard(ns3_dynamic_chunk_mutex);
      Ns3DynamicChunkPlan plan;
      plan.flow = flow;
      plan.chunk_bytes = stripe_bytes;
      plan.concurrency = std::min<size_t>(
          stripe_bytes.size(), ns3_spray_width());
      ns3_dynamic_chunk_plans.emplace(plan_id, std::move(plan));
    }
    const size_t concurrency = std::min<size_t>(
        stripe_bytes.size(), ns3_spray_width());
    for (size_t index = 0; index < concurrency; ++index) {
      ns3_launch_dynamic_chunk(plan_id, index);
    }
    return;
  }

  for (size_t index = 0; index < stripe_bytes.size(); ++index) {
    ns3_launch_physical_subflow(
        flow, stripe_bytes[index], index, stripe_bytes.size(), 0);
  }
}

void SendFlow(int src, int dst, uint64_t maxPacketCount,
              void (*msg_handler)(void *fun_arg), void *fun_arg, int tag, AstraSim::sim_request *request) {
  bool cross_rail = ns3_needs_pxn(src, dst);
  Ns3PxnPlan pxn_plan = ns3_build_pxn_plan(src, dst);
  bool use_pxn = pxn_plan.use_pxn;
  if (cross_rail) {
    if (use_pxn) {
      ns3_pxn_split_count++;
    } else {
      ns3_pxn_direct_cross_rail_count++;
    }
  }
  if (use_pxn) {
    auto first_leg = pxn_plan.legs.front();
    PxnLegKind first_kind =
        pxn_plan.legs.size() == 1 ? PxnLegKind::Remote : PxnLegKind::Local;
    MockNcclLog* NcclLog = MockNcclLog::getInstance();
    NcclLog->writeLog(NcclLogLevel::DEBUG,
        "[PXN] policy %s split logical flow src %d dst %d first_leg %d -> %d legs %zu",
        ns3_pxn_policy_name(ns3_pxn_policy()), src, dst, first_leg.first,
        first_leg.second, pxn_plan.legs.size());
    SendFlowPhysical(first_leg.first, first_leg.second, maxPacketCount,
                     msg_handler, fun_arg, tag, request, first_kind, src, dst,
                     pxn_plan.legs, 1);
    return;
  }
  SendFlowPhysical(src, dst, maxPacketCount, msg_handler, fun_arg, tag, request,
                   PxnLegKind::None, src, dst);
}

void notify_receiver_receive_data(int sender_node, int receiver_node,
                                  uint64_t message_size, AstraSim::ncclFlowTag flowTag) {
  {
    #ifdef NS3_MTP
    MtpInterface::explicitCriticalSection cs;   
    #endif                         
    MockNcclLog* NcclLog = MockNcclLog::getInstance();
    NcclLog->writeLog(NcclLogLevel::DEBUG," %d notify recevier:  %d message size:  %llu",sender_node,receiver_node,message_size);
    int tag = flowTag.tag_id;   
    if (expeRecvHash.find(make_pair(
            tag, make_pair(sender_node, receiver_node))) != expeRecvHash.end()) {
      task1 t2 =
          expeRecvHash[make_pair(tag, make_pair(sender_node, receiver_node))];
    MockNcclLog* NcclLog = MockNcclLog::getInstance();
    NcclLog->writeLog(NcclLogLevel::DEBUG," %d notify recevier:  %d message size:  %llu t2.count:  %llu channle id:  %d",sender_node,receiver_node,message_size,t2.count,flowTag.channel_id);
      AstraSim::RecvPacketEventHadndlerData* ehd = (AstraSim::RecvPacketEventHadndlerData*) t2.fun_arg;
      if (message_size == t2.count) {
        NcclLog->writeLog(NcclLogLevel::DEBUG," message_size = t2.count expeRecvHash.erase  %d notify recevier:  %d message size:  %llu channel_id  %d",sender_node,receiver_node,message_size,tag);
        expeRecvHash.erase(make_pair(tag, make_pair(sender_node, receiver_node)));
        #ifdef NS3_MTP
        cs.ExitSection();
        #endif
        assert(ehd->flowTag.current_flow_id == -1 && ehd->flowTag.child_flow_id == -1);
        ehd->flowTag = flowTag;
        t2.msg_handler(t2.fun_arg);
        goto receiver_end_1st_section;
      } else if (message_size > t2.count) {
        recvHash[make_pair(tag, make_pair(sender_node, receiver_node))] =
            message_size - t2.count;
        NcclLog->writeLog(NcclLogLevel::DEBUG,"message_size > t2.count expeRecvHash.erase %d notify recevier:  %d message size:  %llu channel_id  %d",sender_node,receiver_node,message_size,tag);
        expeRecvHash.erase(make_pair(tag, make_pair(sender_node, receiver_node)));
        #ifdef NS3_MTP
        cs.ExitSection();
        #endif
        assert(ehd->flowTag.current_flow_id == -1 && ehd->flowTag.child_flow_id == -1);
        ehd->flowTag = flowTag;
        t2.msg_handler(t2.fun_arg);
        goto receiver_end_1st_section;
      } else {
        t2.count -= message_size;
        expeRecvHash[make_pair(tag, make_pair(sender_node, receiver_node))] = t2;
      }
    } else {
      receiver_pending_queue[std::make_pair(std::make_pair(receiver_node, sender_node),tag)] = flowTag;
      if (recvHash.find(make_pair(tag, make_pair(sender_node, receiver_node))) ==
          recvHash.end()) {
        recvHash[make_pair(tag, make_pair(sender_node, receiver_node))] =
            message_size;
      } else {
        recvHash[make_pair(tag, make_pair(sender_node, receiver_node))] +=
            message_size;
      }
    }
    #ifdef NS3_MTP
    cs.ExitSection();
    #endif
  receiver_end_1st_section:
    {
    #ifdef NS3_MTP
    MtpInterface::explicitCriticalSection cs2;
    #endif  
    if (nodeHash.find(make_pair(receiver_node, 1)) == nodeHash.end()) {
      nodeHash[make_pair(receiver_node, 1)] = message_size;
    } else {
      nodeHash[make_pair(receiver_node, 1)] += message_size;
    }
    #ifdef NS3_MTP
    cs2.ExitSection();
    #endif
    }
  }
}

void notify_sender_sending_finished(int sender_node, int receiver_node,
                                    uint64_t message_size, AstraSim::ncclFlowTag flowTag) {
  { 
    MockNcclLog * NcclLog = MockNcclLog::getInstance();
    #ifdef NS3_MTP
    MtpInterface::explicitCriticalSection cs;
    #endif    
    int tag = flowTag.tag_id;        
    if (sentHash.find(make_pair(tag, make_pair(sender_node, receiver_node))) !=
      sentHash.end()) {
      task1 t2 = sentHash[make_pair(tag, make_pair(sender_node, receiver_node))];
      AstraSim::SendPacketEventHandlerData* ehd = (AstraSim::SendPacketEventHandlerData*) t2.fun_arg;
      ehd->flowTag=flowTag;   
      if (t2.count == message_size) {
        sentHash.erase(make_pair(tag, make_pair(sender_node, receiver_node)));
        if (nodeHash.find(make_pair(sender_node, 0)) == nodeHash.end()) {
          nodeHash[make_pair(sender_node, 0)] = message_size;
        } else {
          nodeHash[make_pair(sender_node, 0)] += message_size;
        }
        #ifdef NS3_MTP
        cs.ExitSection();
        #endif
        t2.msg_handler(t2.fun_arg);
        goto sender_end_1st_section;
      }else{
        NcclLog->writeLog(NcclLogLevel::ERROR,"sentHash msg size != sender_node %d receiver_node %d message_size %lu flow_id ",sender_node,receiver_node,message_size);
      }
    }else{
      NcclLog->writeLog(NcclLogLevel::ERROR,"sentHash cann't find sender_node %d receiver_node %d message_size %lu",sender_node,receiver_node,message_size);
    }       
    #ifdef NS3_MTP
    cs.ExitSection();
    #endif
  }
sender_end_1st_section:
  return;
}


void notify_sender_packet_arrivered_receiver(int sender_node, int receiver_node,
                                    uint64_t message_size, AstraSim::ncclFlowTag flowTag) {
  int tag = flowTag.channel_id;
  if (sentHash.find(make_pair(tag, make_pair(sender_node, receiver_node))) !=
      sentHash.end()) {
    task1 t2 = sentHash[make_pair(tag, make_pair(sender_node, receiver_node))];
    AstraSim::SendPacketEventHandlerData* ehd = (AstraSim::SendPacketEventHandlerData*) t2.fun_arg;
    ehd->flowTag=flowTag;
    if (t2.count == message_size) {
      sentHash.erase(make_pair(tag, make_pair(sender_node, receiver_node)));
      if (nodeHash.find(make_pair(sender_node, 0)) == nodeHash.end()) {
        nodeHash[make_pair(sender_node, 0)] = message_size;
      } else {
        nodeHash[make_pair(sender_node, 0)] += message_size;
      }
      t2.msg_handler(t2.fun_arg);
    }
  }
}

void qp_finish(FILE *fout, Ptr<RdmaQueuePair> q) {
  uint32_t sid = ip_to_node_id(q->sip), did = ip_to_node_id(q->dip);
  uint64_t base_rtt = pairRtt[sid][did], b = pairBw[sid][did];
  uint32_t total_bytes =
      q->m_size +
      ((q->m_size - 1) / packet_payload_size + 1) *
          (CustomHeader::GetStaticWholeHeaderSize() -
           IntHeader::GetStaticSize()); 
  uint64_t standalone_fct = base_rtt + total_bytes * 8000000000lu / b;

  AstraSim::ncclFlowTag flowTag;
  uint64_t notify_size;
  int notify_src = sid;
  int notify_dst = did;
  PxnLegContext pxn_ctx;
  bool has_pxn_ctx = false;
  {
    #ifdef NS3_MTP
    MtpInterface::explicitCriticalSection cs;
    #endif
    Ptr<Node> dstNode = n.Get(did);
    Ptr<RdmaDriver> rdma = dstNode->GetObject<RdmaDriver>();
    rdma->m_rdma->DeleteRxQp(q->sip.Get(), q->m_pg, q->sport);
    MockNcclLog* NcclLog = MockNcclLog::getInstance();
    NcclLog->writeLog(NcclLogLevel::DEBUG,"qp finish, src:  %d did:  %d port:  %d total bytes:  %llu at the tick:  %d",sid,did,q->sport,q->m_size,AstraSim::Sys::boostedTick());
    auto flow_key = make_pair(q->sport, make_pair(sid, did));
    Ns3SubflowContext subflow_context;
    const bool has_subflow_context =
        ns3_lookup_subflow_context(flow_key, &subflow_context);
    if (sender_src_port_map.find(flow_key) ==
        sender_src_port_map.end()) {
      NcclLog->writeLog(NcclLogLevel::ERROR,"could not find the tag, there must be something wrong");
      exit(-1);
    }
    flowTag = sender_src_port_map[flow_key];
    sender_src_port_map.erase(flow_key);
    if (pxn_leg_context.find(flow_key) != pxn_leg_context.end()) {
      pxn_ctx = pxn_leg_context[flow_key];
      has_pxn_ctx = true;
      pxn_leg_context.erase(flow_key);
    }
    const PxnLogFields log_fields =
        build_pxn_log_fields(sid, did, flowTag, has_pxn_ctx, pxn_ctx);
    if (ns3_completion_log_enabled() && ns3_should_log_fct(flowTag)) {
      fprintf(fout, "%08x %08x %u %u %lu %lu %lu %lu %d %d %s %zu %zu %d\n",
              q->sip.Get(), q->dip.Get(), q->sport, q->dport, q->m_size,
              q->startTime.GetTimeStep(),
              (Simulator::Now() - q->startTime).GetTimeStep(), standalone_fct,
              log_fields.original_src, log_fields.original_dst,
              log_fields.leg_kind, log_fields.leg_index, log_fields.leg_count,
              log_fields.flow_id);
      fflush(fout);
    }
    if (has_subflow_context && ns3_should_log_fct(flowTag)) {
      ns3_write_stripe_metric(
          q,
          sid,
          did,
          flowTag,
          log_fields,
          subflow_context,
          standalone_fct);
    }
    if (has_subflow_context) {
      ns3_dynamic_chunk_receive_finished(subflow_context.dynamic_plan_id);
      ns3_mark_subflow_receive_finished(flow_key);
    }
    if (has_pxn_ctx && pxn_ctx.kind == PxnLegKind::Local) {
      if (pxn_ctx.next_leg_index >= pxn_ctx.legs.size()) {
        NcclLog->writeLog(NcclLogLevel::ERROR,
            "PXN local leg completed but no next leg exists, original src %d dst %d",
            pxn_ctx.original_src, pxn_ctx.original_dst);
        exit(-1);
      }
      auto next_leg = pxn_ctx.legs[pxn_ctx.next_leg_index];
      PxnLegKind next_kind =
          pxn_ctx.next_leg_index + 1 >= pxn_ctx.legs.size()
              ? PxnLegKind::Remote
              : PxnLegKind::Local;
      #ifdef NS3_MTP
      cs.ExitSection();
      #endif
      SendFlowPhysical(next_leg.first, next_leg.second, pxn_ctx.count, pxn_ctx.msg_handler,
                       pxn_ctx.fun_arg, pxn_ctx.tag, &pxn_ctx.request,
                       next_kind, pxn_ctx.original_src, pxn_ctx.original_dst,
                       pxn_ctx.legs, pxn_ctx.next_leg_index + 1);
      return;
    }
    if (has_pxn_ctx && pxn_ctx.kind == PxnLegKind::Remote) {
      notify_src = pxn_ctx.original_src;
      notify_dst = pxn_ctx.original_dst;
    }
    received_chunksize[std::make_pair(flowTag.current_flow_id,std::make_pair(notify_src,notify_dst))]+=q->m_size;
    if(!is_receive_finished(notify_src,notify_dst,flowTag)) {
      #ifdef NS3_MTP
      cs.ExitSection();
      #endif
      return; 
    }
    notify_size = received_chunksize[std::make_pair(flowTag.current_flow_id,std::make_pair(notify_src,notify_dst))];
    received_chunksize.erase(std::make_pair(flowTag.current_flow_id,std::make_pair(notify_src,notify_dst)));    
    #ifdef NS3_MTP
    cs.ExitSection();
    #endif
  }
  notify_receiver_receive_data(notify_src, notify_dst, notify_size, flowTag);
}

void send_finish(FILE *fout, Ptr<RdmaQueuePair> q) {
  uint32_t sid = ip_to_node_id(q->sip), did = ip_to_node_id(q->dip);
  const auto flow_key = make_pair(q->sport, make_pair(sid, did));
  Ns3SubflowContext subflow_context;
  if (ns3_mark_subflow_send_finished(flow_key, &subflow_context)) {
    if (subflow_context.dynamic_plan_id != 0) {
      Ptr<RdmaDriver> rdma = n.Get(sid)->GetObject<RdmaDriver>();
      rdma->m_rdma->ReleasePathReservationBytes(q);
    }
    // Register a replacement before decrementing the logical callback count,
    // so a staged plan cannot notify ASTRA-Sim between chunk waves.
    ns3_dynamic_chunk_send_finished(
        subflow_context.dynamic_plan_id, subflow_context.stripe_index);
  }
  AstraSim::ncclFlowTag flowTag;
  int notify_src = sid;
  int notify_dst = did;
  MockNcclLog* NcclLog = MockNcclLog::getInstance();
  NcclLog->writeLog(NcclLogLevel::DEBUG,"[Packet sent from NIC] send finish, src:  %d did:  %d port:  %d srcip  %d dstip  %d total bytes:  %llu at the tick:  %d",sid,did,q->sport,q->sip,q->dip,q->m_size,AstraSim::Sys::boostedTick());
  uint64_t all_sent_chunksize;
  {
    #ifdef NS3_MTP
    MtpInterface::explicitCriticalSection cs;
    #endif
    if (sender_src_port_map.find(flow_key) == sender_src_port_map.end()) {
      NcclLog->writeLog(NcclLogLevel::ERROR,"could not find the tag in send_finish");
      exit(-1);
    }
    flowTag = sender_src_port_map[flow_key];
    PxnLegContext pxn_ctx;
    bool has_pxn_ctx = false;
    if (pxn_leg_context.find(flow_key) != pxn_leg_context.end()) {
      pxn_ctx = pxn_leg_context[flow_key];
      has_pxn_ctx = true;
    }
    if (ns3_completion_log_enabled() && ns3_should_log_fct(flowTag)) {
      PxnLogFields log_fields =
          build_pxn_log_fields(sid, did, flowTag, has_pxn_ctx, pxn_ctx);
      fprintf(fout, "%08x %08x %u %u %lu %lu %lu %d %d %s %zu %zu %d\n",
              q->sip.Get(), q->dip.Get(), q->sport, q->dport, q->m_size,
              q->startTime.GetTimeStep(),
              (Simulator::Now() - q->startTime).GetTimeStep(),
              log_fields.original_src, log_fields.original_dst,
              log_fields.leg_kind, log_fields.leg_index, log_fields.leg_count,
              log_fields.flow_id);
      fflush(fout);
    }
    if (has_pxn_ctx) {
      if (pxn_ctx.kind == PxnLegKind::Local) {
        #ifdef NS3_MTP
        cs.ExitSection();
        #endif
        return;
      }
      if (pxn_ctx.kind == PxnLegKind::Remote) {
        notify_src = pxn_ctx.original_src;
        notify_dst = pxn_ctx.original_dst;
      }
    }
    sent_chunksize[std::make_pair(flowTag.current_flow_id,std::make_pair(notify_src,notify_dst))]+=q->m_size;
    if(!is_sending_finished(notify_src,notify_dst,flowTag)) {
      #ifdef NS3_MTP
      cs.ExitSection();
      #endif
      return;
    }
    all_sent_chunksize = sent_chunksize[std::make_pair(flowTag.current_flow_id,std::make_pair(notify_src,notify_dst))];
    sent_chunksize.erase(std::make_pair(flowTag.current_flow_id,std::make_pair(notify_src,notify_dst)));
    #ifdef NS3_MTP
    cs.ExitSection();
    #endif
  }
  notify_sender_sending_finished(notify_src, notify_dst, all_sent_chunksize, flowTag);
}

int main1(string network_topo,string network_conf) {
  clock_t begint, endt;
  begint = clock();

  if (!ReadConf(network_topo,network_conf))
    return -1;
  SetConfig();
  SetupNetwork(qp_finish,send_finish);
  if (!qlen_mon_file.empty() || !bw_mon_file.empty() ||
      !rate_mon_file.empty() || !cnp_mon_file.empty()) {
    schedule_monitor();
  }

std::cout << "Running Simulation.\n";
  fflush(stdout);
  NS_LOG_INFO("Run Simulation.");

  endt = clock();
  return 0;
}
#endif
