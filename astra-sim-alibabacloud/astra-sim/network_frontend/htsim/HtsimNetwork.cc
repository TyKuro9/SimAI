/*
 * Copyright (c) 2024, Alibaba Group;
 * Licensed under the Apache License, Version 2.0.
 */

#include "HtsimNetwork.h"

#include "astra-sim/system/Common.hh"
#include "astra-sim/system/MockNcclLog.h"
#include "astra-sim/system/RecvPacketEventHadndlerData.hh"
#include "astra-sim/system/SendPacketEventHandlerData.hh"

#include "eventlist.h"
#include "pipe.h"
#include "queue.h"
#include "roce.h"
#include "route.h"

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <deque>
#include <fstream>
#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>
#include <unordered_map>
#include <vector>

using namespace std;

std::map<std::pair<std::pair<int, int>, int>, AstraSim::ncclFlowTag>
    receiver_pending_queue;
std::map<std::pair<int, std::pair<int, int>>, htsim_task> expeRecvHash;
std::map<std::pair<int, std::pair<int, int>>, uint64_t> recvHash;
std::map<std::pair<int, std::pair<int, int>>, htsim_task> sentHash;
std::map<std::pair<int, int>, int64_t> nodeHash;
uint32_t node_num = 0;
uint32_t switch_num = 0;
uint32_t link_num = 0;
uint32_t nvswitch_num = 0;
uint32_t gpus_per_server = 1;
GPUType gpu_type = GPUType::NONE;
std::vector<int> NVswitchs;

namespace {

constexpr simtime_picosec kDefaultLinkLatencyPs = 1000000000ULL;
constexpr uint64_t kDefaultBandwidthGbps = 400;
constexpr uint32_t kDefaultMaxPaths = 16;
constexpr mem_b kDefaultQueueSizeBytes = 64ULL * 1024ULL * 1024ULL;

string route_strategy_value = "single";
string result_dir_value = "./experiments/htsim_results/csv/";
ofstream fct_file;
uint64_t default_bandwidth_gbps = kDefaultBandwidthGbps;
simtime_picosec base_latency_ps = kDefaultLinkLatencyPs;
bool htsim_stopped = false;
bool packet_level_enabled = true;
EventList htsim_eventlist;
vector<unique_ptr<EventSource>> owned_events;
size_t completed_flows_since_reclaim = 0;
uint64_t completed_flow_sequence = 0;
uint64_t htsim_events_processed = 0;
constexpr size_t kDefaultFlowReclaimBatchSize = 262144;
constexpr size_t kFlowReclaimScanInterval = 4096;
constexpr uint64_t kPeriodicEventReclaimInterval = 65536;

class CallbackEvent : public EventSource {
 public:
  CallbackEvent(
      EventList& eventlist,
      void (*fun_ptr)(void* fun_arg),
      void* fun_arg)
      : EventSource(eventlist, "simai_htsim_callback"),
        fun_ptr(fun_ptr),
        fun_arg(fun_arg) {}

  void doNextEvent() override {
    if (fun_ptr != nullptr) {
      fun_ptr(fun_arg);
    }
    done = true;
  }

  bool is_done() const {
    return done;
  }

 private:
  void (*fun_ptr)(void* fun_arg);
  void* fun_arg;
  bool done = false;
};

struct HtsimFlowOwner;

struct FlowCompletion {
  int src;
  int dst;
  uint64_t count;
  simtime_picosec start_time;
  simtime_picosec finish_time;
  AstraSim::ncclFlowTag flowTag;
  HtsimFlowOwner* owner;
};

GPUType parse_gpu_type(const string& value);
uint64_t parse_bandwidth_gbps(const string& token);
simtime_picosec parse_latency_ps(const string& token);
void flow_completion_callback(void* arg);
size_t flow_reclaim_batch_size();

struct EdgeKey {
  int src;
  int dst;

  bool operator<(const EdgeKey& other) const {
    if (src != other.src) {
      return src < other.src;
    }
    return dst < other.dst;
  }
};

struct SimaiLink {
  int src = 0;
  int dst = 0;
  uint64_t bandwidth_gbps = kDefaultBandwidthGbps;
  simtime_picosec latency_ps = kDefaultLinkLatencyPs;
};

class FlowDoneTrigger : public Trigger {
 public:
  FlowDoneTrigger(EventList& eventlist, triggerid_t id, FlowCompletion* completion)
      : Trigger(eventlist, id), completion(completion), done(false) {}

  void activate() override {
    if (done) {
      return;
    }
    done = true;
    completion->finish_time = EventList::now();
    flow_completion_callback(completion);
    completion = nullptr;
  }

 private:
  FlowCompletion* completion;
  bool done;
};

struct HtsimFlowOwner {
  unique_ptr<RoceSrc> src;
  unique_ptr<RoceSink> sink;
  unique_ptr<Route> route_out;
  unique_ptr<Route> route_in;
  unique_ptr<FlowDoneTrigger> trigger;
  int src_node = -1;
  int dst_node = -1;
  uint64_t bytes = 0;
  simtime_picosec start_time = 0;
  AstraSim::ncclFlowTag flowTag;
  bool done = false;
  uint64_t completion_sequence = 0;
};

class SimaiPacketTopology {
 public:
  bool load(const string& topology_file) {
    ifstream topof(topology_file.c_str());
    if (!topof.is_open()) {
      cerr << "Unable to open htsim topology input: " << topology_file << endl;
      return false;
    }

    string gpu_type_str;
    topof >> node_num >> gpus_per_server >> nvswitch_num >> switch_num >>
        link_num >> gpu_type_str;
    gpu_type = parse_gpu_type(gpu_type_str);
    const int gpu_count =
        static_cast<int>(node_num - nvswitch_num - switch_num);
    if (gpu_count <= 0 || node_num == 0) {
      cerr << "invalid htsim topology header in " << topology_file << endl;
      return false;
    }

    NVswitchs.clear();
    for (uint32_t i = 0; i < nvswitch_num; i++) {
      uint32_t sid = 0;
      topof >> sid;
      NVswitchs.push_back(static_cast<int>(sid));
    }
    for (uint32_t i = 0; i < switch_num; i++) {
      uint32_t sid = 0;
      topof >> sid;
    }

    adjacency.assign(node_num, {});
    reverse_adjacency.assign(node_num, {});
    uint32_t parsed_links = 0;
    int src = 0;
    int dst = 0;
    string bandwidth;
    string latency;
    int error_rate = 0;
    while (topof >> src >> dst >> bandwidth >> latency >> error_rate) {
      if (src < 0 || dst < 0 || src >= static_cast<int>(node_num) ||
          dst >= static_cast<int>(node_num)) {
        cerr << "invalid htsim topology edge " << src << " -> " << dst
             << " in " << topology_file << endl;
        return false;
      }
      SimaiLink link;
      link.src = src;
      link.dst = dst;
      link.bandwidth_gbps = parse_bandwidth_gbps(bandwidth);
      link.latency_ps = parse_latency_ps(latency);
      add_directed_link(link);
      swap(link.src, link.dst);
      add_directed_link(link);
      if (parsed_links == 0) {
        default_bandwidth_gbps = link.bandwidth_gbps;
        base_latency_ps = link.latency_ps;
      }
      parsed_links++;
    }

    if (parsed_links == 0) {
      cerr << "htsim packet topology has no links: " << topology_file << endl;
      return false;
    }

    cout << "[htsim] packet topology nodes=" << node_num
         << " switches=" << switch_num << " nvswitches=" << nvswitch_num
         << " links=" << parsed_links << " directed_links=" << queues.size()
         << " gpus_per_server=" << gpus_per_server
         << " route_strategy=" << route_strategy_value << endl;
    return true;
  }

