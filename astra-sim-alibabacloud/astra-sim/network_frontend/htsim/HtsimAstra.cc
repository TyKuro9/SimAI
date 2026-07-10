/*
 * Copyright (c) 2024, Alibaba Group;
 * Licensed under the Apache License, Version 2.0.
 */

#include "HtsimNetwork.h"

#include "astra-sim/system/MockNcclLog.h"
#include "astra-sim/system/Sys.hh"

#include <getopt.h>
#include <sys/stat.h>
#include <sys/types.h>

#include <cstdlib>
#include <algorithm>
#include <fstream>
#include <iostream>
#include <map>
#include <string>
#include <vector>

#define DEFAULT_RESULT_PATH "./experiments/htsim_results/csv/"

using namespace std;

namespace {

struct user_param {
  int thread;
  string workload;
  string network_topo;
  string network_conf;
  string result_dir;
  string route_strategy;

  user_param()
      : thread(1),
        workload(""),
        network_topo(""),
        network_conf(""),
        result_dir(DEFAULT_RESULT_PATH),
        route_strategy("single") {}
};

string normalize_result_dir(string path) {
  if (path.empty()) {
    return DEFAULT_RESULT_PATH;
  }
  if (path.back() != '/') {
    path.push_back('/');
  }
  return path;
}

bool ensure_result_dir(const string& path) {
  string command = "mkdir -p \"" + path + "\"";
  return system(command.c_str()) == 0;
}

bool env_enabled(const char* name) {
  const char* value = getenv(name);
  return value != nullptr && value[0] != '\0' && value[0] != '0';
}

bool env_enabled_or_default(const char* name, bool default_value) {
  const char* value = getenv(name);
  if (value == nullptr || value[0] == '\0') {
    return default_value;
  }
  string token(value);
  transform(token.begin(), token.end(), token.begin(), ::tolower);
  return token != "0" && token != "false" && token != "no" &&
      token != "off";
}

size_t env_size_or_default(const char* name, size_t default_value) {
  const char* value = getenv(name);
  if (value == nullptr || value[0] == '\0') {
    return default_value;
  }
  return max<size_t>(1, strtoull(value, nullptr, 10));
}

void maybe_read_network_conf(user_param* param) {
  const char* env_strategy = getenv("HTSIM_ROUTE_STRATEGY");
  if (env_strategy != nullptr && env_strategy[0] != '\0') {
    param->route_strategy = env_strategy;
  }

  if (param->network_conf.empty()) {
    return;
  }
  ifstream conf(param->network_conf.c_str());
  if (!conf.is_open()) {
    return;
  }

  string line;
  while (getline(conf, line)) {
    size_t pos = line.find("route_strategy");
    if (pos == string::npos) {
      pos = line.find("network_backend");
    }
    if (pos == string::npos) {
      continue;
    }
    size_t sep = line.find_first_of("=:", pos);
    if (sep == string::npos) {
      continue;
    }
    string value = line.substr(sep + 1);
    size_t start = value.find_first_not_of(" \t\"");
    size_t end = value.find_last_not_of(" \t\";");
    if (start == string::npos || end == string::npos || end < start) {
      continue;
    }
    value = value.substr(start, end - start + 1);
    if (value == "htsim") {
      continue;
    }
    if (value == "single" || value == "ecmp" ||
        value == "ns3_ecmp" ||
        value == "spray_rr" || value == "spray_incremental" ||
        value == "spray_oblivious" || value == "spray_plb" ||
        value == "plb" || value == "spray_reps" ||
        value == "reps") {
      param->route_strategy = value;
    }
  }
}

int parse_user_param(int argc, char* argv[], user_param* param) {
  int opt;
  while ((opt = getopt(argc, argv, "ht:w:g:s:n:c:o:r:")) != -1) {
    switch (opt) {
      case 'h':
        cout << "-t    number of threads, default 1" << endl;
        cout << "-w    workload file" << endl;
        cout << "-n    network topology file" << endl;
        cout << "-c    network config file" << endl;
        cout << "-o    result directory for EndToEnd.csv" << endl;
        cout << "-r    route_strategy: single|ecmp|ns3_ecmp|spray_rr|spray_incremental|spray_oblivious|spray_plb|spray_reps" << endl;
        return 1;
      case 't':
        param->thread = stoi(optarg);
        break;
      case 'w':
        param->workload = optarg;
        break;
      case 'n':
        param->network_topo = optarg;
        break;
      case 'c':
        param->network_conf = optarg;
        break;
      case 'o':
        param->result_dir = normalize_result_dir(optarg);
        break;
      case 'r':
        param->route_strategy = optarg;
        break;
      default:
        cerr << "-h    help message" << endl;
        return 1;
    }
  }
  maybe_read_network_conf(param);
  return 0;
}

}  // namespace

