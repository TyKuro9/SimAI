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
#define _QPS_PER_CONNECTION_  1
#include <algorithm>
#include "common.h"
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
#include <deque>
#include <atomic>
#include <set>
#include <unordered_map>
#include <mutex>
#include <vector>
#include "astra-sim/system/RecvPacketEventHadndlerData.hh"
#ifdef NS3_MTP
#include "ns3/mtp-interface.h"
#endif
#include <map>
#include"astra-sim/system/MockNcclQps.h"
#include "astra-sim/system/MockNcclLog.h"
using namespace ns3;
using namespace std;


using ReceiverPendingKey = std::pair<std::pair<int, int>, int>;
struct ReceiverPendingArrival {
  uint64_t remaining_count;
  AstraSim::ncclFlowTag flow_tag;
};
using ReceiverPendingArrivals = std::deque<ReceiverPendingArrival>;
std::map<ReceiverPendingKey, ReceiverPendingArrivals> receiver_pending_queue;
using LogicalFlowNotificationKey = std::tuple<int, int, int, int>;
std::set<LogicalFlowNotificationKey> receiver_notified_logical_flows;


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
std::atomic<uint64_t> receiver_callbacks_dispatched{0};
std::atomic<uint64_t> sender_callbacks_dispatched{0};

void dispatch_receiver_callback(const task1& task) {
  receiver_callbacks_dispatched.fetch_add(1, std::memory_order_relaxed);
  task.msg_handler(task.fun_arg);
}

void dispatch_sender_callback(const task1& task) {
  sender_callbacks_dispatched.fetch_add(1, std::memory_order_relaxed);
  task.msg_handler(task.fun_arg);
}
using ExpectedReceiveKey = std::pair<int, std::pair<int, int>>;
using ExpectedReceiveTasks = std::deque<task1>;
map<ExpectedReceiveKey, ExpectedReceiveTasks> expeRecvHash;
map<std::pair<int, std::pair<int, int>>, uint64_t> recvHash;
map<std::pair<int, std::pair<int, int>>, struct task1> sentHash;
map<std::pair<int, int>, int64_t> nodeHash;
map<std::pair<int,std::pair<int,int>>,int> waiting_to_sent_callback;  
map<std::pair<int,std::pair<int,int>>,int>waiting_to_notify_receiver;
map<std::pair<int,std::pair<int,int>>,uint64_t>received_chunksize;  
map<std::pair<int,std::pair<int,int>>,uint64_t>sent_chunksize;  

void enqueue_expected_receive(
    const ExpectedReceiveKey& key,
    const task1& task) {
  expeRecvHash[key].push_back(task);
}

bool front_expected_receive(
    const ExpectedReceiveKey& key,
    task1& task) {
  auto expected = expeRecvHash.find(key);
  if (expected == expeRecvHash.end() || expected->second.empty()) {
    return false;
  }
  task = expected->second.front();
  return true;
}

bool pop_expected_receive(
    const ExpectedReceiveKey& key,
    task1& task) {
  auto expected = expeRecvHash.find(key);
  if (expected == expeRecvHash.end() || expected->second.empty()) {
    return false;
  }
  task = expected->second.front();
  expected->second.pop_front();
  if (expected->second.empty()) {
    expeRecvHash.erase(expected);
  }
  return true;
}

size_t expected_receive_count() {
  size_t count = 0;
  for (const auto& expected : expeRecvHash) {
    count += expected.second.size();
  }
  return count;
}