  vector<const Route*>* get_paths(int src, int dst) {
    auto key = make_pair(src, dst);
    auto cached = path_cache.find(key);
    if (cached != path_cache.end()) {
      return &cached->second;
    }

    vector<vector<int>> node_paths = find_shortest_paths(src, dst);
    auto& routes = path_cache[key];
    routes.reserve(node_paths.size());
    for (size_t i = 0; i < node_paths.size(); i++) {
      unique_ptr<Route> route(new Route());
      for (size_t hop = 0; hop + 1 < node_paths[i].size(); hop++) {
        EdgeKey edge{node_paths[i][hop], node_paths[i][hop + 1]};
        auto q = queues.find(edge);
        auto p = pipes.find(edge);
        if (q == queues.end() || p == pipes.end()) {
          throw runtime_error("missing htsim directed edge while building route");
        }
        route->push_back(q->second.get());
        route->push_back(p->second.get());
      }
      route->set_path_id(static_cast<int>(i), static_cast<int>(node_paths.size()));
      routes.push_back(route.get());
      owned_routes.push_back(std::move(route));
    }
    return &routes;
  }

  linkspeed_bps sender_rate(int src, int dst) const {
    if (src >= 0 && src < static_cast<int>(adjacency.size())) {
      for (int next : adjacency[src]) {
        auto link = links.find(EdgeKey{src, next});
        if (link != links.end()) {
          return speedFromGbps(static_cast<double>(link->second.bandwidth_gbps));
        }
      }
    }
    return speedFromGbps(static_cast<double>(default_bandwidth_gbps));
  }

  unique_ptr<Route> build_ns3_ecmp_route(
      int src,
      int dst,
      const AstraSim::ncclFlowTag& flowTag,
      PacketSink& endpoint) {
    vector<int>& dist = distances_to_dst(dst);
    if (src < 0 || dst < 0 || src >= static_cast<int>(dist.size()) ||
        dst >= static_cast<int>(dist.size()) ||
        dist[src] == numeric_limits<int>::max()) {
      throw runtime_error(
          "htsim topology has no ns3_ecmp path from " + to_string(src) +
          " to " + to_string(dst));
    }

    unique_ptr<Route> route(new Route());
    int current = src;
    while (current != dst) {
      vector<int> next_hops;
      for (int next : adjacency[current]) {
        if (next >= 0 && next < static_cast<int>(dist.size()) &&
            dist[next] == dist[current] - 1) {
          next_hops.push_back(next);
        }
      }
      if (next_hops.empty()) {
        throw runtime_error(
            "htsim ns3_ecmp could not choose next hop from " +
            to_string(current) + " to " + to_string(dst));
      }
      sort(next_hops.begin(), next_hops.end());
      size_t choice = ns3_ecmp_next_hop_choice(
          src, dst, current, flowTag, next_hops.size());
      int next = next_hops[choice];
      append_link_to_route(current, next, route.get());
      current = next;
    }
    route->push_back(&endpoint);
    route->set_path_id(0, 1);
    return route;
  }

 private:
  void add_directed_link(const SimaiLink& link) {
    EdgeKey edge{link.src, link.dst};
    if (links.find(edge) != links.end()) {
      return;
    }
    links[edge] = link;
    adjacency[link.src].push_back(link.dst);
    reverse_adjacency[link.dst].push_back(link.src);

    linkspeed_bps speed = speedFromGbps(static_cast<double>(link.bandwidth_gbps));
    unique_ptr<Queue> queue(
        new Queue(speed, kDefaultQueueSizeBytes, htsim_eventlist, nullptr));
    unique_ptr<Pipe> pipe(new Pipe(link.latency_ps, htsim_eventlist));
    queue->forceName(
        "q_" + to_string(link.src) + "_" + to_string(link.dst));
    pipe->forceName(
        "p_" + to_string(link.src) + "_" + to_string(link.dst));
    queues[edge] = std::move(queue);
    pipes[edge] = std::move(pipe);
  }

  void append_link_to_route(int src, int dst, Route* route) {
    EdgeKey edge{src, dst};
    auto q = queues.find(edge);
    auto p = pipes.find(edge);
    if (q == queues.end() || p == pipes.end()) {
      throw runtime_error("missing htsim directed edge while building route");
    }
    route->push_back(q->second.get());
    route->push_back(p->second.get());
  }

  vector<vector<int>> find_shortest_paths(int src, int dst) const {
    if (src == dst) {
      return {{src}};
    }
    if (src < 0 || dst < 0 || src >= static_cast<int>(adjacency.size()) ||
        dst >= static_cast<int>(adjacency.size())) {
      throw runtime_error("htsim path endpoint outside topology");
    }

    vector<int> dist(adjacency.size(), numeric_limits<int>::max());
    vector<vector<int>> parents(adjacency.size());
    deque<int> todo;
    dist[src] = 0;
    todo.push_back(src);
    while (!todo.empty()) {
      int u = todo.front();
      todo.pop_front();
      if (u == dst) {
        continue;
      }
      for (int v : adjacency[u]) {
        if (dist[v] == numeric_limits<int>::max()) {
          dist[v] = dist[u] + 1;
          parents[v].push_back(u);
          todo.push_back(v);
        } else if (dist[v] == dist[u] + 1) {
          parents[v].push_back(u);
        }
      }
    }
    if (dist[dst] == numeric_limits<int>::max()) {
      throw runtime_error(
          "htsim topology has no path from " + to_string(src) + " to " +
          to_string(dst));
    }

    uint32_t max_paths = max_paths_limit();
    vector<vector<int>> results;
    vector<int> reversed;
    collect_paths(src, dst, parents, reversed, results, max_paths);
    for (auto& path : results) {
      reverse(path.begin(), path.end());
    }
    sort(results.begin(), results.end());
    return results;
  }

  vector<int>& distances_to_dst(int dst) {
    auto cached = distance_cache.find(dst);
    if (cached != distance_cache.end()) {
      return cached->second;
    }

    vector<int> dist(adjacency.size(), numeric_limits<int>::max());
    deque<int> todo;
    dist[dst] = 0;
    todo.push_back(dst);
    while (!todo.empty()) {
      int u = todo.front();
      todo.pop_front();
      for (int prev : reverse_adjacency[u]) {
        if (dist[prev] == numeric_limits<int>::max()) {
          dist[prev] = dist[u] + 1;
          todo.push_back(prev);
        }
      }
    }
    auto inserted = distance_cache.emplace(dst, std::move(dist));
    return inserted.first->second;
  }

