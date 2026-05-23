#!/usr/bin/env python3
"""
自定义拓扑生成器模板
用于生成 SimAI 所需的网络拓扑文件
"""

class TopoGenerator:
    def __init__(self, filename):
        self.filename = filename
        self.nodes = []
        self.switches = []
        self.links = []
        
        # 配置参数
        self.gpu_count = 0
        self.gpus_per_server = 0
        self.nv_switch_per_server = 0
        self.gpu_type = "A100"

        # 单台 ASW / PSW 的端口总数与下联比例（可先 SetPortRatios，再在连线函数中用默认 None 读取）
        self.asw_port = None
        self.asw_downlink_alpha = None
        self.psw_port = None
        self.psw_downlink_beta = None
        
        # 节点ID计数器
        self.next_gpu_id = 0
        self.next_nv_switch_id = 0
        self.next_asw_id = 0
        self.next_psw_id = 0
        self.next_dsw_id = 0
    
    def SetConfig(self, gpu_count, gpus_per_server, nv_switch_per_server=1, gpu_type="A100"):
        """设置基本配置"""
        self.gpu_count = gpu_count
        self.gpus_per_server = gpus_per_server
        self.nv_switch_per_server = nv_switch_per_server
        self.gpu_type = gpu_type
        
        # 初始化节点ID
        self.next_gpu_id = 0
        self.next_nv_switch_id = gpu_count
        self.next_asw_id = gpu_count + (gpu_count // gpus_per_server) * nv_switch_per_server

    def SetPortRatios(self, asw_port, alpha, psw_port, beta):
        """
        写入类内：ASW 端口总数、ASW 下联比例 alpha、PSW 端口总数、PSW 下联比例 beta。

        供 FullConnectGPUsToASW、FullConnectASWToPSW 使用。
        端口与比例的完整合法性校验建议在 GenerateMetaTopo 等入口完成；FullConnect* 仅做连线及容量下限检查。
        """
        self.asw_port = asw_port
        self.asw_downlink_alpha = alpha
        self.psw_port = psw_port
        self.psw_downlink_beta = beta
    
    def AddNVSwitches(self):
        """添加 NVLink 交换机"""
        servers = self.gpu_count // self.gpus_per_server
        for i in range(servers * self.nv_switch_per_server):
            self.switches.append(self.next_nv_switch_id + i)
        self.next_psw_id = self.next_asw_id
        return self.next_nv_switch_id
    
    def AddASWSwitches(self, count):
        """添加 ASW 交换机"""
        asw_ids = []
        for i in range(count):
            asw_id = self.next_asw_id + i
            self.switches.append(asw_id)
            asw_ids.append(asw_id)
        self.next_psw_id = self.next_asw_id + count
        return asw_ids
    
    def AddPSWSwitches(self, count):
        """添加 PSW 交换机"""
        psw_ids = []
        for i in range(count):
            psw_id = self.next_psw_id + i
            self.switches.append(psw_id)
            psw_ids.append(psw_id)
        self.next_dsw_id = self.next_psw_id + count
        return psw_ids
    
    def AddDSWSwitches(self, count):
        """添加 DSW 交换机（用于多 Pod）"""
        dsw_ids = []
        for i in range(count):
            dsw_id = self.next_dsw_id + i
            self.switches.append(dsw_id)
            dsw_ids.append(dsw_id)
        return dsw_ids
    
    def AddLink(self, src, dst, bandwidth, latency="0.0005ms", error_rate="0"):
        """添加链接"""
        self.links.append(f"{src} {dst} {bandwidth} {latency} {error_rate}")
    
    def ConnectGPUsToNVSwitch(self, nvlink_bw="2400Gbps", nv_latency="0.000025ms"):
        """连接 GPU 到 NVLink 交换机"""
        servers = self.gpu_count // self.gpus_per_server
        for server_id in range(servers):
            nv_switch_id = self.next_nv_switch_id + server_id * self.nv_switch_per_server
            for gpu_offset in range(self.gpus_per_server):
                gpu_id = server_id * self.gpus_per_server + gpu_offset
                for nv_offset in range(self.nv_switch_per_server):
                    self.AddLink(gpu_id, nv_switch_id + nv_offset, nvlink_bw, nv_latency, "0")
    
    def ConnectGPUsToASW(self, asw_ids, nic_bw="400Gbps", nic_latency="0.0005ms"):
        """连接 GPU 到 ASW 交换机"""
        servers = self.gpu_count // self.gpus_per_server
        if len(asw_ids) != servers:
            print(f"Warning: ASW count ({len(asw_ids)}) != server count ({servers})")
        
        for server_id in range(min(servers, len(asw_ids))):
            asw_id = asw_ids[server_id]
            for gpu_offset in range(self.gpus_per_server):
                gpu_id = server_id * self.gpus_per_server + gpu_offset
                self.AddLink(gpu_id, asw_id, nic_bw, nic_latency, "0")

    def FullConnectGPUsToASW(
        self,
        asw_ids,
        nic_bw="100Gbps",
        nic_latency="0.0005ms",
    ):
        """
        按「每台 ASW 下挂固定数量 GPU」连接 NIC：同一 server 内所有 GPU 连到同一台 ASW。

        使用类内 self.asw_port、self.asw_downlink_alpha（须先 SetPortRatios）。
        port 与比例的合法性由调用方（例如 GenerateMetaTopo）统一校验；本函数只做连线。
        """
        port = self.asw_port
        alpha = self.asw_downlink_alpha
        if port is None or alpha is None:
            raise ValueError(
                "类内 asw_port / asw_downlink_alpha 未设置：请先调用 "
                "SetPortRatios(asw_port, alpha, psw_port, beta)"
            )
        slots_per_asw = int(round(port * alpha))
        servers_per_asw = slots_per_asw // self.gpus_per_server
        num_servers = self.gpu_count // self.gpus_per_server

        for server_id in range(num_servers):
            asw_index = server_id // servers_per_asw
            asw_id = asw_ids[asw_index]
            for gpu_offset in range(self.gpus_per_server):
                gpu_id = server_id * self.gpus_per_server + gpu_offset
                self.AddLink(gpu_id, asw_id, nic_bw, nic_latency, "0")

    def FullConnectASWToPSW(
        self,
        asw_ids,
        psw_ids,
        uplink_bw="400Gbps",
        latency="0.0005ms",
    ):
        """
        ASW 与 PSW 之间全连接（笛卡尔积）。

        使用类内 SetPortRatios 参数。端口与比例约束由调用方（例如 GenerateMetaTopo）校验；
        此处仅做全连接所必需的容量下限检查，避免明显越界。
        """
        ap = self.asw_port
        aa = self.asw_downlink_alpha
        pp = self.psw_port
        pb = self.psw_downlink_beta
        if ap is None or aa is None or pp is None or pb is None:
            raise ValueError(
                "请先调用 SetPortRatios(asw_port, alpha, psw_port, beta) 设置四类端口参数"
            )

        upl_cap = ap * (1.0 - aa)
        if upl_cap + 1e-9 < len(psw_ids):
            raise ValueError(
                f"ASW 上联端口数 asw_port*(1-alpha)={upl_cap} 不足以连接全部 PSW（需要 >= {len(psw_ids)}）"
            )

        dnl_cap = pp * pb
        if dnl_cap + 1e-9 < len(asw_ids):
            raise ValueError(
                f"PSW 下联端口数 psw_port*beta={dnl_cap} 不足以连接全部 ASW（需要 >= {len(asw_ids)}）"
            )

        for asw_id in asw_ids:
            for psw_id in psw_ids:
                self.AddLink(asw_id, psw_id, uplink_bw, latency, "0")

    def ConnectASWToPSW(self, asw_ids, psw_ids, uplink_bw="400Gbps", latency="0.0005ms"):
        """连接 ASW 到 PSW（全连接）"""
        for asw_id in asw_ids:
            for psw_id in psw_ids:
                self.AddLink(asw_id, psw_id, uplink_bw, latency, "0")
    
    def ConnectPSWToDSW(self, psw_ids, dsw_ids, uplink_bw="800Gbps", latency="0.001ms"):
        """连接 PSW 到 DSW（用于多 Pod）"""
        for psw_id in psw_ids:
            for dsw_id in dsw_ids:
                self.AddLink(psw_id, dsw_id, uplink_bw, latency, "0")
    
    def Generate(self):
        """生成拓扑文件"""
        total_nodes = self.gpu_count + len(self.switches)
        nv_switch_count = (self.gpu_count // self.gpus_per_server) * self.nv_switch_per_server
        other_switch_count = len(self.switches) - nv_switch_count
        total_links = len(self.links)
        
        with open(self.filename, 'w') as f:
            # 第一行：元数据
            f.write(f"{total_nodes} {self.gpus_per_server} {nv_switch_count} {other_switch_count} {total_links} {self.gpu_type}\n")
            
            # 第二行：交换机 ID
            switch_line = " ".join(map(str, self.switches))
            f.write(f"{switch_line}\n")
            
            # 后续行：链接信息
            for link in self.links:
                f.write(f"{link}\n")
        
        print(f"拓扑文件已生成: {self.filename}")
        print(f"  总节点数: {total_nodes}")
        print(f"  GPU数: {self.gpu_count}")
        print(f"  NVLink交换机数: {nv_switch_count}")
        print(f"  其他交换机数: {other_switch_count}")
        print(f"  总链接数: {total_links}")


# ==================================
# 以下是您请求的四种拓扑生成函数
# ==================================

def GenerateMetaTopo(
    gpu_count,
    gpus_per_server=8,
    nv_switch_per_server=1,
    gpu_type="A100",
    asw_port=64,
    psw_port=256,
    alpha=0.5,
    beta=1,
    nvlink_bw="3600Gbps",
    nic_bw="400Gbps",
    asw_to_psw_bw="400Gbps",
    nv_latency="0.000025ms",
    latency="0.0005ms",
    error_rate="0",
):
    """
    生成 Meta (Facebook) 风格拓扑：GPU–ASW、ASW–PSW 由类内端口与比例约束，并用 FullConnect* 连线。

    在函数内完成 port / alpha / beta 与台数的一致性校验；FullConnect* 不再重复校验，仅做连线与下限检查。

    推导与约束
    ----------
    - 每台 ASW 下联 GPU 数 slots = asw_port * alpha（须为正整数且为 gpus_per_server 的倍数）。
    - ASW 台数由 GPU 满载划分：asw_count = gpu_count // slots。
    - PSW 台数 psw_count = asw_port * (1 - alpha)（须为正整数，用于创建 spine 节点数）。
    - ASW 上联容量：asw_port * (1 - alpha) >= psw_count（全连接时每台 ASW 需连到每台 PSW）。
    - PSW 下联容量：psw_port * beta >= asw_count（下联端口可富余，不必等于 ASW 台数）。
    """
    print(f"开始生成 Meta (Facebook) 拓扑，GPU数量: {gpu_count}...")

    slots_f = asw_port * alpha
    if abs(slots_f - round(slots_f)) > 1e-9:
        raise ValueError(
            f"asw_port*alpha 须为整数，当前为 {slots_f}（asw_port={asw_port}, alpha={alpha}）"
        )
    slots_per_asw = int(round(slots_f))
    if slots_per_asw < 1 or slots_per_asw % gpus_per_server != 0:
        raise ValueError(
            f"asw_port*alpha（={slots_per_asw}）须为 >=1 的整数且为 gpus_per_server（={gpus_per_server}）的倍数"
        )
    if gpu_count % slots_per_asw != 0:
        raise ValueError(
            f"gpu_count（={gpu_count}）须为 slots（={slots_per_asw}）的整数倍"
        )

    asw_count = gpu_count // slots_per_asw

    psw_f = asw_port * (1.0 - alpha)
    if abs(psw_f - round(psw_f)) > 1e-9:
        raise ValueError(
            f"asw_port*(1-alpha) 须为整数（PSW 台数），当前为 {psw_f}（asw_port={asw_port}, alpha={alpha}）"
        )
    psw_count = int(round(psw_f))
    if psw_count < 1:
        raise ValueError(f"PSW 台数 asw_port*(1-alpha) 须 >=1，当前为 {psw_count}")

    upl_cap = asw_port * (1.0 - alpha)
    if upl_cap + 1e-9 < psw_count:
        raise ValueError(
            f"ASW 上联端口 asw_port*(1-alpha)={upl_cap} 须 >= PSW 台数 {psw_count}"
        )

    dnl_cap = psw_port * beta
    if dnl_cap + 1e-9 < asw_count:
        raise ValueError(
            f"PSW 下联端口 psw_port*beta={dnl_cap} 须 >= ASW 台数 {asw_count}"
        )

    servers_count = gpu_count // gpus_per_server
    servers_per_asw = slots_per_asw // gpus_per_server

    filename = f"Meta_Topo_{gpu_count}g_{gpus_per_server}gps_{nic_bw}_{gpu_type}"
    topo = TopoGenerator(filename)

    topo.SetConfig(
        gpu_count=gpu_count,
        gpus_per_server=gpus_per_server,
        nv_switch_per_server=nv_switch_per_server,
        gpu_type=gpu_type,
    )
    topo.SetPortRatios(asw_port, alpha, psw_port, beta)

    print(f"  服务器数: {servers_count}")
    print(f"  ASW 端口: {asw_port}, alpha: {alpha}, 每台 ASW 下联 GPU: {slots_per_asw} ({servers_per_asw} server/ASW)")
    print(f"  ASW 数量: {asw_count} (= gpu_count // slots)")
    print(f"  PSW 端口: {psw_port}, beta: {beta}，PSW 下联容量 psw_port*beta={dnl_cap} (>= ASW 数)")
    print(f"  PSW 数量: {psw_count} (= asw_port*(1-alpha))")

    topo.AddNVSwitches()
    asw_ids = topo.AddASWSwitches(asw_count)
    psw_ids = topo.AddPSWSwitches(psw_count)

    topo.ConnectGPUsToNVSwitch(nvlink_bw=nvlink_bw, nv_latency=nv_latency)
    topo.FullConnectGPUsToASW(asw_ids, nic_bw=nic_bw, nic_latency=latency)
    topo.FullConnectASWToPSW(asw_ids, psw_ids, uplink_bw=asw_to_psw_bw, latency=latency)

    print(
        f"  ASW–PSW 全连接: {asw_count} ASW × {psw_count} PSW = {asw_count * psw_count} 条链路"
    )

    topo.Generate()
    print("Meta 拓扑生成完成！")
    return filename


def generateDeepSeekTopo(
    gpu_count=2048,
    gpus_per_server=8,
    port=64,
    alpha=0.5,
    psw_port=64,
    gpu_type="H800",
    nv_switch_per_server=1,
    nvlink_bw="3600Gbps",
    nic_bw="400Gbps",
    asw_to_psw_bw="400Gbps",
    nv_latency="0.000025ms",
    latency="0.0005ms",
    error_rate="0",
    name_suffix="",
):
    """
    DeepSeek 风格 segment + Rail 拓扑（TopoGenerator + Generate 写文件）。

    GPU–ASW（每个 segment 内）
    ------------------------
    同一 segment 内，**各 Host（server）上机内槽位相同 rank 的 GPU**（即所有 host 上的 GPU
    rank 0 一伙、rank 1 一伙…）全部接到 **同一台 ASW**。等价实现：GPU 全局下标 i 对应
    host=i//g、rank=i%g、seg=host//hosts_per_segment，连 ASW(seg, rank)。

    ASW–PSW（存在多个 segment 时）
    ------------------------------
    每个 segment 仍只有 gpus_per_server 台 ASW（与 rank 一一对应）。**不同 segment、相同
    rank** 的各台 ASW，全部只连接 **同一组** 共 **port*(1-alpha)** 台 PSW（代码里 upl_ports；
    即 ASW 上联端口数对应的 spine 组大小）。PSW 总数 = gpus_per_server * port*(1-alpha)，
    rank r 对应下标区间 [r*upl_ports, (r+1)*upl_ports)。

    单 segment 时不建 PSW。GPU–ASW 仅 AddLink，不使用 FullConnectGPUsToASW。
    """
    print(f"开始生成 DeepSeek 风格拓扑，GPU 数量: {gpu_count}...")

    g = int(gpus_per_server)
    if g < 1:
        raise ValueError("gpus_per_server 须 >= 1")

    num_hosts = gpu_count // g
    if num_hosts * g != gpu_count:
        raise ValueError("gpu_count 须为 gpus_per_server 的整数倍（以得到整数 Host 数）")

    down_f = float(port) * float(alpha)
    if abs(down_f - round(down_f)) > 1e-9:
        raise ValueError(
            f"port*alpha 须为整数，当前为 {down_f}（port={port}, alpha={alpha}）"
        )
    hosts_per_segment = int(round(down_f))
    if hosts_per_segment < 1:
        raise ValueError("port*alpha 推算得到的每 segment Host 数须 >= 1")

    upl_f = float(port) * (1.0 - float(alpha))
    if abs(upl_f - round(upl_f)) > 1e-9:
        raise ValueError(
            f"port*(1-alpha) 须为整数，当前为 {upl_f}（port={port}, alpha={alpha}）"
        )
    upl_ports = int(round(upl_f))

    segment_gpus = hosts_per_segment * g
    if segment_gpus < 1:
        raise ValueError("segment_gpus 无效")
    if gpu_count % segment_gpus != 0:
        raise ValueError(
            f"gpu_count（={gpu_count}）须为 segment_gpus（={segment_gpus}）的整数倍"
        )
    segment_num = gpu_count // segment_gpus

    asw_total = segment_num * g
    need_psw = segment_num > 1
    if need_psw and upl_ports < 1:
        raise ValueError(
            "存在多个 segment 时需要 PSW，但 port*(1-alpha) < 1，无法为 ASW 分配上联 spine"
        )
    if need_psw:
        psw_total = g * upl_ports
        if segment_num > int(psw_port):
            raise ValueError(
                f"segment_num（={segment_num}）须 <= psw_port（={psw_port}），"
                "否则每台 PSW 从同 rank 各 segment 的 ASW 收链数将超过下联端口上界。"
            )
    else:
        psw_total = 0

    filename = (
        f"DeepSeek_{gpu_count}g_{g}gps_p{port}a{alpha}_{nic_bw}_{gpu_type}{name_suffix}"
    )

    print(f"  Host 数: {num_hosts}")
    print(
        f"  每 segment：Host={hosts_per_segment}，GPU={segment_gpus}；"
        f"segment_num={segment_num}"
    )
    print(
        f"  ASW 总数: {asw_total}（每 segment {g} 台 = gpus_per_server，rank 0..{g - 1}）"
    )
    print(
        f"  ASW 下联槽位 port*alpha={hosts_per_segment} Host，"
        f"上联槽位 port*(1-alpha)={upl_ports}"
    )
    if need_psw:
        print(
            f"  PSW 总数: {psw_total}（= gpus_per_server * port*(1-alpha) = {g}*{upl_ports}）"
        )
    else:
        print("  PSW：不需要（仅 1 个 segment），拓扑为 ASW-only underlay")

    topo = TopoGenerator(filename)
    topo.SetConfig(
        gpu_count=gpu_count,
        gpus_per_server=g,
        nv_switch_per_server=nv_switch_per_server,
        gpu_type=gpu_type,
    )

    topo.AddNVSwitches()
    asw_flat = topo.AddASWSwitches(asw_total)
    if need_psw:
        psw_flat = topo.AddPSWSwitches(psw_total)
    else:
        psw_flat = []

    def GetAswId(seg, rank):
        """segment seg 内、负责机内 rank 条 Rail 的那台 ASW。"""
        return asw_flat[seg * g + rank]

    topo.ConnectGPUsToNVSwitch(nvlink_bw=nvlink_bw, nv_latency=nv_latency)

    # 同一 segment 内：各 host 上相同 rank 的 GPU → 同一 ASW(seg, rank)
    for i in range(gpu_count):
        host = i // g
        rank = i % g
        seg = host // hosts_per_segment
        asw_id = GetAswId(seg, rank)
        topo.AddLink(i, asw_id, nic_bw, latency, str(error_rate))

    if need_psw:
        # 各 segment 相同 rank 的 ASW → 同一组 port*(1-alpha) 台 PSW（rank 对应 spine 块）
        for seg in range(segment_num):
            for rank in range(g):
                asw_id = GetAswId(seg, rank)
                base = rank * upl_ports
                for u in range(upl_ports):
                    topo.AddLink(
                        asw_id,
                        psw_flat[base + u],
                        asw_to_psw_bw,
                        latency,
                        str(error_rate),
                    )

    topo.Generate()
    print(f"DeepSeek 风格拓扑已写入: {filename}")
    return filename

def GenerateROFTTopo(
    gpu_count=256,
    gpus_per_server=8,
    nv_switch_per_server=1,
    gpu_type="H100",
    asw_port=64,
    alpha=0.5,
    psw_port=64,
    beta=1.0,
    nvlink_bw="3600Gbps",
    nic_bw="400Gbps",
    asw_to_psw_bw="400Gbps",
    nv_latency="0.000025ms",
    latency="0.0005ms",
    error_rate="0",
    name_suffix="",
):
    """
    ROFT（Rail-Optimized Full ToR）：Rail 下联 + ASW–PSW 全连接 Spine。

    即 Spectrum-X / gen_Topo_Template.Rail_Opti_SingleToR 风格，含 PSW 层。
    若只需 ASW、无 PSW，请使用 GenerateRailOnlyTopo。

    GPU–ASW：segment 内同 rank → 同一 ASW（hosts_per_segment = asw_port * alpha）。
    ASW–PSW：全连接；PSW 台数 = asw_port * (1 - alpha)。
    """
    print(f"开始生成 ROFT (Rail-Optimized Full ToR) 拓扑，GPU 数量: {gpu_count}...")

    g = int(gpus_per_server)
    if g < 1:
        raise ValueError("gpus_per_server 须 >= 1")
    if gpu_count % g != 0:
        raise ValueError("gpu_count 须为 gpus_per_server 的整数倍")

    num_hosts = gpu_count // g

    down_f = float(asw_port) * float(alpha)
    if abs(down_f - round(down_f)) > 1e-9:
        raise ValueError(
            f"asw_port*alpha 须为整数，当前为 {down_f}（asw_port={asw_port}, alpha={alpha}）"
        )
    hosts_per_segment = int(round(down_f))
    if hosts_per_segment < 1:
        raise ValueError("asw_port*alpha 推算的每 segment Host 数须 >= 1")
    if num_hosts % hosts_per_segment != 0:
        raise ValueError(
            f"Host 数（={num_hosts}）须为 hosts_per_segment（={hosts_per_segment}）的整数倍"
        )

    upl_f = float(asw_port) * (1.0 - float(alpha))
    if abs(upl_f - round(upl_f)) > 1e-9:
        raise ValueError(
            f"asw_port*(1-alpha) 须为整数，当前为 {upl_f}（asw_port={asw_port}, alpha={alpha}）"
        )
    psw_count = int(round(upl_f))
    if psw_count < 1:
        raise ValueError(f"PSW 台数 asw_port*(1-alpha) 须 >= 1，当前为 {psw_count}")

    segment_num = num_hosts // hosts_per_segment
    asw_count = segment_num * g
    segment_gpus = hosts_per_segment * g

    if gpu_count % segment_gpus != 0:
        raise ValueError(
            f"gpu_count（={gpu_count}）须为 segment_gpus（={segment_gpus}）的整数倍"
        )

    dnl_cap = float(psw_port) * float(beta)
    if abs(dnl_cap - round(dnl_cap)) > 1e-9:
        raise ValueError(f"psw_port*beta 须为整数，当前为 {dnl_cap}")
    dnl_cap_i = int(round(dnl_cap))
    if dnl_cap_i < asw_count:
        raise ValueError(
            f"PSW 下联容量 psw_port*beta（={dnl_cap_i}）须 >= ASW 台数 {asw_count}"
        )

    max_segments_per_pod = psw_count // g
    if segment_num > max_segments_per_pod:
        raise ValueError(
            f"segment_num（={segment_num}）须 <= asw_port*(1-alpha)/gpus_per_server"
            f"（={max_segments_per_pod}），否则 Rail Single-ToR 下单 Pod 内 PSW 下联 ASW 组数不足"
        )

    filename = (
        f"ROFT_{gpu_count}g_{g}gps_p{asw_port}a{alpha}_{nic_bw}_{gpu_type}{name_suffix}"
    )

    print(f"  Host 数: {num_hosts}")
    print(
        f"  每 segment：Host={hosts_per_segment}，GPU={segment_gpus}；"
        f"segment_num={segment_num}"
    )
    print(f"  ASW 总数: {asw_count}（每 segment {g} 台，按 rank Rail）")
    print(f"  PSW 总数: {psw_count} (= asw_port*(1-alpha))")
    print(
        f"  ASW–PSW 全连接: {asw_count} × {psw_count} = {asw_count * psw_count} 条链路"
    )

    topo = TopoGenerator(filename)
    topo.SetConfig(
        gpu_count=gpu_count,
        gpus_per_server=g,
        nv_switch_per_server=nv_switch_per_server,
        gpu_type=gpu_type,
    )

    topo.AddNVSwitches()
    asw_ids = topo.AddASWSwitches(asw_count)
    psw_ids = topo.AddPSWSwitches(psw_count)

    def GetAswId(seg, rank):
        return asw_ids[seg * g + rank]

    topo.ConnectGPUsToNVSwitch(nvlink_bw=nvlink_bw, nv_latency=nv_latency)

    for i in range(gpu_count):
        host = i // g
        rank = i % g
        seg = host // hosts_per_segment
        topo.AddLink(i, GetAswId(seg, rank), nic_bw, latency, str(error_rate))

    topo.ConnectASWToPSW(
        asw_ids, psw_ids, uplink_bw=asw_to_psw_bw, latency=latency
    )

    topo.Generate()
    print(f"ROFT 拓扑已写入: {filename}")
    return filename


def GenerateRailOnlyTopo(
    gpu_count=256,
    gpus_per_server=8,
    nv_switch_per_server=1,
    gpu_type="H100",
    asw_port=64,
    alpha=0.5,
    nvlink_bw="3600Gbps",
    nic_bw="400Gbps",
    asw_to_asw_bw="400Gbps",
    nv_latency="0.000025ms",
    latency="0.0005ms",
    error_rate="0",
    name_suffix="",
):
    """
    Rail-only：跨机通信仅经 ASW，不建 PSW。

    GPU–ASW（segment 内 Rail）
    -------------------------
    hosts_per_segment = asw_port * alpha。同 segment 内各 host 相同 rank 的 GPU → ASW(seg, rank)。

    ASW–ASW（跨 segment、同 rank）
    -----------------------------
    当 segment_num > 1 时，不同 segment 上相同 rank 的 ASW 两两全连接；
    每条 ASW 需 (segment_num - 1) 条上联，要求 asw_port * (1 - alpha) >= segment_num - 1。
    单 segment 时无上联，纯 ASW underlay。
    """
    print(f"开始生成 Rail-only 拓扑（仅 ASW），GPU 数量: {gpu_count}...")

    g = int(gpus_per_server)
    if g < 1:
        raise ValueError("gpus_per_server 须 >= 1")
    if gpu_count % g != 0:
        raise ValueError("gpu_count 须为 gpus_per_server 的整数倍")

    num_hosts = gpu_count // g

    down_f = float(asw_port) * float(alpha)
    if abs(down_f - round(down_f)) > 1e-9:
        raise ValueError(
            f"asw_port*alpha 须为整数，当前为 {down_f}（asw_port={asw_port}, alpha={alpha}）"
        )
    hosts_per_segment = int(round(down_f))
    if hosts_per_segment < 1:
        raise ValueError("asw_port*alpha 推算的每 segment Host 数须 >= 1")
    if num_hosts % hosts_per_segment != 0:
        raise ValueError(
            f"Host 数（={num_hosts}）须为 hosts_per_segment（={hosts_per_segment}）的整数倍"
        )

    upl_f = float(asw_port) * (1.0 - float(alpha))
    if abs(upl_f - round(upl_f)) > 1e-9:
        raise ValueError(
            f"asw_port*(1-alpha) 须为整数，当前为 {upl_f}（asw_port={asw_port}, alpha={alpha}）"
        )
    upl_ports = int(round(upl_f))

    segment_num = num_hosts // hosts_per_segment
    asw_count = segment_num * g
    segment_gpus = hosts_per_segment * g

    if gpu_count % segment_gpus != 0:
        raise ValueError(
            f"gpu_count（={gpu_count}）须为 segment_gpus（={segment_gpus}）的整数倍"
        )

    if segment_num > 1:
        need_upl = segment_num - 1
        if upl_ports < need_upl:
            raise ValueError(
                f"跨 segment 时 ASW 上联数 asw_port*(1-alpha)（={upl_ports}）"
                f"须 >= segment_num-1（={need_upl}）"
            )

    filename = (
        f"RailOnly_{gpu_count}g_{g}gps_p{asw_port}a{alpha}_{nic_bw}_{gpu_type}{name_suffix}"
    )

    print(f"  Host 数: {num_hosts}")
    print(
        f"  每 segment：Host={hosts_per_segment}，GPU={segment_gpus}；"
        f"segment_num={segment_num}"
    )
    print(f"  ASW 总数: {asw_count}（无 PSW）")
    if segment_num > 1:
        pairs = segment_num * (segment_num - 1) // 2
        asw_asw_links = pairs * g
        print(
            f"  ASW–ASW（同 rank 跨 segment 全连接）: 每 rank {pairs} 对 × {g} rank"
            f" = {asw_asw_links} 条"
        )
    else:
        print("  ASW–ASW：无（单 segment）")

    topo = TopoGenerator(filename)
    topo.SetConfig(
        gpu_count=gpu_count,
        gpus_per_server=g,
        nv_switch_per_server=nv_switch_per_server,
        gpu_type=gpu_type,
    )

    topo.AddNVSwitches()
    asw_ids = topo.AddASWSwitches(asw_count)

    def GetAswId(seg, rank):
        return asw_ids[seg * g + rank]

    topo.ConnectGPUsToNVSwitch(nvlink_bw=nvlink_bw, nv_latency=nv_latency)

    for i in range(gpu_count):
        host = i // g
        rank = i % g
        seg = host // hosts_per_segment
        topo.AddLink(i, GetAswId(seg, rank), nic_bw, latency, str(error_rate))

    if segment_num > 1:
        for rank in range(g):
            for seg_a in range(segment_num):
                for seg_b in range(seg_a + 1, segment_num):
                    topo.AddLink(
                        GetAswId(seg_a, rank),
                        GetAswId(seg_b, rank),
                        asw_to_asw_bw,
                        latency,
                        str(error_rate),
                    )

    topo.Generate()
    print(f"Rail-only 拓扑已写入: {filename}")
    return filename


def GenerateHPNTopo(
    gpu_count=256,
    gpus_per_server=8,
    nv_switch_per_server=1,
    gpu_type="H100",
    switch_throughput=12800,  # Gbps
    alpha=0.5,
    nvlink_bw="3600Gbps",
    nic_bw="200Gbps",
    asw_to_psw_bw="400Gbps",
    nv_latency="0.000025ms",
    latency="0.0005ms",
    error_rate="0",
    dual_plane=True,  # 是否为双平面（16个ASW），False则为单平面（8个ASW）
):
    """
    生成阿里巴巴 HPN (High Performance Network) 风格拓扑。
    
    拓扑特点
    --------
    - 固定16个ASW（双平面模式）或8个ASW（单平面模式）
    - 双平面模式：Plane 0 有8个ASW (0-7)，Plane 1 有8个ASW (8-15)
    - 每个server内的8个GPU根据其rank（0-7）连接到对应的ASW对
    - GPU rank i 连接到 ASW i (Plane 0) 和 ASW (i+8) (Plane 1)
    - 每个GPU到ASW的NIC带宽为200Gbps
    - ASW到PSW的带宽为400Gbps
    
    参数说明
    --------
    gpu_count : int
        GPU总数，默认256
    gpus_per_server : int
        每个server的GPU数，默认8（必须为8以匹配16个ASW）
    switch_throughput : float
        ASW交换机吞吐量（单位Gbps），默认6400Gbps
    alpha : float
        ASW下联端口比例，默认0.5
    nic_bw : str
        GPU到ASW的NIC带宽，默认"200Gbps"
    asw_to_psw_bw : str
        ASW到PSW的上联带宽，默认"400Gbps"
    dual_plane : bool
        是否为双平面模式，默认True
        
    端口计算
    --------
    - ASW下联端口数 = (switch_throughput × alpha) / nic_bw数值
    - ASW上联端口数 = (switch_throughput × (1-alpha)) / asw_to_psw_bw数值
    - 每个Plane的PSW数量 = ASW上联端口数
    - 双平面总PSW数 = 上联端口数 × 2
    """
    print(f"开始生成 HPN 拓扑，GPU数量: {gpu_count}...")
    
    if gpus_per_server != 8:
        raise ValueError("HPN 拓扑要求 gpus_per_server = 8（匹配16个ASW的DualToR设计）")
    
    num_servers = gpu_count // gpus_per_server
    if num_servers * gpus_per_server != gpu_count:
        raise ValueError(f"gpu_count（={gpu_count}）须为 gpus_per_server（={gpus_per_server}）的整数倍")
    
    # 提取带宽数值（假设格式为 "XXXGbps"）
    nic_bw_value = float(nic_bw.replace("Gbps", "").replace("gbps", ""))
    asw_psw_bw_value = float(asw_to_psw_bw.replace("Gbps", "").replace("gbps", ""))
    
    # 计算端口数
    downlink_ports_f = (switch_throughput * alpha) / nic_bw_value
    uplink_ports_f = (switch_throughput * (1.0 - alpha)) / asw_psw_bw_value
    
    if abs(downlink_ports_f - round(downlink_ports_f)) > 1e-6:
        raise ValueError(
            f"ASW 下联端口数 (switch_throughput×alpha / nic_bw) = {downlink_ports_f} 须为整数"
        )
    if abs(uplink_ports_f - round(uplink_ports_f)) > 1e-6:
        raise ValueError(
            f"ASW 上联端口数 (switch_throughput×(1-alpha) / asw_to_psw_bw) = {uplink_ports_f} 须为整数"
        )
    
    downlink_ports = int(round(downlink_ports_f))
    uplink_ports = int(round(uplink_ports_f))
    
    # ASW 和 PSW 数量
    if dual_plane:
        asw_count = 16  # 固定16个ASW，两个Plane各8个
        psw_per_plane = uplink_ports
        psw_count = psw_per_plane * 2  # 两个Plane
        mode_str = "DualToR_DualPlane"
    else:
        asw_count = 8   # 单平面只有8个ASW
        psw_per_plane = uplink_ports
        psw_count = psw_per_plane
        mode_str = "DualToR_SinglePlane"
    
    # 检查下联端口容量
    gpus_per_asw = num_servers  # 每个ASW连接所有server的对应rank GPU
    if gpus_per_asw > downlink_ports:
        raise ValueError(
            f"ASW 下联端口数（={downlink_ports}）不足以连接 {gpus_per_asw} 个GPU。"
            f"需增大 switch_throughput 或 alpha，或减小 GPU 数量"
        )
    
    filename = f"AlibabaHPN_{gpu_count}g_{gpus_per_server}gps_{mode_str}_{nic_bw}_{gpu_type}"
    topo = TopoGenerator(filename)
    
    topo.SetConfig(
        gpu_count=gpu_count,
        gpus_per_server=gpus_per_server,
        nv_switch_per_server=nv_switch_per_server,
        gpu_type=gpu_type,
    )
    
    print(f"  服务器数: {num_servers}")
    print(f"  交换机吞吐量: {switch_throughput}Gbps, alpha: {alpha}")
    print(f"  ASW 下联端口数: {downlink_ports} (每个ASW连接{gpus_per_asw}个GPU)")
    print(f"  ASW 上联端口数: {uplink_ports}")
    print(f"  ASW 数量: {asw_count}")
    print(f"  PSW 数量: {psw_count} ({'每个Plane ' + str(psw_per_plane) if dual_plane else '单Plane'})")
    
    # 添加交换机
    topo.AddNVSwitches()
    asw_ids = topo.AddASWSwitches(asw_count)
    psw_ids = topo.AddPSWSwitches(psw_count)
    
    # 连接 GPU 到 NVSwitch
    topo.ConnectGPUsToNVSwitch(nvlink_bw=nvlink_bw, nv_latency=nv_latency)
    
    # 连接 GPU 到 ASW
    # 每个GPU根据其在server内的rank连接到对应的ASW
    for gpu_id in range(gpu_count):
        rank = gpu_id % gpus_per_server  # GPU在server内的rank (0-7)
        
        if dual_plane:
            # DualPlane: rank对应ASW为 rank 和 rank+8
            asw_plane0 = asw_ids[rank]
            asw_plane1 = asw_ids[rank + 8]
            topo.AddLink(gpu_id, asw_plane0, nic_bw, latency, str(error_rate))
            topo.AddLink(gpu_id, asw_plane1, nic_bw, latency, str(error_rate))
        else:
            # SinglePlane: rank只对应一个ASW
            asw_id = asw_ids[rank]
            topo.AddLink(gpu_id, asw_id, nic_bw, latency, str(error_rate))
    
    # 连接 ASW 到 PSW
    if dual_plane:
        # Plane 0: ASW 0-7 全连接到前 psw_per_plane 个PSW
        plane0_asw = asw_ids[0:8]
        plane0_psw = psw_ids[0:psw_per_plane]
        for asw_id in plane0_asw:
            for psw_id in plane0_psw:
                topo.AddLink(asw_id, psw_id, asw_to_psw_bw, latency, str(error_rate))
        
        # Plane 1: ASW 8-15 全连接到后 psw_per_plane 个PSW
        plane1_asw = asw_ids[8:16]
        plane1_psw = psw_ids[psw_per_plane:psw_count]
        for asw_id in plane1_asw:
            for psw_id in plane1_psw:
                topo.AddLink(asw_id, psw_id, asw_to_psw_bw, latency, str(error_rate))
        
        print(f"  Plane 0: {len(plane0_asw)} ASW × {len(plane0_psw)} PSW = {len(plane0_asw) * len(plane0_psw)} 条链路")
        print(f"  Plane 1: {len(plane1_asw)} ASW × {len(plane1_psw)} PSW = {len(plane1_asw) * len(plane1_psw)} 条链路")
    else:
        # SinglePlane: 所有ASW全连接到所有PSW
        for asw_id in asw_ids:
            for psw_id in psw_ids:
                topo.AddLink(asw_id, psw_id, asw_to_psw_bw, latency, str(error_rate))
        print(f"  SinglePlane: {len(asw_ids)} ASW × {len(psw_ids)} PSW = {len(asw_ids) * len(psw_ids)} 条链路")
    
    topo.Generate()
    print(f"HPN 拓扑已生成: {filename}")
    return filename

def GenerateZcubeTopo(
    n,
    k=2,
    gpus_per_server=8,
    nv_switch_per_server=1,
    gpu_type="H100",
    asw_port=None,
    psw_port=None,
    alpha=0.5,
    beta=0.5,
    nvlink_bw="3600Gbps",
    nic_bw="200Gbps",
    asw_to_psw_bw="200Gbps",
    nv_latency="0.000025ms",
    latency="0.0005ms",
    error_rate="0",
):
    """
    生成 Zcube 拓扑（当前实现 k=2 的典型形态）。

    参数含义
    --------
    n : int
        每一层交换机台数；k=2 时 ASW、PSW 各 n 台，总 GPU 数为 n**k = n**2。
    k : int
        交换机层级数；当前仅支持 k=2（一层 ASW、一层 PSW）。总 GPU = n**k。
    gpus_per_server : int
        每台 host 上的 GPU 数。每个 segment 挂 n 个 GPU，要求 n % gpus_per_server == 0，
        则每个 segment 对应 n // gpus_per_server 台 host。

    连线规则（k=2）
    --------------
    - 将 GPU 全局编号 gid in [0, n^2) 分解为 seg = gid // n、rail = gid % n。
    - gid 与 ASW[seg] 相连（每个 ASW 下联 n 个 GPU，构成一个 segment）。
    - gid 与 PSW[rail] 相连（同一 segment 内 GPU 依次对应不同 PSW；下一 segment 仍按 rail 下标
      与同一组 PSW 相连，故每个 PSW 共连接 n 条 GPU–PSW 边，每个 rail 一列）。
    - 任意 ASW 与任意 PSW 全连接（n×n 笛卡尔积）。

    端口约定（与 SetPortRatios / FullConnectASWToPSW 一致）
    --------------------------------------------------------
    默认 asw_port = psw_port = 2n、alpha = beta = 0.5：单侧 n 口接 GPU/对侧交换机，
    另一侧 n 口接对层，满足全连接所需容量。
    """
    print(f"开始生成 Zcube 拓扑（n={n}, k={k}）...")

    if k != 2:
        raise ValueError(
            f"当前 GenerateZcubeTopo 仅实现 k=2；收到 k={k}。"
            "一般 k=2 时总 GPU 数为 n**2，ASW/PSW 各 n 台。"
        )
    nn = int(n)
    if nn < 1:
        raise ValueError("n 须为 >= 1 的整数")

    g = int(gpus_per_server)
    if g < 1:
        raise ValueError("gpus_per_server 须 >= 1")

    gpu_count = nn ** k
    if gpu_count % g != 0:
        raise ValueError(
            f"gpu_count=n**k={gpu_count} 须为 gpus_per_server（={g}）的整数倍"
        )
    if nn % g != 0:
        raise ValueError(
            f"Zcube 每个 segment 含 n={nn} 个 GPU，须能整除为整数台 host："
            f"要求 n % gpus_per_server == 0，当前 n % g = {nn % g}"
        )

    if asw_port is None:
        asw_port = 2 * nn
    if psw_port is None:
        psw_port = 2 * nn

    ap = int(asw_port)
    pp = int(psw_port)
    aa = float(alpha)
    bb = float(beta)

    slots_f = ap * aa
    if abs(slots_f - round(slots_f)) > 1e-9:
        raise ValueError(
            f"asw_port*alpha 须为整数，当前为 {slots_f}（asw_port={ap}, alpha={aa}）"
        )
    slots_per_asw = int(round(slots_f))
    if slots_per_asw != nn:
        raise ValueError(
            f"Zcube(k=2) 要求每台 ASW 下联 GPU 数 = n = {nn}，"
            f"当前 asw_port*alpha = {slots_per_asw}；请设 asw_port=2n, alpha=0.5"
        )

    upl_f = ap * (1.0 - aa)
    if abs(upl_f - round(upl_f)) > 1e-9:
        raise ValueError(
            f"asw_port*(1-alpha) 须为整数，当前为 {upl_f}"
        )
    upl_ports = int(round(upl_f))
    if upl_ports != nn:
        raise ValueError(
            f"Zcube 要求 ASW 上联端口数 = n = {nn}（与 PSW 台数一致），"
            f"当前 asw_port*(1-alpha)={upl_ports}"
        )

    dnl_asw_psw = pp * bb
    if abs(dnl_asw_psw - round(dnl_asw_psw)) > 1e-9:
        raise ValueError(f"psw_port*beta 须为整数，当前为 {dnl_asw_psw}")
    dnl_asw_psw_i = int(round(dnl_asw_psw))
    if dnl_asw_psw_i < nn:
        raise ValueError(
            f"PSW 下联 ASW 所需端口 psw_port*beta（={dnl_asw_psw_i}）须 >= ASW 台数 n={nn}"
        )

    gpu_psw_ports = pp * (1.0 - bb)
    if abs(gpu_psw_ports - round(gpu_psw_ports)) > 1e-9:
        raise ValueError(f"psw_port*(1-beta) 须为整数，当前为 {gpu_psw_ports}")
    gpu_psw_ports_i = int(round(gpu_psw_ports))
    if gpu_psw_ports_i < nn:
        raise ValueError(
            f"PSW 上用于 GPU 的端口数 psw_port*(1-beta)（={gpu_psw_ports_i}）"
            f"须 >= n={nn}（每个 PSW 接 n 条 GPU–PSW 边）"
        )

    asw_count = nn
    psw_count = nn
    num_hosts = gpu_count // g

    filename = f"Zcube_n{nn}_k{k}_{gpu_count}g_{g}gps_{nic_bw}_{gpu_type}"
    topo = TopoGenerator(filename)
    topo.SetConfig(
        gpu_count=gpu_count,
        gpus_per_server=g,
        nv_switch_per_server=nv_switch_per_server,
        gpu_type=gpu_type,
    )
    topo.SetPortRatios(ap, aa, pp, bb)

    print(f"  总 GPU: {gpu_count} (= n**k = {nn}**{k})")
    print(f"  Host 数: {num_hosts}；每 segment Host 数: {nn // g} (= n//gpus_per_server)")
    print(f"  ASW: {asw_count}，PSW: {psw_count}；ASW–PSW 全连接: {asw_count * psw_count} 条")

    topo.AddNVSwitches()
    asw_ids = topo.AddASWSwitches(asw_count)
    psw_ids = topo.AddPSWSwitches(psw_count)

    topo.ConnectGPUsToNVSwitch(nvlink_bw=nvlink_bw, nv_latency=nv_latency)

    for gid in range(gpu_count):
        seg = gid // nn
        rail = gid % nn
        topo.AddLink(gid, asw_ids[seg], nic_bw, latency, str(error_rate))
        topo.AddLink(gid, psw_ids[rail], nic_bw, latency, str(error_rate))

    topo.FullConnectASWToPSW(
        asw_ids, psw_ids, uplink_bw=asw_to_psw_bw, latency=latency
    )

    topo.Generate()
    print(f"Zcube 拓扑已写入: {filename}")
    return filename


# ===========================
# 使用示例 1: 单 Pod 拓扑
# ===========================
def GenerateSinglePodTopo():
    """生成单 Pod 拓扑（类似 Spectrum-X）"""
    topo = TopoGenerator("Custom_SinglePod_64g_8gps_100Gbps_A100")
    
    # 配置
    topo.SetConfig(
        gpu_count=64,           # 64 个 GPU
        gpus_per_server=8,      # 每台服务器 8 个 GPU
        nv_switch_per_server=1, # 每台服务器 1 个 NVLink 交换机
        gpu_type="A100"
    )
    
    # 添加交换机
    topo.AddNVSwitches()                    # 8 个 NVLink 交换机
    asw_ids = topo.AddASWSwitches(8)        # 8 个 ASW 交换机
    psw_ids = topo.AddPSWSwitches(4)        # 4 个 PSW 交换机
    
    # 建立连接
    topo.ConnectGPUsToNVSwitch(nvlink_bw="2400Gbps", nv_latency="0.000025ms")
    topo.ConnectGPUsToASW(asw_ids, nic_bw="100Gbps", nic_latency="0.0005ms")
    topo.ConnectASWToPSW(asw_ids, psw_ids, uplink_bw="400Gbps", latency="0.0005ms")
    
    # 生成文件
    topo.Generate()


# ===========================
# 使用示例 2: 双 Pod 拓扑
# ===========================
def GenerateDualPodTopo():
    """生成双 Pod 拓扑"""
    topo = TopoGenerator("Custom_DualPod_128g_8gps_100Gbps_A100")
    
    # 配置
    topo.SetConfig(
        gpu_count=128,          # 128 个 GPU (64 per Pod)
        gpus_per_server=8,
        nv_switch_per_server=1,
        gpu_type="A100"
    )
    
    # Pod 0 和 Pod 1 的交换机
    topo.AddNVSwitches()                    # 16 个 NVLink 交换机
    asw_ids = topo.AddASWSwitches(16)       # 16 个 ASW (8 per Pod)
    psw_ids = topo.AddPSWSwitches(8)        # 8 个 PSW (4 per Pod)
    dsw_ids = topo.AddDSWSwitches(2)        # 2 个 DSW (Core)
    
    # GPU 到 NVLink 和 ASW
    topo.ConnectGPUsToNVSwitch(nvlink_bw="2400Gbps")
    topo.ConnectGPUsToASW(asw_ids, nic_bw="100Gbps")
    
    # Pod 0 的 ASW 到 PSW
    topo.ConnectASWToPSW(asw_ids[0:8], psw_ids[0:4], uplink_bw="400Gbps")
    
    # Pod 1 的 ASW 到 PSW
    topo.ConnectASWToPSW(asw_ids[8:16], psw_ids[4:8], uplink_bw="400Gbps")
    
    # 两个 Pod 的 PSW 都连到 DSW（跨 Pod 连接）
    topo.ConnectPSWToDSW(psw_ids, dsw_ids, uplink_bw="800Gbps", latency="0.001ms")
    
    # 生成文件
    topo.Generate()


# ===========================
# 使用示例 3: 自定义拓扑
# ===========================
def GenerateCustomTopo():
    """完全自定义的拓扑"""
    topo = TopoGenerator("My_Custom_Topo")
    
    # 您的自定义配置
    topo.SetConfig(
        gpu_count=32,
        gpus_per_server=8,
        nv_switch_per_server=1,
        gpu_type="H100"
    )
    
    # 添加您需要的交换机
    topo.AddNVSwitches()
    asw_ids = topo.AddASWSwitches(4)
    psw_ids = topo.AddPSWSwitches(2)
    
    # 建立您需要的连接
    topo.ConnectGPUsToNVSwitch(nvlink_bw="3600Gbps")  # H100 NVLink
    topo.ConnectGPUsToASW(asw_ids, nic_bw="200Gbps")
    topo.ConnectASWToPSW(asw_ids, psw_ids, uplink_bw="400Gbps")
    
    # 您还可以手动添加特殊链接
    # topo.AddLink(0, 16, "1000Gbps", "0.0001ms", "0")
    
    topo.Generate()


if __name__ == "__main__":
    print("选择要生成的拓扑类型:")
    print("1. 单 Pod 拓扑 (64 GPU)")
    print("2. 双 Pod 拓扑 (128 GPU)")
    print("3. 自定义拓扑 (32 GPU)")
    print("4. Meta (Facebook) 拓扑")
    print("5. DeepSeek 拓扑")
    print("6. Rail-only 拓扑（仅 ASW，无 PSW）")
    print("7. ROFT 拓扑（Rail + PSW 全连接）")
    print("8. Zcube 拓扑")

    choice = input("请输入选项 (1/2/3/4/5/6/7/8): ").strip()
    
    if choice == "1":
        GenerateSinglePodTopo()
    elif choice == "2":
        GenerateDualPodTopo()
    elif choice == "3":
        GenerateCustomTopo()
    elif choice == "4":
        # Meta 拓扑：默认 asw_port=64, psw_port=256, alpha=0.5, beta=1；ASW 台数由 gpu_count/slots 决定
        GenerateMetaTopo(
            gpu_count=8192,
            gpus_per_server=8,
            nv_switch_per_server=1,
            gpu_type="A100",
            nvlink_bw="3600Gbps",
            nic_bw="400Gbps",
            asw_to_psw_bw="400Gbps",
        )
    elif choice == "5":
        generateDeepSeekTopo()
    elif choice == "6":
        # 256 GPU / 8 gps；asw_port=64, alpha=0.5 → 1 segment、8 ASW、无 PSW
        GenerateRailOnlyTopo(
            gpu_count=256,
            gpus_per_server=8,
            gpu_type="H100",
            asw_port=64,
            alpha=0.5,
            nic_bw="400Gbps",
        )
    elif choice == "7":
        # ROFT：同上规模 + 32 PSW，ASW–PSW 全连接
        GenerateROFTTopo(
            gpu_count=256,
            gpus_per_server=8,
            gpu_type="H100",
            asw_port=64,
            alpha=0.5,
            psw_port=64,
            beta=1.0,
            nic_bw="400Gbps",
            asw_to_psw_bw="400Gbps",
        )
    elif choice == "8":
        # 示例：n=16, k=2 → 256 GPU；须满足 n % gpus_per_server == 0
        GenerateZcubeTopo(n=16, k=2, gpus_per_server=8, gpu_type="H100")
    else:
        print("无效选项")