void dump_receive_mismatch(size_t limit) {
  #ifdef NS3_MTP
  MtpInterface::explicitCriticalSection cs;
  #endif
  size_t printed = 0;
  size_t exact_key_overlap = 0;
  for (const auto& arrival : recvHash) {
    auto expected = expeRecvHash.find(arrival.first);
    if (expected != expeRecvHash.end() && !expected->second.empty()) {
      exact_key_overlap++;
    }
  }
  size_t recv_items = 0;
  for (const auto& arrival : recvHash) {
    recv_items += arrival.second;
  }
  std::cerr << "[NS3 debug] pending counts recv_keys=" << recvHash.size()
            << " expected_keys=" << expeRecvHash.size()
            << " recv_items=" << recv_items
            << " expected_items=" << expected_receive_count()
            << " exact_key_overlap=" << exact_key_overlap << std::endl;
  std::cerr << "[NS3 debug] pending arrivals" << std::endl;
  for (const auto& arrival : recvHash) {
    if (printed++ >= limit) {
      break;
    }
    int tag = arrival.first.first;
    int src = arrival.first.second.first;
    int dst = arrival.first.second.second;
    auto pending = receiver_pending_queue.find(
        make_pair(make_pair(dst, src), tag));
    std::cerr << "  arrival tag=" << tag
              << " src=" << src
              << " dst=" << dst
              << " count=" << arrival.second;
    if (pending != receiver_pending_queue.end() &&
        !pending->second.empty()) {
      const auto& flow_tag = pending->second.front().flow_tag;
      std::cerr << " flow_id=" << flow_tag.current_flow_id
                << " channel=" << flow_tag.channel_id
                << " sender=" << flow_tag.sender_node
                << " receiver=" << flow_tag.receiver_node;
    }
    std::cerr << std::endl;
  }

  printed = 0;
  std::cerr << "[NS3 debug] expected receives" << std::endl;
  for (const auto& expected : expeRecvHash) {
    if (printed++ >= limit) {
      break;
    }
    const auto& key = expected.first;
    std::cerr << "  expected tag=" << key.first
              << " src=" << key.second.first
              << " dst=" << key.second.second
              << " queued=" << expected.second.size();
    if (!expected.second.empty()) {
      auto* ehd = static_cast<AstraSim::RecvPacketEventHadndlerData*>(
          expected.second.front().fun_arg);
      if (ehd != nullptr) {
        std::cerr << " flow_id=" << ehd->flowTag.current_flow_id
                  << " expected_flow=" << ehd->flow_id
                  << " expected_chunk=" << ehd->flowTag.chunk_id
                  << " channel=" << ehd->flowTag.channel_id
                  << " sender=" << ehd->flowTag.sender_node
                  << " receiver=" << ehd->flowTag.receiver_node
                  << " stream=" << ehd->stream_num
                  << " phase_generation=" << ehd->phase_generation;
        if (ehd->owner != nullptr) {
          std::cerr << " owner_generation="
                    << ehd->owner->phase_generation.load(
                           std::memory_order_acquire)
                    << " owner_state=" << static_cast<int>(ehd->owner->state)
                    << " owner_queue=" << ehd->owner->current_queue_id
                    << " owner_phase_owner="
                    << ehd->owner->my_current_phase.algorithm
                    << " task_phase_owner=" << ehd->phase_owner;
        }
      }
    }
    std::cerr << std::endl;
  }
  #ifdef NS3_MTP
  cs.ExitSection();
  #endif
}

void enqueue_receiver_pending_arrival(
    int sender_node,
    int receiver_node,
    int tag,
    uint64_t count,
    const AstraSim::ncclFlowTag& flow_tag) {
  if (count == 0) {
    return;
  }
  auto recv_key = make_pair(tag, make_pair(sender_node, receiver_node));
  auto pending_key =
      make_pair(make_pair(receiver_node, sender_node), tag);
  receiver_pending_queue[pending_key].push_back({count, flow_tag});
  recvHash[recv_key] += count;
}

bool consume_receiver_pending_arrival(
    int sender_node,
    int receiver_node,
    int tag,
    uint64_t count,
    AstraSim::ncclFlowTag& flow_tag) {
  auto recv_key = make_pair(tag, make_pair(sender_node, receiver_node));
  auto recv_it = recvHash.find(recv_key);
  auto pending_key =
      make_pair(make_pair(receiver_node, sender_node), tag);
  auto pending = receiver_pending_queue.find(pending_key);
  if (count == 0 || recv_it == recvHash.end() || recv_it->second < count ||
      pending == receiver_pending_queue.end() || pending->second.empty()) {
    return false;
  }

  uint64_t queued_count = 0;
  for (const auto& arrival : pending->second) {
    queued_count += arrival.remaining_count;
    if (queued_count >= count) {
      break;
    }
  }
  if (queued_count < count) {
    return false;
  }

  flow_tag = pending->second.front().flow_tag;
  uint64_t remaining = count;
  while (remaining > 0) {
    ReceiverPendingArrival& arrival = pending->second.front();
    uint64_t consumed = std::min(remaining, arrival.remaining_count);
    arrival.remaining_count -= consumed;
    remaining -= consumed;
    if (arrival.remaining_count == 0) {
      pending->second.pop_front();
    }
  }
  if (pending->second.empty()) {
    receiver_pending_queue.erase(pending);
  }
  recv_it->second -= count;
  if (recv_it->second == 0) {
    recvHash.erase(recv_it);
  }
  return true;
}