  size_t ns3_ecmp_next_hop_choice(
      int src,
      int dst,
      int current,
      const AstraSim::ncclFlowTag& flowTag,
      size_t next_hop_count) const {
    uint64_t hash = 1469598103934665603ULL;
    auto mix = [&hash](uint64_t value) {
      hash ^= value + 0x9e3779b97f4a7c15ULL + (hash << 6) + (hash >> 2);
    };
    mix(static_cast<uint64_t>(src));
    mix(static_cast<uint64_t>(dst));
    mix(static_cast<uint64_t>(current));
    mix(static_cast<uint64_t>(flowTag.tag_id));
    mix(static_cast<uint64_t>(flowTag.channel_id));
    mix(static_cast<uint64_t>(flowTag.chunk_id));
    mix(static_cast<uint64_t>(flowTag.current_flow_id));
    mix(static_cast<uint64_t>(flowTag.child_flow_id));
    return static_cast<size_t>(hash % next_hop_count);
  }

  void collect_paths(
      int src,
      int current,
      const vector<vector<int>>& parents,
      vector<int>& reversed,
      vector<vector<int>>& results,
      uint32_t max_paths) const {
    if (results.size() >= max_paths) {
      return;
    }
    reversed.push_back(current);
    if (current == src) {
      results.push_back(reversed);
      reversed.pop_back();
      return;
    }
    vector<int> ordered = parents[current];
    sort(ordered.begin(), ordered.end());
    for (int parent : ordered) {
      collect_paths(src, parent, parents, reversed, results, max_paths);
      if (results.size() >= max_paths) {
        break;
      }
    }
    reversed.pop_back();
  }

  uint32_t max_paths_limit() const {
    const char* env_paths = getenv("HTSIM_MAX_PATHS");
    if (env_paths != nullptr && env_paths[0] != '\0') {
      return max<uint32_t>(1, strtoul(env_paths, nullptr, 10));
    }
    return kDefaultMaxPaths;
  }