int main(int argc, char* argv[]) {
  user_param param;
  MockNcclLog::set_log_name("SimAI_htsim.log");
  MockNcclLog::getInstance()->writeLog(NcclLogLevel::INFO, "init htsim");

  if (parse_user_param(argc, argv, &param)) {
    return 0;
  }
  param.result_dir = normalize_result_dir(param.result_dir);
  if (!ensure_result_dir(param.result_dir)) {
    cerr << "failed to create result directory: " << param.result_dir << endl;
    return 1;
  }
  try {
    htsim_set_result_dir(param.result_dir);
    htsim_set_route_strategy(param.route_strategy);
  } catch (const invalid_argument& err) {
    cerr << err.what() << endl;
    return 1;
  } catch (const runtime_error& err) {
    cerr << err.what() << endl;
    return 1;
  }
  if (!htsim_load_topology_summary(param.network_topo)) {
    return 1;
  }

  int gpu_num = static_cast<int>(node_num - nvswitch_num - switch_num);
  int nodes_num = gpu_num;
  if (nodes_num <= 0 || gpu_num <= 0) {
    cerr << "invalid htsim topology summary: nodes=" << node_num
         << " switches=" << switch_num << " nvswitches=" << nvswitch_num
         << endl;
    return 1;
  }

  map<int, int> node2nvswitch;
  for (int i = 0; i < gpu_num; ++i) {
    node2nvswitch[i] = gpu_num + i / gpus_per_server;
  }
  for (int i = gpu_num; i < gpu_num + static_cast<int>(nvswitch_num); ++i) {
    node2nvswitch[i] = i;
  }

  vector<HtsimNetwork*> networks(nodes_num, nullptr);
  vector<AstraSim::Sys*> systems(nodes_num, nullptr);

  for (int j = 0; j < nodes_num; j++) {
    networks[j] = new HtsimNetwork(j, 0);
    systems[j] = new AstraSim::Sys(
        networks[j],
        nullptr,
        j,
        0,
        1,
        {gpu_num},
        {1},
        "",
        param.workload,
        1,
        1,
        1,
        1,
        0,
        param.result_dir,
        "htsim",
        true,
        false,
        gpu_type,
        {gpu_num},
        NVswitchs,
        gpus_per_server);
    systems[j]->nvswitch_id = node2nvswitch[j];
    systems[j]->num_gpus = gpu_num;
  }

  for (int i = 0; i < nodes_num; i++) {
    systems[i]->workload->fire();
  }

  cout << "SimAI begin run htsim route_strategy=" << htsim_route_strategy()
       << " packet_level=" << (htsim_packet_level_enabled() ? 1 : 0)
       << endl;
  auto dump_astra_watchdog = [&systems]() {
    if (!env_enabled("HTSIM_WATCHDOG_DUMP_ASTRA")) {
      return;
    }
    const size_t rank_limit =
        env_size_or_default("HTSIM_WATCHDOG_ASTRA_RANKS", 4);
    const size_t stream_limit =
        env_size_or_default("HTSIM_WATCHDOG_ASTRA_STREAMS", 4);
    size_t dumped = 0;
    for (auto* system : systems) {
      if (system == nullptr || system->unfinished_stream_count() == 0) {
        continue;
      }
      system->dump_unfinished_streams(stream_limit);
      dumped++;
      if (dumped >= rank_limit) {
        break;
      }
    }
    if (dumped == 0) {
      cout << "[htsim watchdog] ASTRA has no unfinished streams" << endl;
    }
  };

  htsim_run(dump_astra_watchdog);

  auto rank0_reported = [&systems]() {
    return !systems.empty() && systems[0] != nullptr &&
        systems[0]->workload_reported;
  };
  auto dump_unfinished_astra = [&systems](size_t rank_limit, size_t stream_limit) {
    size_t dumped = 0;
    for (auto* system : systems) {
      if (system == nullptr) {
        continue;
      }
      size_t unfinished = system->unfinished_stream_count();
      if (unfinished == 0) {
        continue;
      }
      cerr << "[htsim] unfinished ASTRA rank " << system->id
           << " pending_items " << unfinished << endl;
      system->dump_unfinished_streams(stream_limit);
      dumped++;
      if (dumped >= rank_limit) {
        cerr << "[htsim] truncated unfinished ASTRA rank dump" << endl;
        break;
      }
    }
  };

  int drained_streams = 0;
  int scheduled_streams = 0;
  int started_streams = 0;
  int flushed_events = 0;
  bool final_drain_failed = false;
  const bool final_drain_recovery =
      env_enabled_or_default("HTSIM_FINAL_DRAIN_RECOVERY", true);
  const size_t max_final_drain_recovery_rounds =
      env_size_or_default("HTSIM_FINAL_DRAIN_RECOVERY_ROUNDS", 32768);
  size_t final_drain_recovery_round = 0;
  size_t previous_recovered_flows = 0;
  while (!rank0_reported()) {
    drained_streams = 0;
    scheduled_streams = 0;
    started_streams = 0;
    flushed_events = 0;
    for (auto* system : systems) {
      if (system != nullptr) {
        drained_streams += system->drain_finished_streams();
      }
    }
    if (drained_streams > 0) {
      cout << "[htsim] Drained " << drained_streams
           << " finished streams after event queue became empty" << endl;
      htsim_run(dump_astra_watchdog);
    }
    for (auto* system : systems) {
      if (system != nullptr) {
        scheduled_streams += system->schedule_ready_list_streams();
      }
    }
    if (scheduled_streams > 0) {
      cout << "[htsim] Scheduled " << scheduled_streams
           << " ready-list streams after event queue became empty" << endl;
      htsim_run(dump_astra_watchdog);
    }
    for (auto* system : systems) {
      if (system != nullptr) {
        started_streams += system->start_ready_streams();
      }
    }
    if (started_streams > 0) {
      cout << "[htsim] Started " << started_streams
           << " ready streams after event queue became empty" << endl;
      htsim_run(dump_astra_watchdog);
    }
    for (auto* system : systems) {
      if (system != nullptr) {
        flushed_events += system->flush_pending_events();
      }
    }
    if (flushed_events > 0) {
      cout << "[htsim] Flushed " << flushed_events
           << " pending ASTRA event batches after event queue became empty"
           << endl;
      htsim_run(dump_astra_watchdog);
    }
    if (rank0_reported()) {
      break;
    }
    if (drained_streams == 0 && scheduled_streams == 0 &&
        started_streams == 0 && flushed_events == 0) {
      if (final_drain_recovery &&
          final_drain_recovery_round < max_final_drain_recovery_rounds) {
        size_t recovered_flows = htsim_recover_stalled_flows();
        if (recovered_flows > 0) {
          final_drain_recovery_round++;
          if (final_drain_recovery_round == 1 ||
              final_drain_recovery_round % 256 == 0 ||
              recovered_flows != previous_recovered_flows) {
            cout << "[htsim] Final drain recovery round "
                 << final_drain_recovery_round << " recovered_flows="
                 << recovered_flows << endl;
          }
          previous_recovered_flows = recovered_flows;
          htsim_run(dump_astra_watchdog);
          continue;
        }
      }
      cerr << "[htsim] Final drain stalled before workload report" << endl;
      htsim_dump_pending_state(32);
      dump_unfinished_astra(32, 8);
      final_drain_failed = true;
      break;
    }
  }

  if (final_drain_recovery_round > 0) {
    cout << "[htsim] Final drain recovery completed after "
         << final_drain_recovery_round << " rounds" << endl;
  }

  htsim_destroy();
  cout << "SimAI-htsim finished." << endl;
  return final_drain_failed ? 2 : 0;
}