bool fallback_task_accepts_flow_tag(
    const task1& task,
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
  if (ehd->flow_id >= 0 && !flowTag.tree_flow_list.empty() &&
      std::find(
          flowTag.tree_flow_list.begin(),
          flowTag.tree_flow_list.end(),
          ehd->flow_id) == flowTag.tree_flow_list.end()) {
    return false;
  }
  if (expected.tree_flow_list.empty() || flowTag.tree_flow_list.empty()) {
    return true;
  }
  for (int next_flow_id : flowTag.tree_flow_list) {
    if (next_flow_id == -1) {
      continue;
    }
    if (std::find(
            expected.tree_flow_list.begin(),
            expected.tree_flow_list.end(),
            next_flow_id) == expected.tree_flow_list.end()) {
      return false;
    }
  }
  return true;
}

bool find_unique_expected_recv_by_route(
    int src,
    int dst,
    uint64_t count,
    int reference_tag,
    const AstraSim::ncclFlowTag& flowTag,
    pair<int, pair<int, int>>& found_key,
    task1& found_task) {
  bool found = false;
  long long best_diff = 0;
  for (const auto& item : expeRecvHash) {
    if (item.second.empty()) {
      continue;
    }
    const task1& candidate_task = item.second.front();
    if (item.first.second.first != src || item.first.second.second != dst ||
        candidate_task.count != count ||
        !fallback_task_accepts_flow_tag(candidate_task, flowTag)) {
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
    found_task = candidate_task;
  }
  return found;
}

bool find_unique_arrived_recv_by_route(
    int src,
    int dst,
    uint64_t count,
    int reference_tag,
    const task1& expected_task,
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
        pending_it->second.empty() ||
        !fallback_task_accepts_flow_tag(
            expected_task, pending_it->second.front().flow_tag)) {
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

int reconcile_pending_receives() {
  std::vector<task1> callbacks;
  {
    #ifdef NS3_MTP
    MtpInterface::explicitCriticalSection cs;
    #endif
    for (const auto& arrival : recvHash) {
      int tag = arrival.first.first;
      int src = arrival.first.second.first;
      int dst = arrival.first.second.second;
      uint64_t count = arrival.second;
      auto pending = receiver_pending_queue.find(
          make_pair(make_pair(dst, src), tag));
      if (pending == receiver_pending_queue.end() ||
          pending->second.empty()) {
        continue;
      }

      pair<int, pair<int, int>> expected_key = arrival.first;
      task1 expected_task;
      bool matched_by_route = false;
      auto expected = expeRecvHash.find(arrival.first);
      if (expected != expeRecvHash.end() && !expected->second.empty()) {
        expected_task = expected->second.front();
      } else if (find_unique_expected_recv_by_route(
                     src,
                     dst,
                     count,
                     tag,
                     pending->second.front().flow_tag,
                     expected_key,
                     expected_task)) {
        matched_by_route = true;
      } else {
        continue;
      }
      if (expected_task.count != count ||
          !fallback_task_accepts_flow_tag(
              expected_task, pending->second.front().flow_tag)) {
        continue;
      }

      AstraSim::ncclFlowTag flow_tag;
      if (!consume_receiver_pending_arrival(
              src, dst, tag, count, flow_tag)) {
        continue;
      }
      bool popped = pop_expected_receive(expected_key, expected_task);
      assert(popped);
      auto* ehd =
          static_cast<AstraSim::RecvPacketEventHadndlerData*>(
              expected_task.fun_arg);
      if (ehd != nullptr && ehd->flowTag.current_flow_id == -1 &&
          ehd->flowTag.child_flow_id == -1) {
        ehd->flowTag = flow_tag;
      }
      if (matched_by_route) {
        std::cerr << "[NS3] Reconciled receive by unique route: arrival_tag "
                  << tag << ", expected_tag " << expected_key.first
                  << ", src " << src << ", dst " << dst
                  << ", count " << count
                  << ", arrival_flow " << flow_tag.current_flow_id;
        if (ehd != nullptr) {
          std::cerr << ", expected_flow " << ehd->flow_id;
        }
        std::cerr << std::endl;
      }
      callbacks.push_back(expected_task);
      break;
    }
    #ifdef NS3_MTP
    cs.ExitSection();
    #endif
  }

  for (const task1& task : callbacks) {
    dispatch_receiver_callback(task);
  }
  return callbacks.size();
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

void SendFlow(int src, int dst, uint64_t maxPacketCount,
              void (*msg_handler)(void *fun_arg), void *fun_arg, int tag, AstraSim::sim_request *request) {
  MockNcclLog*NcclLog = MockNcclLog::getInstance();
  uint64_t PacketCount=((maxPacketCount+_QPS_PER_CONNECTION_-1)/_QPS_PER_CONNECTION_);
  uint64_t leftPacketCount = maxPacketCount;
  for(int index = 0 ;index<_QPS_PER_CONNECTION_;index++){
  uint64_t real_PacketCount = min(PacketCount,leftPacketCount);
  leftPacketCount-=real_PacketCount;
  uint32_t port = portNumber[src][dst]++; 
    {
      #ifdef NS3_MTP
      MtpInterface::explicitCriticalSection cs;
      #endif
      sender_src_port_map[make_pair(port, make_pair(src, dst))] = request->flowTag;
      #ifdef NS3_MTP
      cs.ExitSection();
      #endif
    }
  int flow_id = request->flowTag.current_flow_id;
  bool nvls_on = request->flowTag.nvls_on;
  int pg = 3, dport = 100;
  int send_lat = 6000;
  const char* send_lat_env = std::getenv("AS_SEND_LAT");
  if (send_lat_env) {
    try {
      send_lat = std::stoi(send_lat_env);
    } catch (const std::invalid_argument& e) {
      NcclLog->writeLog(NcclLogLevel::ERROR,"send_lat set error");
      exit(-1);
    }
  }
  send_lat *= 1000;
  flow_input.idx++;
  if(real_PacketCount == 0) real_PacketCount = 1;
    MockNcclLog* NcclLog = MockNcclLog::getInstance();
    NcclLog->writeLog(NcclLogLevel::DEBUG," [Packet sending event]  %dSendFlow to  %d channelid:  %d flow_id  %d srcip  %d dstip  %d size:  %llu at the tick:  %d",src,dst,tag,flow_id,serverAddress[src],serverAddress[dst],maxPacketCount,AstraSim::Sys::boostedTick());
    NcclLog->writeLog(NcclLogLevel::DEBUG," request->flowTag [Packet sending event]  %dSendFlow to  %d tag_id:  %d flow_id  %d srcip  %d dstip  %d size:  %llu at the tick:  %d",request->flowTag.sender_node,request->flowTag.receiver_node,request->flowTag.tag_id,request->flowTag.current_flow_id,serverAddress[src],serverAddress[dst],maxPacketCount,AstraSim::Sys::boostedTick());
  RdmaClientHelper clientHelper(
      pg, serverAddress[src], serverAddress[dst], port, dport, real_PacketCount,
      has_win ? (global_t == 1 ? maxBdp : pairBdp[n.Get(src)][n.Get(dst)]) : 0,
      global_t == 1 ? maxRtt : pairRtt[src][dst], msg_handler, fun_arg, tag,
      src, dst);
  if(nvls_on) clientHelper.SetAttribute("NVLS_enable", UintegerValue (1));
  int pending_receiver_callbacks = 0;
  {
    #ifdef NS3_MTP
    MtpInterface::explicitCriticalSection cs;
    #endif
    ApplicationContainer appCon = clientHelper.Install(n.Get(src));
    appCon.Start(Time(send_lat));
    waiting_to_sent_callback[std::make_pair(request->flowTag.current_flow_id,std::make_pair(src,dst))]++;
    waiting_to_notify_receiver[std::make_pair(request->flowTag.current_flow_id,std::make_pair(src,dst))]++;
    pending_receiver_callbacks = waiting_to_notify_receiver[std::make_pair(
        request->flowTag.current_flow_id, std::make_pair(src, dst))];
    #ifdef NS3_MTP
    cs.ExitSection();
    #endif
  }
  NcclLog->writeLog(NcclLogLevel::DEBUG,"waiting_to_notify_receiver  current_flow_id  %d src  %d dst  %d count  %d",request->flowTag.current_flow_id,src,dst,pending_receiver_callbacks);
  }
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
    auto logical_flow_key = std::make_tuple(
        tag, flowTag.current_flow_id, sender_node, receiver_node);
    if (flowTag.current_flow_id >= 0 &&
        !receiver_notified_logical_flows.insert(logical_flow_key).second) {
      NcclLog->writeLog(
          NcclLogLevel::WARNING,
          "duplicate receiver notification dropped: tag %d flow_id %d src %d dst %d size %llu",
          tag,
          flowTag.current_flow_id,
          sender_node,
          receiver_node,
          message_size);
      #ifdef NS3_MTP
      cs.ExitSection();
      #endif
      return;
    }
    auto exact_key = make_pair(tag, make_pair(sender_node, receiver_node));
    auto exact_expected = expeRecvHash.find(exact_key);
    if (exact_expected != expeRecvHash.end() &&
        !exact_expected->second.empty()) {
      task1 t2 =
          exact_expected->second.front();
    MockNcclLog* NcclLog = MockNcclLog::getInstance();
    NcclLog->writeLog(NcclLogLevel::DEBUG," %d notify recevier:  %d message size:  %llu t2.count:  %llu channle id:  %d",sender_node,receiver_node,message_size,t2.count,flowTag.channel_id);
      AstraSim::RecvPacketEventHadndlerData* ehd = (AstraSim::RecvPacketEventHadndlerData*) t2.fun_arg;
      if (message_size == t2.count) {
        NcclLog->writeLog(NcclLogLevel::DEBUG," message_size = t2.count expeRecvHash.erase  %d notify recevier:  %d message size:  %llu channel_id  %d",sender_node,receiver_node,message_size,tag);
        bool popped = pop_expected_receive(exact_key, t2);
        assert(popped);
        #ifdef NS3_MTP
        cs.ExitSection();
        #endif
        assert(ehd->flowTag.current_flow_id == -1 && ehd->flowTag.child_flow_id == -1);
        ehd->flowTag = flowTag;
        dispatch_receiver_callback(t2);
        goto receiver_end_1st_section;
      } else if (message_size > t2.count) {
        enqueue_receiver_pending_arrival(
            sender_node,
            receiver_node,
            tag,
            message_size - t2.count,
            flowTag);
        NcclLog->writeLog(NcclLogLevel::DEBUG,"message_size > t2.count expeRecvHash.erase %d notify recevier:  %d message size:  %llu channel_id  %d",sender_node,receiver_node,message_size,tag);
        bool popped = pop_expected_receive(exact_key, t2);
        assert(popped);
        #ifdef NS3_MTP
        cs.ExitSection();
        #endif
        assert(ehd->flowTag.current_flow_id == -1 && ehd->flowTag.child_flow_id == -1);
        ehd->flowTag = flowTag;
        dispatch_receiver_callback(t2);
        goto receiver_end_1st_section;
      } else {
        exact_expected->second.front().count -= message_size;
      }
    } else {
      enqueue_receiver_pending_arrival(
          sender_node, receiver_node, tag, message_size, flowTag);
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
        dispatch_sender_callback(t2);
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
      dispatch_sender_callback(t2);
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
  static const bool fct_output_enabled = [] {
    const char* value = std::getenv("AS_FCT_OUTPUT");
    return value == nullptr || value[0] != '0';
  }();
  if (fct_output_enabled) {
    fprintf(fout, "%08x %08x %u %u %lu %lu %lu %lu\n", q->sip.Get(), q->dip.Get(),
            q->sport, q->dport, q->m_size, q->startTime.GetTimeStep(),
            (Simulator::Now() - q->startTime).GetTimeStep(), standalone_fct);
    fflush(fout);
  }

  AstraSim::ncclFlowTag flowTag;
  uint64_t notify_size;
  {
    #ifdef NS3_MTP
    MtpInterface::explicitCriticalSection cs;
    #endif
    Ptr<Node> dstNode = n.Get(did);
    Ptr<RdmaDriver> rdma = dstNode->GetObject<RdmaDriver>();
    rdma->m_rdma->DeleteRxQp(q->sip.Get(), q->m_pg, q->sport);
    MockNcclLog* NcclLog = MockNcclLog::getInstance();
    NcclLog->writeLog(NcclLogLevel::DEBUG,"qp finish, src:  %d did:  %d port:  %d total bytes:  %llu at the tick:  %d",sid,did,q->sport,q->m_size,AstraSim::Sys::boostedTick());
    if (sender_src_port_map.find(make_pair(q->sport, make_pair(sid, did))) ==
        sender_src_port_map.end()) {
      NcclLog->writeLog(NcclLogLevel::ERROR,"could not find the tag, there must be something wrong");
      exit(-1);
    }
    flowTag = sender_src_port_map[make_pair(q->sport, make_pair(sid, did))];
    sender_src_port_map.erase(make_pair(q->sport, make_pair(sid, did)));
    received_chunksize[std::make_pair(flowTag.current_flow_id,std::make_pair(sid,did))]+=q->m_size;
    if(!is_receive_finished(sid,did,flowTag)) {
      #ifdef NS3_MTP
      cs.ExitSection();
      #endif
      return; 
    }
    notify_size = received_chunksize[std::make_pair(flowTag.current_flow_id,std::make_pair(sid,did))];
    received_chunksize.erase(std::make_pair(flowTag.current_flow_id,std::make_pair(sid,did)));    
    #ifdef NS3_MTP
    cs.ExitSection();
    #endif
  }
  if (flowTag.flow_size > 0 && notify_size > flowTag.flow_size) {
    MockNcclLog::getInstance()->writeLog(
        NcclLogLevel::WARNING,
        "receiver notification size clamped: flow_id %d src %d dst %d aggregated %llu logical %llu",
        flowTag.current_flow_id,
        sid,
        did,
        notify_size,
        flowTag.flow_size);
    notify_size = flowTag.flow_size;
  }
  notify_receiver_receive_data(sid, did, notify_size, flowTag);
}

void send_finish(FILE *fout, Ptr<RdmaQueuePair> q) {
  uint32_t sid = ip_to_node_id(q->sip), did = ip_to_node_id(q->dip);
  AstraSim::ncclFlowTag flowTag;
  MockNcclLog* NcclLog = MockNcclLog::getInstance();
  NcclLog->writeLog(NcclLogLevel::DEBUG,"[Packet sent from NIC] send finish, src:  %d did:  %d port:  %d srcip  %d dstip  %d total bytes:  %llu at the tick:  %d",sid,did,q->sport,q->sip,q->dip,q->m_size,AstraSim::Sys::boostedTick());
  uint64_t all_sent_chunksize;
  {
    #ifdef NS3_MTP
    MtpInterface::explicitCriticalSection cs;
    #endif
    flowTag = sender_src_port_map[make_pair(q->sport, make_pair(sid, did))];
    sent_chunksize[std::make_pair(flowTag.current_flow_id,std::make_pair(sid,did))]+=q->m_size;
    if(!is_sending_finished(sid,did,flowTag)) {
      #ifdef NS3_MTP
      cs.ExitSection();
      #endif
      return;
    }
    all_sent_chunksize = sent_chunksize[std::make_pair(flowTag.current_flow_id,std::make_pair(sid,did))];
    sent_chunksize.erase(std::make_pair(flowTag.current_flow_id,std::make_pair(sid,did)));
    #ifdef NS3_MTP
    cs.ExitSection();
    #endif
  }
  if (flowTag.flow_size > 0 && all_sent_chunksize > flowTag.flow_size) {
    MockNcclLog::getInstance()->writeLog(
        NcclLogLevel::WARNING,
        "sender notification size clamped: flow_id %d src %d dst %d aggregated %llu logical %llu",
        flowTag.current_flow_id,
        sid,
        did,
        all_sent_chunksize,
        flowTag.flow_size);
    all_sent_chunksize = flowTag.flow_size;
  }
  notify_sender_sending_finished(sid, did, all_sent_chunksize, flowTag);
}

int main1(string network_topo,string network_conf) {
  clock_t begint, endt;
  begint = clock();

  if (!ReadConf(network_topo,network_conf))
    return -1;
  SetConfig();
  SetupNetwork(qp_finish,send_finish);

std::cout << "Running Simulation.\n";
  fflush(stdout);
  NS_LOG_INFO("Run Simulation.");

  endt = clock();
  return 0;
}
#endif