  vector<vector<int>> adjacency;
  vector<vector<int>> reverse_adjacency;
  map<EdgeKey, SimaiLink> links;
  map<EdgeKey, unique_ptr<Queue>> queues;
  map<EdgeKey, unique_ptr<Pipe>> pipes;
  vector<unique_ptr<Route>> owned_routes;
  map<pair<int, int>, vector<const Route*>> path_cache;
  map<int, vector<int>> distance_cache;
};

unique_ptr<SimaiPacketTopology> packet_topology;
vector<unique_ptr<HtsimFlowOwner>> owned_flows;
uint64_t next_flow_id = 1;

void reclaim_completed_flows() {
  if (completed_flows_since_reclaim == 0) {
    return;
  }
  const size_t reclaim_batch = flow_reclaim_batch_size();

  owned_flows.erase(
      remove_if(
          owned_flows.begin(),
          owned_flows.end(),
          [reclaim_batch](const unique_ptr<HtsimFlowOwner>& flow) {
            if (flow == nullptr || !flow->done) {
              return false;
            }
            if (completed_flow_sequence - flow->completion_sequence <
                reclaim_batch) {
              return false;
            }
            if (flow->src != nullptr) {
              EventList::cancelPendingSource(*flow->src);
            }
            return true;
          }),
      owned_flows.end());
  completed_flows_since_reclaim = 0;
}

void reclaim_completed_events() {
  owned_events.erase(
      remove_if(
          owned_events.begin(),
          owned_events.end(),
          [](const unique_ptr<EventSource>& event) {
            const auto* callback =
                dynamic_cast<const CallbackEvent*>(event.get());
            return callback != nullptr && callback->is_done();
          }),
      owned_events.end());
}

size_t flow_reclaim_batch_size() {
  static const size_t value = []() {
    const char* env_batch = getenv("HTSIM_FLOW_RECLAIM_BATCH");
    if (env_batch != nullptr && env_batch[0] != '\0') {
      return max<size_t>(1, strtoull(env_batch, nullptr, 10));
    }
    return kDefaultFlowReclaimBatchSize;
  }();
  return value;
}

GPUType parse_gpu_type(const string& value) {
  if (value == "A100" || value == "a100") {
    return GPUType::A100;
  }
  if (value == "A800" || value == "a800") {
    return GPUType::A800;
  }
  if (value == "H100" || value == "h100") {
    return GPUType::H100;
  }
  if (value == "H800" || value == "h800") {
    return GPUType::H800;
  }
  if (value == "H20" || value == "h20") {
    return GPUType::H20;
  }
  return GPUType::NONE;
}

uint64_t parse_bandwidth_gbps(const string& token) {
  size_t idx = 0;
  while (idx < token.size() && (isdigit(token[idx]) || token[idx] == '.')) {
    idx++;
  }
  if (idx == 0) {
    return kDefaultBandwidthGbps;
  }
  double value = atof(token.substr(0, idx).c_str());
  string unit = token.substr(idx);
  transform(unit.begin(), unit.end(), unit.begin(), ::tolower);
  if (unit.find("tbps") != string::npos) {
    value *= 1000.0;
  } else if (unit.find("mbps") != string::npos) {
    value /= 1000.0;
  }
  return max<uint64_t>(1, static_cast<uint64_t>(value));
}

simtime_picosec parse_latency_ps(const string& token) {
  size_t idx = 0;
  while (idx < token.size() && (isdigit(token[idx]) || token[idx] == '.')) {
    idx++;
  }
  if (idx == 0) {
    return kDefaultLinkLatencyPs;
  }
  double value = atof(token.substr(0, idx).c_str());
  string unit = token.substr(idx);
  transform(unit.begin(), unit.end(), unit.begin(), ::tolower);
  if (unit.find("ms") != string::npos) {
    value *= 1000000000.0;
  } else if (unit.find("us") != string::npos) {
    value *= 1000000.0;
  } else if (unit.find("ns") != string::npos) {
    value *= 1000.0;
  }
  return max<simtime_picosec>(1, static_cast<simtime_picosec>(value));
}

simtime_picosec flow_delay_ps(uint64_t bytes) {
  uint64_t bandwidth = default_bandwidth_gbps;
  const char* bw_env = getenv("HTSIM_LINK_BW_GBPS");
  if (bw_env != nullptr) {
    bandwidth = max<uint64_t>(1, strtoull(bw_env, nullptr, 10));
  }

  simtime_picosec serialization =
      static_cast<simtime_picosec>((bytes * 8.0 * 1000.0) / bandwidth);
  simtime_picosec delay = base_latency_ps + serialization;
  if (route_strategy_value == "spray_rr" ||
      route_strategy_value == "spray_incremental" ||
      route_strategy_value == "spray_oblivious" ||
      route_strategy_value == "spray_plb" ||
      route_strategy_value == "plb" ||
      route_strategy_value == "spray_reps" ||
      route_strategy_value == "reps") {
    delay = static_cast<simtime_picosec>(delay * 0.95);
  }
  return max<simtime_picosec>(1, delay);
}

bool fallback_task_accepts_flow_tag(
    const htsim_task& task,
    const AstraSim::ncclFlowTag& flowTag) {
  auto* ehd =
      static_cast<AstraSim::RecvPacketEventHadndlerData*>(task.fun_arg);
  if (ehd == nullptr) {
    return true;
  }
  const AstraSim::ncclFlowTag& expected = ehd->flowTag;
  if (expected.receiver_node >= 0 &&
      flowTag.receiver_node != expected.receiver_node) {
    return false;
  }
  if (expected.channel_id >= 0 && flowTag.channel_id != expected.channel_id) {
    return false;
  }
  if (expected.tree_flow_list.empty() || flowTag.tree_flow_list.empty()) {
    return true;
  }
  for (int next_flow_id : flowTag.tree_flow_list) {
    if (next_flow_id == -1) {
      continue;
    }
    bool found = false;
    for (int expected_flow_id : expected.tree_flow_list) {
      if (expected_flow_id == next_flow_id) {
        found = true;
        break;
      }
    }
    if (!found) {
      return false;
    }
  }
  return true;
}

bool flow_tag_has_specific_successor(const AstraSim::ncclFlowTag& flowTag) {
  for (int next_flow_id : flowTag.tree_flow_list) {
    if (next_flow_id != -1) {
      return true;
    }
  }
  return false;
}

bool find_unique_expected_recv_by_route(
    int src,
    int dst,
    uint64_t count,
    int reference_tag,
    const AstraSim::ncclFlowTag& flowTag,
    pair<int, pair<int, int>>& found_key,
    htsim_task& found_task) {
  bool found = false;
  long long best_diff = 0;
  for (const auto& item : expeRecvHash) {
    if (item.first.second.first != src || item.first.second.second != dst ||
        item.second.count != count) {
      continue;
    }
    if (!fallback_task_accepts_flow_tag(item.second, flowTag)) {
      continue;
    }
    long long diff = item.first.first > reference_tag
        ? static_cast<long long>(item.first.first) - reference_tag
        : static_cast<long long>(reference_tag) - item.first.first;
    if (found && diff == best_diff) {
      return false;
    }
    if (found && diff > best_diff) {
      continue;
    }
    found = true;
    best_diff = diff;
    found_key = item.first;
    found_task = item.second;
  }
  return found;
}

bool find_unique_expected_recv_by_flow_tag(
    int dst,
    uint64_t count,
    int reference_tag,
    const AstraSim::ncclFlowTag& flowTag,
    pair<int, pair<int, int>>& found_key,
    htsim_task& found_task) {
  if (!flow_tag_has_specific_successor(flowTag)) {
    return false;
  }
  bool found = false;
  long long best_diff = 0;
  for (const auto& item : expeRecvHash) {
    if (item.first.second.second != dst || item.second.count != count) {
      continue;
    }
    if (!fallback_task_accepts_flow_tag(item.second, flowTag)) {
      continue;
    }
    long long diff = item.first.first > reference_tag
        ? static_cast<long long>(item.first.first) - reference_tag
        : static_cast<long long>(reference_tag) - item.first.first;
    if (found && diff == best_diff) {
      return false;
    }
    if (found && diff > best_diff) {
      continue;
    }
    found = true;
    best_diff = diff;
    found_key = item.first;
    found_task = item.second;
  }
  return found;
}

bool find_unique_arrived_recv_by_route(
    int src,
    int dst,
    uint64_t count,
    int reference_tag,
    const htsim_task& expected_task,
    pair<int, pair<int, int>>& found_key) {
  bool found = false;
  long long best_diff = 0;
  for (const auto& item : recvHash) {
    if (item.first.second.first != src || item.first.second.second != dst ||
        item.second != count) {
      continue;
    }
    auto pending_it = receiver_pending_queue.find(
        make_pair(make_pair(dst, src), item.first.first));
    if (pending_it == receiver_pending_queue.end() ||
        !fallback_task_accepts_flow_tag(expected_task, pending_it->second)) {
      continue;
    }
    long long diff = item.first.first > reference_tag
        ? static_cast<long long>(item.first.first) - reference_tag
        : static_cast<long long>(reference_tag) - item.first.first;
    if (found && diff == best_diff) {
      return false;
    }
    if (found && diff > best_diff) {
      continue;
    }
    found = true;
    best_diff = diff;
    found_key = item.first;
  }
  return found;
}

bool find_unique_arrived_recv_by_flow_tag(
    int reference_tag,
    const htsim_task& expected_task,
    pair<int, pair<int, int>>& found_key) {
  bool found = false;
  long long best_diff = 0;
  for (const auto& item : recvHash) {
    if (item.first.second.second != expected_task.dest ||
        item.second != expected_task.count) {
      continue;
    }
    auto pending_it = receiver_pending_queue.find(
        make_pair(
            make_pair(item.first.second.second, item.first.second.first),
            item.first.first));
    if (pending_it == receiver_pending_queue.end() ||
        !flow_tag_has_specific_successor(pending_it->second) ||
        !fallback_task_accepts_flow_tag(expected_task, pending_it->second)) {
      continue;
    }
    long long diff = item.first.first > reference_tag
        ? static_cast<long long>(item.first.first) - reference_tag
        : static_cast<long long>(reference_tag) - item.first.first;
    if (found && diff == best_diff) {
      return false;
    }
    if (found && diff > best_diff) {
      continue;
    }
    found = true;
    best_diff = diff;
    found_key = item.first;
  }
  return found;
}

void notify_receiver_receive_data(
    int sender_node,
    int receiver_node,
    uint64_t message_size,
    AstraSim::ncclFlowTag flowTag) {
  int tag = flowTag.tag_id;
  auto key = make_pair(tag, make_pair(sender_node, receiver_node));
  auto pending_key = make_pair(make_pair(receiver_node, sender_node), tag);
  auto expected = expeRecvHash.find(key);

  if (expected != expeRecvHash.end()) {
    htsim_task task = expected->second;
    auto* ehd =
        static_cast<AstraSim::RecvPacketEventHadndlerData*>(task.fun_arg);

    if (message_size >= task.count) {
      expeRecvHash.erase(expected);
      if (message_size > task.count) {
        recvHash[key] = message_size - task.count;
      }
      if (ehd->flowTag.current_flow_id == -1 &&
          ehd->flowTag.child_flow_id == -1) {
        ehd->flowTag = flowTag;
      }
      if (task.msg_handler != nullptr && ehd->node != nullptr &&
          ehd->owner != nullptr) {
        task.msg_handler(task.fun_arg);
      } else {
        delete ehd;
      }
    } else {
      task.count -= message_size;
      expeRecvHash[key] = task;
    }
  } else {
    pair<int, pair<int, int>> fallback_key = key;
    htsim_task fallback_task;
    if (find_unique_expected_recv_by_route(
            sender_node,
            receiver_node,
            message_size,
            tag,
            flowTag,
            fallback_key,
            fallback_task)) {
      auto* ehd =
          static_cast<AstraSim::RecvPacketEventHadndlerData*>(
              fallback_task.fun_arg);
      expeRecvHash.erase(fallback_key);
      if (ehd->flowTag.current_flow_id == -1 &&
          ehd->flowTag.child_flow_id == -1) {
        ehd->flowTag = flowTag;
      }
      if (fallback_task.msg_handler != nullptr && ehd->node != nullptr &&
          ehd->owner != nullptr) {
        fallback_task.msg_handler(fallback_task.fun_arg);
      } else {
        delete ehd;
      }
      nodeHash[make_pair(receiver_node, 1)] += message_size;
      return;
    }
    if (find_unique_expected_recv_by_flow_tag(
            receiver_node,
            message_size,
            tag,
            flowTag,
            fallback_key,
            fallback_task)) {
      auto* ehd =
          static_cast<AstraSim::RecvPacketEventHadndlerData*>(
              fallback_task.fun_arg);
      expeRecvHash.erase(fallback_key);
      if (ehd->flowTag.current_flow_id == -1 &&
          ehd->flowTag.child_flow_id == -1) {
        ehd->flowTag = flowTag;
      }
      if (fallback_task.msg_handler != nullptr && ehd->node != nullptr &&
          ehd->owner != nullptr) {
        fallback_task.msg_handler(fallback_task.fun_arg);
      } else {
        delete ehd;
      }
      nodeHash[make_pair(receiver_node, 1)] += message_size;
      return;
    }
    receiver_pending_queue[pending_key] = flowTag;
    recvHash[key] += message_size;
  }

  nodeHash[make_pair(receiver_node, 1)] += message_size;
}

void notify_sender_sending_finished(
    int sender_node,
    int receiver_node,
    uint64_t message_size,
    AstraSim::ncclFlowTag flowTag) {
  int tag = flowTag.tag_id;
  auto key = make_pair(tag, make_pair(sender_node, receiver_node));
  auto sent = sentHash.find(key);
  if (sent == sentHash.end()) {
    MockNcclLog::getInstance()->writeLog(
        NcclLogLevel::ERROR,
        "htsim sentHash cannot find sender %d receiver %d message_size %lu",
        sender_node,
        receiver_node,
        message_size);
    return;
  }

  htsim_task task = sent->second;
  auto* ehd = static_cast<AstraSim::SendPacketEventHandlerData*>(task.fun_arg);
  ehd->flowTag = flowTag;
  sentHash.erase(sent);
  nodeHash[make_pair(sender_node, 0)] += message_size;
  if (task.msg_handler != nullptr && ehd->node != nullptr) {
    task.msg_handler(task.fun_arg);
  } else {
    delete ehd;
  }
}

void flow_completion_callback(void* arg) {
  unique_ptr<FlowCompletion> completion(static_cast<FlowCompletion*>(arg));
  if (fct_file.is_open()) {
    fct_file << completion->src << " " << completion->dst << " "
             << completion->flowTag.tag_id << " "
             << completion->flowTag.current_flow_id << " "
             << completion->count << " " << (completion->start_time / 1000.0)
             << " " << (completion->finish_time / 1000.0) << " "
             << ((completion->finish_time - completion->start_time) / 1000.0)
             << " " << route_strategy_value << "\n";
  }
  notify_receiver_receive_data(
      completion->src,
      completion->dst,
      completion->count,
      completion->flowTag);
  notify_sender_sending_finished(
      completion->src,
      completion->dst,
      completion->count,
      completion->flowTag);
  if (completion->owner != nullptr) {
    completion->owner->done = true;
    completion->owner->completion_sequence = ++completed_flow_sequence;
    completed_flows_since_reclaim++;
  }
}

void schedule_callback(
    simtime_picosec delay,
    void (*fun_ptr)(void* fun_arg),
    void* fun_arg) {
  auto event =
      unique_ptr<EventSource>(new CallbackEvent(htsim_eventlist, fun_ptr, fun_arg));
  EventSource* raw_event = event.get();
  owned_events.push_back(std::move(event));
  EventList::sourceIsPendingRel(*raw_event, delay);
}

bool flow_level_forced() {
  const char* value = getenv("HTSIM_FLOW_LEVEL");
  return value != nullptr && value[0] != '\0' && value[0] != '0';
}

bool fct_output_disabled() {
  const char* value = getenv("HTSIM_DISABLE_FCT_OUTPUT");
  if (value == nullptr || value[0] == '\0' || value[0] == '0') {
    return false;
  }
  string token(value);
  transform(token.begin(), token.end(), token.begin(), ::tolower);
  return token != "false" && token != "no" && token != "off";
}

bool tail_rto_enabled_for_strategy(const string& strategy) {
  const char* value = getenv("HTSIM_ROCE_TAIL_RTO");
  if (value != nullptr && value[0] != '\0') {
    string token(value);
    transform(token.begin(), token.end(), token.begin(), ::tolower);
    return token != "0" && token != "false" && token != "no" &&
        token != "off";
  }
  return strategy == "ns3_ecmp";
}

uint32_t roce_min_rto_us_for_strategy(const string& strategy) {
  const char* value = getenv("HTSIM_ROCE_MIN_RTO_US");
  if (value != nullptr && value[0] != '\0') {
    return max<uint32_t>(1, strtoul(value, nullptr, 10));
  }
  return strategy == "ns3_ecmp" ? 100U : static_cast<uint32_t>(DEFAULT_RTO_MIN);
}

uint64_t htsim_watchdog_event_interval() {
  static const uint64_t value = []() {
    const char* interval = getenv("HTSIM_WATCHDOG_EVENTS");
    if (interval == nullptr || interval[0] == '\0') {
      return 0ULL;
    }
    return strtoull(interval, nullptr, 10);
  }();
  return value;
}

size_t htsim_watchdog_sample_limit() {
  static const size_t value = []() {
    const char* limit = getenv("HTSIM_WATCHDOG_SAMPLE_FLOWS");
    if (limit == nullptr || limit[0] == '\0') {
      return static_cast<size_t>(8);
    }
    return max<size_t>(1, strtoull(limit, nullptr, 10));
  }();
  return value;
}

void dump_htsim_watchdog_state(uint64_t event_count) {
  size_t active_flows = 0;
  size_t started_flows = 0;
  size_t printed = 0;
  for (const auto& flow : owned_flows) {
    if (flow == nullptr || flow->done) {
      continue;
    }
    active_flows++;
    if (flow->src != nullptr && flow->src->_flow_started) {
      started_flows++;
    }
  }

  cout << "[htsim watchdog] events=" << event_count
       << " now_ps=" << EventList::now()
       << " completed_flows=" << completed_flow_sequence
       << " owned_flows=" << owned_flows.size()
       << " active_flows=" << active_flows
       << " started_flows=" << started_flows
       << " sentHash=" << sentHash.size()
       << " recvHash=" << recvHash.size()
       << " expeRecvHash=" << expeRecvHash.size()
       << " receiver_pending=" << receiver_pending_queue.size()
       << " owned_events=" << owned_events.size()
       << " strategy=" << route_strategy_value << endl;

  const size_t sample_limit = htsim_watchdog_sample_limit();
  for (const auto& flow : owned_flows) {
    if (flow == nullptr || flow->done || flow->src == nullptr) {
      continue;
    }
    cout << "[htsim watchdog]   flow src=" << flow->src_node
         << " dst=" << flow->dst_node
         << " tag=" << flow->flowTag.tag_id
         << " channel=" << flow->flowTag.channel_id
         << " current_flow=" << flow->flowTag.current_flow_id
         << " bytes=" << flow->bytes
         << " age_ps=" << (EventList::now() - flow->start_time)
         << " flow_id=" << flow->src->flow_id()
         << " started=" << flow->src->_flow_started
         << " src_last_acked=" << flow->src->_last_acked
         << " src_highest_sent=" << flow->src->_highest_sent
         << " packets_sent=" << flow->src->_packets_sent
         << " acks=" << flow->src->_acks_received
         << " nacks=" << flow->src->_nacks_received
         << " rtx=" << flow->src->_rtx_packets_sent;
    if (flow->sink != nullptr) {
      cout << " sink_cum_ack=" << flow->sink->cumulative_ack();
    }
    cout << endl;
    printed++;
    if (printed >= sample_limit) {
      break;
    }
  }
}

size_t stable_path_choice(int src, int dst, int tag, size_t path_count) {
  if (path_count == 0) {
    return 0;
  }
  uint64_t hash = 1469598103934665603ULL;
  auto mix = [&hash](uint64_t value) {
    hash ^= value + 0x9e3779b97f4a7c15ULL + (hash << 6) + (hash >> 2);
  };
  mix(static_cast<uint64_t>(src));
  mix(static_cast<uint64_t>(dst));
  mix(static_cast<uint64_t>(tag));
  return static_cast<size_t>(hash % path_count);
}

bool schedule_roce_packet_flow(
    int src,
    int dst,
    int tag,
    uint64_t count,
    const AstraSim::ncclFlowTag& flowTag) {
  if (!packet_level_enabled || packet_topology == nullptr || count == 0) {
    return false;
  }

  vector<const Route*>* paths_out = packet_topology->get_paths(src, dst);
  vector<const Route*>* paths_in = packet_topology->get_paths(dst, src);
  if (paths_out == nullptr || paths_in == nullptr || paths_out->empty() ||
      paths_in->empty()) {
    return false;
  }

  size_t choice = 0;
  if (route_strategy_value == "ecmp") {
    choice = stable_path_choice(src, dst, tag, paths_out->size());
  }
  if (route_strategy_value == "single") {
    choice = 0;
  }
  choice %= paths_out->size();
  size_t reverse_choice = min(choice, paths_in->size() - 1);

  unique_ptr<HtsimFlowOwner> flow(new HtsimFlowOwner());
  flow->src_node = src;
  flow->dst_node = dst;
  flow->bytes = count;
  flow->flowTag = flowTag;
  linkspeed_bps rate = packet_topology->sender_rate(src, dst);
  flow->src.reset(new RoceSrc(nullptr, nullptr, htsim_eventlist, rate));
  flow->sink.reset(new RoceSink());
  if (route_strategy_value == "spray_oblivious") {
    flow->src->set_route_strategy(RoceSrc::ROCE_ROUTE_OBLIVIOUS);
  } else if (
      route_strategy_value == "spray_plb" || route_strategy_value == "plb") {
    flow->src->set_route_strategy(RoceSrc::ROCE_ROUTE_PLB);
  } else if (
      route_strategy_value == "spray_reps" || route_strategy_value == "reps") {
    flow->src->set_route_strategy(RoceSrc::ROCE_ROUTE_REPS);
  } else {
    flow->src->set_route_strategy(RoceSrc::ROCE_ROUTE_INCREMENTAL);
  }
  flow->src->set_dst(dst);
  flow->src->set_flowsize(count);
  flow->src->set_flowid(static_cast<flowid_t>(next_flow_id++));
  flow->src->setName("Roce_" + to_string(src) + "_" + to_string(dst));
  flow->sink->set_src(src);
  flow->sink->setName("Roce_sink_" + to_string(src) + "_" + to_string(dst));

  simtime_picosec start_time = EventList::now();
  flow->start_time = start_time;
  FlowCompletion* completion =
      new FlowCompletion{src, dst, count, start_time, start_time, flowTag, flow.get()};
  flow->trigger.reset(new FlowDoneTrigger(
      htsim_eventlist,
      static_cast<triggerid_t>(next_flow_id++),
      completion));
  flow->src->set_end_trigger(*flow->trigger);

  if (route_strategy_value == "ns3_ecmp") {
    flow->route_out = packet_topology->build_ns3_ecmp_route(
        src, dst, flowTag, *flow->sink);
    reverse_choice = stable_path_choice(dst, src, tag, paths_in->size());
    flow->route_in.reset(new Route(*(paths_in->at(reverse_choice)), *flow->src));
  } else {
    flow->route_out.reset(new Route(*(paths_out->at(choice)), *flow->sink));
    flow->route_in.reset(new Route(*(paths_in->at(reverse_choice)), *flow->src));
  }
  flow->src->connect(
      flow->route_out.get(),
      flow->route_in.get(),
      *flow->sink,
      EventList::now());
  if (route_strategy_value != "single" && route_strategy_value != "ecmp" &&
      route_strategy_value != "ns3_ecmp" &&
      paths_out->size() > 1) {
    flow->src->set_paths(paths_out);
  }

  owned_flows.push_back(std::move(flow));
  return true;
}

}  // namespace

