#ifndef ASTRA_SIM_NS3_ROUTING_POLICY_H
#define ASTRA_SIM_NS3_ROUTING_POLICY_H

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace AstraSim {

enum class Ns3RoutingPolicy {
  Ecmp,
  Spray,
  SprayDynamic,
  SprayPathAware,
  SprayFlowlet,
  SprayDualTable,
  SprayAdaptive,
  SprayDynamicChunk,
  SprayPacketDlb,
};

inline std::string NormalizeNs3RoutingValue(const char* value) {
  std::string normalized = value ? value : "";
  std::transform(
      normalized.begin(), normalized.end(), normalized.begin(),
      [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
  return normalized;
}

inline Ns3RoutingPolicy ParseNs3RoutingPolicy(const char* value) {
  const std::string normalized = NormalizeNs3RoutingValue(value);
  if (normalized.empty() || normalized == "ecmp" ||
      normalized == "flow_ecmp" || normalized == "legacy") {
    return Ns3RoutingPolicy::Ecmp;
  }
  if (normalized == "spray" || normalized == "qp_spray" ||
      normalized == "flow_spray") {
    return Ns3RoutingPolicy::Spray;
  }
  if (normalized == "spray_dynamic" || normalized == "dynamic_spray" ||
      normalized == "qp_dynamic" || normalized == "dynamic_qp") {
    return Ns3RoutingPolicy::SprayDynamic;
  }
  if (normalized == "spray_path" || normalized == "spray_path_aware" ||
      normalized == "path_aware" || normalized == "qp_path") {
    return Ns3RoutingPolicy::SprayPathAware;
  }
  if (normalized == "spray_flowlet" || normalized == "flowlet_spray" ||
      normalized == "dynamic_flowlet" || normalized == "flowlet_dynamic") {
    return Ns3RoutingPolicy::SprayFlowlet;
  }
  if (normalized == "spray_dual_table" ||
      normalized == "dual_table_spray" ||
      normalized == "dual_table_flowlet" ||
      normalized == "zcube_dual_table") {
    return Ns3RoutingPolicy::SprayDualTable;
  }
  if (normalized == "spray_adaptive" ||
      normalized == "adaptive_spray" ||
      normalized == "zcube_adaptive" || normalized == "eta_spray") {
    return Ns3RoutingPolicy::SprayAdaptive;
  }
  if (normalized == "spray_dynamic_chunk" ||
      normalized == "dynamic_chunk_spray" ||
      normalized == "chunk_spray" || normalized == "chunk_adaptive") {
    return Ns3RoutingPolicy::SprayDynamicChunk;
  }
  if (normalized == "spray_packet_dlb" ||
      normalized == "packet_dlb" ||
      normalized == "packet_spray" || normalized == "dlb_spray") {
    return Ns3RoutingPolicy::SprayPacketDlb;
  }
  throw std::invalid_argument(
      "expected ecmp, spray/qp_spray, spray_dynamic/qp_dynamic, or "
      "spray_path/qp_path, spray_flowlet/dynamic_flowlet, or "
      "spray_dual_table/dual_table_flowlet, spray_adaptive/eta_spray, or "
      "spray_dynamic_chunk/chunk_spray, or spray_packet_dlb/packet_dlb");
}

inline bool IsNs3SprayPolicy(Ns3RoutingPolicy policy) {
  return policy == Ns3RoutingPolicy::Spray ||
         policy == Ns3RoutingPolicy::SprayDynamic ||
         policy == Ns3RoutingPolicy::SprayPathAware ||
         policy == Ns3RoutingPolicy::SprayFlowlet ||
         policy == Ns3RoutingPolicy::SprayDualTable ||
         policy == Ns3RoutingPolicy::SprayAdaptive ||
         policy == Ns3RoutingPolicy::SprayDynamicChunk;
}

inline bool IsNs3DynamicChunkPolicy(Ns3RoutingPolicy policy) {
  return policy == Ns3RoutingPolicy::SprayDynamicChunk;
}

inline bool IsNs3PacketDlbPolicy(Ns3RoutingPolicy policy) {
  return policy == Ns3RoutingPolicy::SprayPacketDlb;
}

inline uint32_t ParseNs3SprayWidth(const char* value) {
  const std::string normalized = NormalizeNs3RoutingValue(value);
  if (normalized.empty()) {
    return 4;
  }

  size_t consumed = 0;
  unsigned long parsed = 0;
  try {
    parsed = std::stoul(normalized, &consumed, 10);
  } catch (const std::exception&) {
    throw std::invalid_argument("spray width must be an integer from 1 to 16");
  }
  if (consumed != normalized.size() || parsed < 1 || parsed > 16) {
    throw std::invalid_argument("spray width must be an integer from 1 to 16");
  }
  return static_cast<uint32_t>(parsed);
}

inline uint32_t EffectiveNs3SprayWidth(
    uint64_t total_bytes,
    uint32_t configured_width) {
  if (total_bytes == 0) {
    return 1;
  }
  return static_cast<uint32_t>(
      std::min<uint64_t>(total_bytes, std::max<uint32_t>(1, configured_width)));
}

inline std::vector<uint64_t> SplitNs3SprayBytes(
    uint64_t total_bytes,
    uint32_t stripe_count) {
  stripe_count = EffectiveNs3SprayWidth(total_bytes, stripe_count);
  std::vector<uint64_t> stripes(stripe_count, total_bytes / stripe_count);
  const uint64_t remainder = total_bytes % stripe_count;
  for (uint32_t index = 0; index < remainder; ++index) {
    ++stripes[index];
  }
  return stripes;
}

inline uint32_t ParseNs3DynamicChunkCount(const char* value) {
  const std::string normalized = NormalizeNs3RoutingValue(value);
  if (normalized.empty()) {
    return 8;
  }

  size_t consumed = 0;
  unsigned long parsed = 0;
  try {
    parsed = std::stoul(normalized, &consumed, 10);
  } catch (const std::exception&) {
    throw std::invalid_argument(
        "dynamic chunk count must be an integer from 1 to 64");
  }
  if (consumed != normalized.size() || parsed < 1 || parsed > 64) {
    throw std::invalid_argument(
        "dynamic chunk count must be an integer from 1 to 64");
  }
  return static_cast<uint32_t>(parsed);
}

}  // namespace AstraSim

#endif  // ASTRA_SIM_NS3_ROUTING_POLICY_H
