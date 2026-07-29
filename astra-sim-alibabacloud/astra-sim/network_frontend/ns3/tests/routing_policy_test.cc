#include "../routing_policy.h"

#include <cassert>
#include <cstdint>
#include <vector>

int main() {
  using AstraSim::Ns3RoutingPolicy;

  assert(AstraSim::ParseNs3RoutingPolicy(nullptr) == Ns3RoutingPolicy::Ecmp);
  assert(AstraSim::ParseNs3RoutingPolicy("spray") == Ns3RoutingPolicy::Spray);
  assert(
      AstraSim::ParseNs3RoutingPolicy("spray_dynamic") ==
      Ns3RoutingPolicy::SprayDynamic);
  assert(
      AstraSim::ParseNs3RoutingPolicy("QP_DYNAMIC") ==
      Ns3RoutingPolicy::SprayDynamic);
  assert(AstraSim::IsNs3SprayPolicy(Ns3RoutingPolicy::Spray));
  assert(AstraSim::IsNs3SprayPolicy(Ns3RoutingPolicy::SprayDynamic));
  assert(
      AstraSim::ParseNs3RoutingPolicy("spray_path") ==
      Ns3RoutingPolicy::SprayPathAware);
  assert(
      AstraSim::ParseNs3RoutingPolicy("qp_path") ==
      Ns3RoutingPolicy::SprayPathAware);
  assert(AstraSim::IsNs3SprayPolicy(Ns3RoutingPolicy::SprayPathAware));
  assert(
      AstraSim::ParseNs3RoutingPolicy("spray_flowlet") ==
      Ns3RoutingPolicy::SprayFlowlet);
  assert(
      AstraSim::ParseNs3RoutingPolicy("DYNAMIC_FLOWLET") ==
      Ns3RoutingPolicy::SprayFlowlet);
  assert(AstraSim::IsNs3SprayPolicy(Ns3RoutingPolicy::SprayFlowlet));
  assert(
      AstraSim::ParseNs3RoutingPolicy("spray_dual_table") ==
      Ns3RoutingPolicy::SprayDualTable);
  assert(
      AstraSim::ParseNs3RoutingPolicy("ZCUBE_DUAL_TABLE") ==
      Ns3RoutingPolicy::SprayDualTable);
  assert(AstraSim::IsNs3SprayPolicy(Ns3RoutingPolicy::SprayDualTable));
  assert(
      AstraSim::ParseNs3RoutingPolicy("spray_adaptive") ==
      Ns3RoutingPolicy::SprayAdaptive);
  assert(
      AstraSim::ParseNs3RoutingPolicy("ETA_SPRAY") ==
      Ns3RoutingPolicy::SprayAdaptive);
  assert(AstraSim::IsNs3SprayPolicy(Ns3RoutingPolicy::SprayAdaptive));
  assert(
      AstraSim::ParseNs3RoutingPolicy("spray_dynamic_chunk") ==
      Ns3RoutingPolicy::SprayDynamicChunk);
  assert(
      AstraSim::ParseNs3RoutingPolicy("CHUNK_SPRAY") ==
      Ns3RoutingPolicy::SprayDynamicChunk);
  assert(AstraSim::IsNs3SprayPolicy(Ns3RoutingPolicy::SprayDynamicChunk));
  assert(AstraSim::IsNs3DynamicChunkPolicy(
      Ns3RoutingPolicy::SprayDynamicChunk));
  assert(
      AstraSim::ParseNs3RoutingPolicy("spray_disjoint_chunk") ==
      Ns3RoutingPolicy::SprayDisjointChunk);
  assert(
      AstraSim::ParseNs3RoutingPolicy("ZCUBE_DISJOINT_CHUNK") ==
      Ns3RoutingPolicy::SprayDisjointChunk);
  assert(AstraSim::IsNs3SprayPolicy(Ns3RoutingPolicy::SprayDisjointChunk));
  assert(AstraSim::IsNs3DynamicChunkPolicy(
      Ns3RoutingPolicy::SprayDisjointChunk));
  assert(AstraSim::IsNs3DisjointChunkPolicy(
      Ns3RoutingPolicy::SprayDisjointChunk));
  assert(
      AstraSim::ParseNs3RoutingPolicy("spray_packet_dlb") ==
      Ns3RoutingPolicy::SprayPacketDlb);
  assert(
      AstraSim::ParseNs3RoutingPolicy("PACKET_DLB") ==
      Ns3RoutingPolicy::SprayPacketDlb);
  assert(AstraSim::IsNs3PacketDlbPolicy(Ns3RoutingPolicy::SprayPacketDlb));
  assert(!AstraSim::IsNs3SprayPolicy(Ns3RoutingPolicy::SprayPacketDlb));
  assert(
      AstraSim::ParseNs3RoutingPolicy("spray_switch_dlb") ==
      Ns3RoutingPolicy::SpraySwitchDlb);
  assert(
      AstraSim::ParseNs3RoutingPolicy("hop_by_hop_dlb") ==
      Ns3RoutingPolicy::SpraySwitchDlb);
  assert(AstraSim::IsNs3PacketDlbPolicy(Ns3RoutingPolicy::SpraySwitchDlb));
  assert(AstraSim::IsNs3SwitchDlbPolicy(Ns3RoutingPolicy::SpraySwitchDlb));
  assert(!AstraSim::IsNs3SwitchDlbPolicy(Ns3RoutingPolicy::SprayPacketDlb));
  assert(!AstraSim::IsNs3SprayPolicy(Ns3RoutingPolicy::SpraySwitchDlb));
  assert(
      AstraSim::ParseNs3RoutingPolicy("spray_multi_qp_dlb") ==
      Ns3RoutingPolicy::SprayMultiQpDlb);
  assert(
      AstraSim::ParseNs3RoutingPolicy("REALISTIC_PACKET_DLB") ==
      Ns3RoutingPolicy::SprayMultiQpDlb);
  assert(
      AstraSim::IsNs3MultiQpDlbPolicy(Ns3RoutingPolicy::SprayMultiQpDlb));
  assert(!AstraSim::IsNs3SprayPolicy(Ns3RoutingPolicy::SprayMultiQpDlb));
  assert(!AstraSim::IsNs3SprayPolicy(Ns3RoutingPolicy::Ecmp));

  assert(AstraSim::ParseNs3SprayWidth(nullptr) == 4);
  assert(AstraSim::ParseNs3SprayWidth("16") == 16);
  assert(AstraSim::EffectiveNs3SprayWidth(2, 4) == 2);
  assert(
      AstraSim::SplitNs3SprayBytes(10, 4) ==
      (std::vector<uint64_t>{3, 3, 2, 2}));
  assert(AstraSim::ParseNs3DynamicChunkCount(nullptr) == 8);
  assert(AstraSim::ParseNs3DynamicChunkCount("32") == 32);
  assert(AstraSim::ParseNs3MultiQpCount(nullptr) == 4);
  assert(AstraSim::ParseNs3MultiQpCount("16") == 16);

  return 0;
}