void htsim_dump_pending_state(size_t limit) {
  cerr << "[htsim debug] pending maps sentHash=" << sentHash.size()
       << " recvHash=" << recvHash.size()
       << " expeRecvHash=" << expeRecvHash.size()
       << " receiver_pending=" << receiver_pending_queue.size()
       << " nodeHash=" << nodeHash.size() << endl;

  map<tuple<int, int, uint64_t>, size_t> recv_routes;
  map<tuple<int, int, uint64_t>, size_t> expected_routes;
  for (const auto& item : recvHash) {
    recv_routes[make_tuple(
        item.first.second.first, item.first.second.second, item.second)]++;
  }
  for (const auto& item : expeRecvHash) {
    expected_routes[make_tuple(
        item.first.second.first, item.first.second.second, item.second.count)]++;
  }

  size_t recv_exact_route_hits = 0;
  size_t recv_reverse_route_hits = 0;
  for (const auto& item : recvHash) {
    auto exact_key = make_tuple(
        item.first.second.first, item.first.second.second, item.second);
    auto reverse_key = make_tuple(
        item.first.second.second, item.first.second.first, item.second);
    if (expected_routes.count(exact_key) != 0) {
      recv_exact_route_hits++;
    }
    if (expected_routes.count(reverse_key) != 0) {
      recv_reverse_route_hits++;
    }
  }

  size_t expected_exact_route_hits = 0;
  for (const auto& item : expeRecvHash) {
    auto exact_key = make_tuple(
        item.first.second.first, item.first.second.second, item.second.count);
    if (recv_routes.count(exact_key) != 0) {
      expected_exact_route_hits++;
    }
  }
  cerr << "[htsim debug] route overlap recv_exact="
       << recv_exact_route_hits
       << " expected_exact=" << expected_exact_route_hits
       << " recv_reverse=" << recv_reverse_route_hits
       << " recv_unique_routes=" << recv_routes.size()
       << " expected_unique_routes=" << expected_routes.size() << endl;

  auto print_flow_tag = [](const AstraSim::ncclFlowTag& flowTag) {
    cerr << " flowTag(tag=" << flowTag.tag_id
         << " ch=" << flowTag.channel_id
         << " chunk=" << flowTag.chunk_id
         << " current=" << flowTag.current_flow_id
         << " child=" << flowTag.child_flow_id
         << " sender=" << flowTag.sender_node
         << " receiver=" << flowTag.receiver_node
         << " size=" << flowTag.flow_size
         << " tree=[";
    size_t printed = 0;
    for (int flow_id : flowTag.tree_flow_list) {
      if (printed > 0) {
        cerr << ",";
      }
      cerr << flow_id;
      printed++;
      if (printed >= 8) {
        if (flowTag.tree_flow_list.size() > printed) {
          cerr << ",...";
        }
        break;
      }
    }
    cerr << "])";
  };

  size_t printed = 0;
  for (const auto& item : sentHash) {
    if (printed >= limit) {
      break;
    }
    cerr << "[htsim debug] sentHash tag=" << item.first.first
         << " src=" << item.first.second.first
         << " dst=" << item.first.second.second
         << " count=" << item.second.count
         << " type=" << item.second.type << endl;
    printed++;
  }

  printed = 0;
  for (const auto& item : recvHash) {
    if (printed >= limit) {
      break;
    }
    cerr << "[htsim debug] recvHash tag=" << item.first.first
         << " src=" << item.first.second.first
         << " dst=" << item.first.second.second
         << " bytes=" << item.second << endl;
    printed++;
  }

  printed = 0;
  for (const auto& item : expeRecvHash) {
    if (printed >= limit) {
      break;
    }
    cerr << "[htsim debug] expeRecvHash tag=" << item.first.first
         << " src=" << item.first.second.first
         << " dst=" << item.first.second.second
         << " count=" << item.second.count
         << " type=" << item.second.type;
    auto* ehd =
        static_cast<AstraSim::RecvPacketEventHadndlerData*>(item.second.fun_arg);
    if (ehd != nullptr) {
      print_flow_tag(ehd->flowTag);
    }
    cerr << endl;
    printed++;
  }

  printed = 0;
  for (const auto& item : receiver_pending_queue) {
    if (printed >= limit) {
      break;
    }
    cerr << "[htsim debug] receiver_pending receiver="
         << item.first.first.first
         << " sender=" << item.first.first.second
         << " tag=" << item.first.second;
    print_flow_tag(item.second);
    cerr << endl;
    printed++;
  }
}

bool htsim_load_topology_summary(const string& topology_file) {
  if (!flow_level_forced()) {
    packet_level_enabled = true;
    try {
      Packet::set_packet_size(9000);
      packet_topology.reset(new SimaiPacketTopology());
      if (packet_topology->load(topology_file)) {
        return true;
      }
    } catch (const exception& err) {
      cerr << "[htsim] packet topology load failed: " << err.what() << endl;
    }
    packet_topology.reset();
    packet_level_enabled = false;
    cerr << "[htsim] falling back to flow-level completion estimator" << endl;
  } else {
    packet_level_enabled = false;
    cerr << "[htsim] HTSIM_FLOW_LEVEL is set; using flow-level estimator"
         << endl;
  }

  ifstream topof(topology_file.c_str());
  if (!topof.is_open()) {
    cerr << "Unable to open htsim topology input: " << topology_file << endl;
    return false;
  }

  string gpu_type_str;
  topof >> node_num >> gpus_per_server >> nvswitch_num >> switch_num >>
      link_num >> gpu_type_str;
  gpu_type = parse_gpu_type(gpu_type_str);
  NVswitchs.clear();
  for (uint32_t i = 0; i < nvswitch_num; i++) {
    uint32_t sid = 0;
    topof >> sid;
    NVswitchs.push_back(static_cast<int>(sid));
  }
  for (uint32_t i = 0; i < switch_num; i++) {
    uint32_t sid = 0;
    topof >> sid;
  }

  int src = 0;
  int dst = 0;
  string bandwidth;
  string latency;
  int error_rate = 0;
  if (topof >> src >> dst >> bandwidth >> latency >> error_rate) {
    default_bandwidth_gbps = parse_bandwidth_gbps(bandwidth);
    base_latency_ps = parse_latency_ps(latency);
  }

  cout << "[htsim] topology summary nodes=" << node_num
       << " switches=" << switch_num << " nvswitches=" << nvswitch_num
       << " links=" << link_num << " gpus_per_server=" << gpus_per_server
       << " route_strategy=" << route_strategy_value << endl;
  return true;
}

void htsim_set_result_dir(const string& result_dir) {
  result_dir_value = result_dir;
  if (!result_dir_value.empty() && result_dir_value.back() != '/') {
    result_dir_value.push_back('/');
  }
  if (fct_file.is_open()) {
    fct_file.close();
  }
  if (fct_output_disabled()) {
    cout << "[htsim] fct output disabled by HTSIM_DISABLE_FCT_OUTPUT" << endl;
    return;
  }
  fct_file.open((result_dir_value + "fct.txt").c_str(), ios::out | ios::trunc);
  if (!fct_file.is_open()) {
    throw runtime_error("unable to open htsim fct output: " + result_dir_value + "fct.txt");
  }
  fct_file << "# src dst tag flow_id size_bytes start_ns end_ns fct_ns route_strategy\n";
}

void htsim_set_route_strategy(const string& strategy) {
  if (strategy == "single" || strategy == "ecmp" ||
      strategy == "ns3_ecmp" ||
      strategy == "spray_rr" || strategy == "spray_incremental" ||
      strategy == "spray_oblivious" || strategy == "spray_plb" ||
      strategy == "plb" || strategy == "spray_reps" ||
      strategy == "reps") {
    route_strategy_value = strategy;
    bool tail_rto_enabled = tail_rto_enabled_for_strategy(strategy);
    RoceSrc::setTailRTO(tail_rto_enabled);
    if (tail_rto_enabled) {
      RoceSrc::setMinRTO(roce_min_rto_us_for_strategy(strategy));
    }
    return;
  }
  throw invalid_argument("unsupported htsim route_strategy: " + strategy);
}

const string& htsim_route_strategy() {
  return route_strategy_value;
}

bool htsim_packet_level_enabled() {
  return packet_level_enabled;
}

void htsim_schedule_flow_completion(
    int src,
    int dst,
    uint64_t count,
    const AstraSim::ncclFlowTag& flowTag) {
  simtime_picosec start_time = EventList::now();
  simtime_picosec delay = flow_delay_ps(count);
  FlowCompletion* completion =
      new FlowCompletion{
          src, dst, count, start_time, start_time + delay, flowTag, nullptr};
  schedule_callback(delay, flow_completion_callback, completion);
}

void htsim_run(const function<void()>& watchdog_callback) {
  const uint64_t watchdog_interval = htsim_watchdog_event_interval();
  uint64_t next_watchdog_event = watchdog_interval;
  while (!htsim_stopped && EventList::doNextEvent()) {
    htsim_events_processed++;
    if (completed_flow_sequence >= flow_reclaim_batch_size() &&
        completed_flows_since_reclaim >= kFlowReclaimScanInterval) {
      reclaim_completed_flows();
    }
    if (htsim_events_processed % kPeriodicEventReclaimInterval == 0) {
      reclaim_completed_events();
    }
    if (watchdog_interval > 0 &&
        htsim_events_processed >= next_watchdog_event) {
      dump_htsim_watchdog_state(htsim_events_processed);
      if (watchdog_callback != nullptr) {
        watchdog_callback();
      }
      next_watchdog_event += watchdog_interval;
    }
  }
  htsim_events_processed = 0;
  reclaim_completed_flows();
  reclaim_completed_events();
}

void htsim_stop() {
  htsim_stopped = true;
}

void htsim_destroy() {
  if (fct_file.is_open()) {
    fct_file.flush();
    fct_file.close();
  }
  owned_flows.clear();
  packet_topology.reset();
  owned_events.clear();
}

HtsimNetwork::HtsimNetwork(int rank, int npu_offset)
    : AstraNetworkAPI(rank), npu_offset(npu_offset) {}

HtsimNetwork::~HtsimNetwork() {}

AstraSim::AstraNetworkAPI::BackendType HtsimNetwork::get_backend_type() {
  return AstraSim::AstraNetworkAPI::BackendType::NotSpecified;
}

int HtsimNetwork::sim_comm_size(AstraSim::sim_comm comm, int* size) {
  return 0;
}

int HtsimNetwork::sim_finish() {
  for (auto it = nodeHash.begin(); it != nodeHash.end(); it++) {
    pair<int, int> p = it->first;
    if (p.second == 0) {
      cout << "All data sent from node " << p.first << " is " << it->second
           << "\n";
    } else {
      cout << "All data received by node " << p.first << " is " << it->second
           << "\n";
    }
  }
  htsim_stop();
  return 0;
}

void HtsimNetwork::pass_front_end_report(
    AstraSim::AstraSimDataAPI astraSimDataAPI) {
  (void)astraSimDataAPI;
  htsim_stop();
}

double HtsimNetwork::sim_time_resolution() {
  return 0;
}

int HtsimNetwork::sim_init(AstraSim::AstraMemoryAPI* MEM) {
  return 0;
}

AstraSim::timespec_t HtsimNetwork::sim_get_time() {
  AstraSim::timespec_t timeSpec;
  timeSpec.time_res = AstraSim::time_type_e::NS;
  timeSpec.time_val = EventList::now() / 1000.0;
  return timeSpec;
}

void HtsimNetwork::sim_schedule(
    AstraSim::timespec_t delta,
    void (*fun_ptr)(void* fun_arg),
    void* fun_arg) {
  schedule_callback(
      static_cast<simtime_picosec>(max(0.0, delta.time_val) * 1000.0),
      fun_ptr,
      fun_arg);
}

int HtsimNetwork::sim_send(
    void* buffer,
    uint64_t count,
    int type,
    int dst,
    int tag,
    AstraSim::sim_request* request,
    void (*msg_handler)(void* fun_arg),
    void* fun_arg) {
  dst += npu_offset;
  htsim_task task;
  task.src = rank;
  task.dest = dst;
  task.count = count;
  task.type = 0;
  task.fun_arg = fun_arg;
  task.msg_handler = msg_handler;
  task.schTime = 0;
  sentHash[make_pair(tag, make_pair(task.src, task.dest))] = task;

  AstraSim::ncclFlowTag flowTag = request->flowTag;
  if (flowTag.tag_id == -1) {
    flowTag.tag_id = tag;
  }
  try {
    if (!schedule_roce_packet_flow(rank, dst, tag, count, flowTag)) {
      htsim_schedule_flow_completion(rank, dst, count, flowTag);
    }
  } catch (const exception& err) {
    cerr << "[htsim] failed to schedule packet-level RoCE flow "
         << rank << " -> " << dst << ": " << err.what() << endl;
    throw;
  }
  return 0;
}

int HtsimNetwork::sim_recv(
    void* buffer,
    uint64_t count,
    int type,
    int src,
    int tag,
    AstraSim::sim_request* request,
    void (*msg_handler)(void* fun_arg),
    void* fun_arg) {
  src += npu_offset;
  htsim_task task;
  task.src = src;
  task.dest = rank;
  task.count = count;
  task.type = 1;
  task.fun_arg = fun_arg;
  task.msg_handler = msg_handler;
  task.schTime = 0;

  auto* ehd = static_cast<AstraSim::RecvPacketEventHadndlerData*>(task.fun_arg);
  tag = ehd->flowTag.tag_id;
  auto key = make_pair(tag, make_pair(task.src, task.dest));

  auto received = recvHash.find(key);
  if (received != recvHash.end()) {
    uint64_t received_count = received->second;
    if (received_count >= task.count) {
      if (received_count == task.count) {
        recvHash.erase(received);
      } else {
        recvHash[key] = received_count - task.count;
      }
      auto pending_key = make_pair(make_pair(rank, src), tag);
      auto pending = receiver_pending_queue.find(pending_key);
      if (pending != receiver_pending_queue.end() &&
          ehd->flowTag.current_flow_id == -1 &&
          ehd->flowTag.child_flow_id == -1) {
        ehd->flowTag = pending->second;
        receiver_pending_queue.erase(pending);
      }
      task.msg_handler(task.fun_arg);
    } else {
      recvHash.erase(received);
      task.count -= received_count;
      expeRecvHash[key] = task;
    }
  } else {
    pair<int, pair<int, int>> fallback_key = key;
    if (find_unique_arrived_recv_by_route(
            task.src, task.dest, task.count, tag, task, fallback_key)) {
      uint64_t fallback_count = recvHash[fallback_key];
      recvHash.erase(fallback_key);
      auto pending_key = make_pair(make_pair(rank, src), fallback_key.first);
      auto pending = receiver_pending_queue.find(pending_key);
      if (pending != receiver_pending_queue.end() &&
          ehd->flowTag.current_flow_id == -1 &&
          ehd->flowTag.child_flow_id == -1) {
        ehd->flowTag = pending->second;
        receiver_pending_queue.erase(pending);
      }
      if (fallback_count > task.count) {
        recvHash[fallback_key] = fallback_count - task.count;
      }
      task.msg_handler(task.fun_arg);
      return 0;
    }
    if (find_unique_arrived_recv_by_flow_tag(tag, task, fallback_key)) {
      uint64_t fallback_count = recvHash[fallback_key];
      recvHash.erase(fallback_key);
      auto pending_key = make_pair(
          make_pair(fallback_key.second.second, fallback_key.second.first),
          fallback_key.first);
      auto pending = receiver_pending_queue.find(pending_key);
      if (pending != receiver_pending_queue.end() &&
          ehd->flowTag.current_flow_id == -1 &&
          ehd->flowTag.child_flow_id == -1) {
        ehd->flowTag = pending->second;
        receiver_pending_queue.erase(pending);
      }
      if (fallback_count > task.count) {
        recvHash[fallback_key] = fallback_count - task.count;
      }
      task.msg_handler(task.fun_arg);
      return 0;
    }
    expeRecvHash[key] = task;
  }
  return 0;
}
