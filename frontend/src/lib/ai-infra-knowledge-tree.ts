export type AiInfraMetric = {
  label: string;
  value: string;
  scope?: string;
  source?: string;
  caution?: string;
};

export type AiInfraPlayerGroup = {
  group: string;
  names: string[];
  note?: string;
};

export type AiInfraNode = {
  id: string;
  title: string;
  layer: string;
  summary: string;
  parentId?: string;
  role?: string;
  logic?: string[];
  players?: AiInfraPlayerGroup[];
  metrics?: AiInfraMetric[];
  investmentKeys?: string[];
  risks?: string[];
  trackingIndicators?: string[];
  relatedTerms?: string[];
  upstream?: string[];
  downstream?: string[];
  sourceNotes?: string[];
  children?: AiInfraNode[];
};

export type AiInfraFlatNode = AiInfraNode & {
  depth: number;
  path: string[];
  rootId: string;
  childCount: number;
};

export const AI_INFRA_VERSION = "AI算力基础设施产业链知识树 v1.0";

export const AI_INFRA_CORE_FIELDS = [
  "产业节点",
  "上游原材料",
  "核心技术壁垒",
  "全球龙头",
  "中国映射",
  "市场份额",
  "客户结构",
  "受益逻辑",
  "风险因素",
  "关键跟踪指标",
  "相关股票",
  "证据来源",
  "更新时间"
];

export const AI_INFRA_MAIN_VARIABLES = [
  {
    title: "NVIDIA平台迭代",
    summary: "H100 -> H200 -> GB200 -> GB300 -> Rubin；每代升级都会拉动 HBM、CoWoS、PCB、光模块、铜互联、液冷和电力。"
  },
  {
    title: "云厂商Capex",
    summary: "重点跟踪 Microsoft、Amazon、Google、Meta、Oracle、CoreWeave、Nebius 的资本开支和机柜交付节奏。"
  },
  {
    title: "HBM与CoWoS瓶颈",
    summary: "GPU再强，没有 HBM 与 CoWoS 也难以出货，先进封装和客户认证是供给约束。"
  },
  {
    title: "Scale-up与Scale-out",
    summary: "机柜内看 NVLink、铜互联、NVSwitch；机柜外看光模块、交换机、InfiniBand 与以太网。"
  },
  {
    title: "推理带来的ASIC机会",
    summary: "训练看 GPU，推理看 ASIC、CPU 调度和低成本 Token。"
  },
  {
    title: "液冷和电力",
    summary: "AI数据中心不只是买 GPU，最终瓶颈可能是电力接入、液冷工程和交付周期。"
  },
  {
    title: "中国国产替代",
    summary: "AI芯片、存储、PCB、光模块、服务器、EDA、半导体设备都有国产替代映射，但要区分真实供货和主题交易。"
  }
];

export const AI_INFRA_TREE: AiInfraNode[] = [
  {
    id: "demand",
    title: "需求端：谁在花钱",
    layer: "需求端",
    summary: "云厂商、大模型公司和算力租赁商是AI算力基础设施的资本开支源头。",
    logic: ["模型越大 -> 训练越贵 -> 推理调用越多 -> 云厂商Capex越高 -> GPU/HBM/光模块/液冷/电力需求越大。"],
    players: [
      { group: "美国云巨头", names: ["Microsoft", "Amazon", "Google", "Meta", "Oracle"], note: "最大Capex来源，买GPU并建设数据中心。" },
      { group: "AI模型公司", names: ["OpenAI", "Anthropic", "xAI", "Perplexity", "Mistral"], note: "训练和推理需求源头。" },
      { group: "算力租赁商", names: ["CoreWeave", "Nebius", "Lambda"], note: "帮模型公司租GPU、建AI云。" },
      { group: "中国云厂商", names: ["阿里云", "腾讯云", "华为云", "火山引擎", "百度智能云"], note: "国内算力需求源头。" },
      { group: "国内大模型公司", names: ["智谱", "月之暗面", "MiniMax", "百川", "DeepSeek"], note: "国内训练和推理需求源头。" }
    ],
    metrics: [
      { label: "AI服务器出货", value: "2025年同比增长超过20%", source: "TrendForce", scope: "全球AI服务器出货预测", caution: "高端AI服务器需求主要来自北美CSP和自研ASIC/GPU平台。" }
    ],
    investmentKeys: ["先看Capex预算，再看订单转换和交付节奏。", "需求端变化会传导到GPU、HBM、网络、散热和电力。"],
    risks: ["Capex放缓", "模型训练效率提升导致单位算力需求下降", "云厂商自研芯片压低外采比例"],
    trackingIndicators: ["CSP资本开支指引", "GPU集群建设计划", "推理Token成本", "AI服务器订单"],
    relatedTerms: ["AI算力", "云厂商Capex", "AI服务器", "大模型", "推理"],
    children: [
      {
        id: "training-demand",
        title: "训练需求",
        layer: "需求端",
        parentId: "demand",
        summary: "大模型训练推动GPU/AI加速卡、HBM、高速互联和超大规模GPU集群需求。",
        upstream: ["模型参数规模", "训练数据", "云厂商预算"],
        downstream: ["GPU / AI加速卡", "HBM", "NVLink / InfiniBand / 以太网", "超大规模GPU集群"],
        relatedTerms: ["训练", "GPU", "HBM", "NVLink", "InfiniBand"]
      },
      {
        id: "inference-demand",
        title: "推理需求",
        layer: "需求端",
        parentId: "demand",
        summary: "推理放量强调GPU、ASIC、CPU调度、KV Cache、低延迟网络和低成本Token。",
        upstream: ["用户调用", "Agent工作流", "应用侧负载"],
        downstream: ["GPU", "ASIC", "CPU调度", "KV Cache", "低延迟网络", "低成本Token"],
        relatedTerms: ["推理", "ASIC", "CPU", "KV Cache", "低成本Token"]
      }
    ]
  },
  {
    id: "ai-data-center",
    title: "AI数据中心",
    layer: "总图",
    summary: "AI数据中心把服务器、机柜、集群网络和基础设施组合成算力工厂，是需求端向硬件和工程交付落地的主容器。",
    logic: ["AI大模型训练和推理需求最终落到AI数据中心的服务器、机柜、集群网络、电力、冷却、土地、水资源、审批和电网接入。"],
    investmentKeys: ["不要只看单个零部件，要看整柜、整网、整站交付。", "AI数据中心瓶颈可能从GPU切换到电力、冷却、审批和并网。"],
    risks: ["电力接入不足", "审批周期拉长", "水资源和土地约束", "整站交付延期"],
    trackingIndicators: ["数据中心开工", "机柜功率密度", "电网接入", "PUE", "水资源约束", "审批进度"],
    relatedTerms: ["AI数据中心", "AI服务器", "机柜", "集群网络", "电力", "液冷"],
    children: [
      {
        id: "datacenter-server-stack",
        title: "服务器",
        layer: "AI数据中心",
        parentId: "ai-data-center",
        summary: "AI服务器内部包括GPU/ASIC、CPU、HBM、DDR5、SSD、DPU/NIC、PCB/HDI/高多层板以及服务器整机/ODM/OEM。",
        downstream: ["GPU / ASIC", "CPU", "HBM", "DDR5", "SSD", "DPU / NIC", "PCB / HDI / 高多层板", "服务器整机 / ODM / OEM"],
        relatedTerms: ["AI服务器", "GPU", "ASIC", "CPU", "HBM", "DDR5", "SSD", "DPU", "NIC", "PCB"]
      },
      {
        id: "datacenter-rack-stack",
        title: "机柜",
        layer: "AI数据中心",
        parentId: "ai-data-center",
        summary: "AI机柜把GPU节点组织成rack-scale系统，核心环节包括NVLink、NVSwitch、铜互联、连接器、液冷和高功率供电。",
        downstream: ["NVLink", "NVSwitch", "铜互联", "连接器", "液冷", "高功率供电"],
        relatedTerms: ["机柜", "NVLink", "NVSwitch", "铜互联", "连接器", "液冷", "高功率供电"]
      },
      {
        id: "datacenter-cluster-network-stack",
        title: "集群网络",
        layer: "AI数据中心",
        parentId: "ai-data-center",
        summary: "集群网络连接机柜和交换机，核心环节包括光模块、光纤、交换机、InfiniBand、以太网、CPO和硅光。",
        downstream: ["光模块", "光纤", "交换机", "InfiniBand", "以太网", "CPO / 硅光"],
        relatedTerms: ["集群网络", "光模块", "光纤", "交换机", "InfiniBand", "以太网", "CPO", "硅光"]
      },
      {
        id: "datacenter-infra-stack",
        title: "数据中心基础设施",
        layer: "AI数据中心",
        parentId: "ai-data-center",
        summary: "数据中心基础设施包括电力、UPS、变压器、储能、冷却、土地、水资源、审批和电网接入。",
        downstream: ["电力", "UPS", "变压器", "储能", "冷却", "土地", "水资源", "审批 / 电网接入"],
        relatedTerms: ["数据中心基础设施", "电力", "UPS", "变压器", "储能", "冷却", "土地", "水资源", "审批", "电网接入"]
      }
    ]
  },
  {
    id: "compute-chip",
    title: "算力芯片",
    layer: "第一主链",
    summary: "GPU、ASIC和服务器CPU共同构成AI训练和推理的计算底座。",
    relatedTerms: ["GPU", "AI加速卡", "ASIC", "CPU", "昇腾", "NVIDIA"],
    children: [
      {
        id: "gpu-accelerator",
        title: "GPU / AI Accelerator",
        layer: "算力芯片",
        parentId: "compute-chip",
        summary: "负责大模型训练和推理的矩阵计算，是训练端最强主链。",
        players: [
          { group: "全球龙头", names: ["NVIDIA"], note: "数据中心GPU和AI训练市场长期占据80%-90%级别优势；Bloomberg Intelligence预计2030年前仍可能维持AI加速器70%-75%份额。" },
          { group: "第二供应源", names: ["AMD"], note: "MI300/MI325/MI350/MI400系列，主要作为NVIDIA替代和第二供应源。" },
          { group: "边缘化路线", names: ["Intel Gaudi"], note: "Gaudi路线受挫，但数据中心CPU仍有价值。" },
          { group: "ASIC与互联强者", names: ["Broadcom", "Marvell"], note: "Google TPU、Meta、AWS、Microsoft定制芯片及互联方案。" },
          { group: "云厂商自研", names: ["Google TPU", "AWS Trainium", "AWS Inferentia", "Microsoft Maia", "Meta MTIA"], note: "自用为主，服务训练、推理和降本。" },
          { group: "中国映射", names: ["华为昇腾", "阿里平头哥", "百度昆仑芯", "寒武纪", "海光信息", "摩尔线程", "壁仞", "沐曦", "燧原"], note: "国产GPU/AI芯片替代力量。" }
        ],
        metrics: [
          { label: "全球AI训练市场", value: "NVIDIA长期80%-90%级别优势", scope: "数据中心GPU/AI训练", caution: "份额口径可能是收入、出货或训练市场。" },
          { label: "2030年前AI加速器", value: "NVIDIA可能维持70%-75%", source: "Bloomberg Intelligence", scope: "AI加速器市场预期" },
          { label: "中国AI加速卡", value: "NVIDIA约55%，AMD约4%，中国厂商合计约41%", source: "IDC数据经Reuters报道", scope: "2025年中国AI加速卡市场", caution: "中国市场口径；华为约812,000张，约占国产厂商出货一半。" }
        ],
        investmentKeys: ["看训练：NVIDIA壁垒最强。", "看推理：ASIC替代空间更大。", "看中国：国产替代空间大，但性能和生态仍追赶。"],
        risks: ["出口管制", "云厂商自研ASIC替代", "供给受HBM/CoWoS约束", "估值透支"],
        trackingIndicators: ["H100/H200/GB200/GB300/Rubin迭代", "MI300/MI350出货", "昇腾生态订单", "GPU利用率", "客户认证"],
        relatedTerms: ["NVIDIA", "GPU", "AI芯片", "昇腾", "寒武纪", "AI加速卡"]
      },
      {
        id: "asic",
        title: "ASIC定制芯片",
        layer: "算力芯片",
        parentId: "compute-chip",
        summary: "针对特定AI任务优化，牺牲通用性换取更低成本和更高能效。",
        players: [
          { group: "设计服务/ASIC平台", names: ["Broadcom"], note: "Google TPU、Meta、自研AI ASIC核心受益者。" },
          { group: "设计服务/互联", names: ["Marvell"], note: "AWS、Microsoft等客户，AI ASIC + SerDes + 互联相关方案。" },
          { group: "云厂商自研", names: ["Google", "AWS", "Microsoft", "Meta"], note: "自用为主，不一定外售。" },
          { group: "中国映射", names: ["阿里平头哥", "百度昆仑芯", "华为昇腾"], note: "国内云厂商自研或生态自用。" }
        ],
        metrics: [
          { label: "AI Server Compute ASIC", value: "到2027年出货量较当前大幅增长", source: "Counterpoint", scope: "AI服务器计算ASIC" },
          { label: "设计伙伴份额", value: "Broadcom 2027年约60%", source: "Counterpoint", scope: "AI ASIC设计伙伴预期" }
        ],
        investmentKeys: ["训练端GPU仍强。", "推理端ASIC性价比更强。", "云厂商越想降本，ASIC越重要。"],
        risks: ["客户集中", "设计周期长", "生态兼容风险", "外售空间有限"],
        trackingIndicators: ["云厂商ASIC量产节点", "SerDes/互联配套", "推理成本下降", "客户Capex结构"],
        relatedTerms: ["ASIC", "TPU", "Trainium", "Inferentia", "Maia", "MTIA", "Broadcom", "Marvell"]
      },
      {
        id: "server-cpu",
        title: "服务器CPU",
        layer: "算力芯片",
        parentId: "compute-chip",
        summary: "AI系统里CPU负责任务调度、数据预处理、工具调用、Agent执行、系统管理和GPU/ASIC资源调度。",
        players: [
          { group: "传统龙头", names: ["Intel Xeon"], note: "服务器CPU单位份额仍高。" },
          { group: "快速追赶", names: ["AMD EPYC"], note: "Mercury Research口径下，Q4 2025服务器CPU收入份额41.3%，单位份额约28.8%。" },
          { group: "ARM架构", names: ["AWS Graviton", "Google Axion", "Microsoft Cobalt", "NVIDIA Grace"], note: "云厂商降本和AI机柜生态的重要方向。" },
          { group: "中国映射", names: ["鲲鹏", "海光", "飞腾", "兆芯"], note: "国产服务器CPU路线。" }
        ],
        metrics: [
          { label: "AMD服务器CPU收入份额", value: "41.3%", source: "Mercury Research", scope: "Q4 2025服务器CPU收入口径" },
          { label: "AMD服务器CPU单位份额", value: "约28.8%", source: "Mercury Research", scope: "Q4 2025单位口径" },
          { label: "服务器CPU市场", value: "2030年可能达到1200亿美元", source: "AMD管理层预期", caution: "增长预期从约18%年增速上调到35%以上，驱动包括AI和Agentic AI工作负载。" }
        ],
        investmentKeys: ["GPU负责算，CPU负责调度。", "Agent越复杂，CPU越重要。", "ARM越强，Intel压力越大。"],
        risks: ["云厂商自研替代", "单位价格下降", "GPU直连体系改变CPU价值量"],
        trackingIndicators: ["Agent工作负载增长", "Grace/Graviton/Cobalt/Axion采用", "AMD服务器收入份额", "Intel数据中心恢复"],
        relatedTerms: ["CPU", "Agent", "EPYC", "Xeon", "Grace", "ARM服务器"]
      }
    ]
  },
  {
    id: "memory-storage",
    title: "存储系统",
    layer: "第三主链",
    summary: "HBM、DDR5和企业级SSD共同决定AI训练、推理和数据湖的吞吐效率。",
    relatedTerms: ["HBM", "DDR5", "SSD", "DRAM", "NAND", "长鑫存储", "长江存储"],
    children: [
      {
        id: "hbm",
        title: "HBM",
        layer: "存储系统",
        parentId: "memory-storage",
        summary: "GPU旁边的高速数据搬运工，解决内存墙，是DRAM工艺、TSV、先进封装和客户认证的综合能力。",
        players: [
          { group: "全球三巨头", names: ["SK hynix", "Samsung", "Micron"], note: "HBM市场高度集中。" },
          { group: "中国映射", names: ["长鑫存储"], note: "国产HBM希望，主要服务国内生态。" }
        ],
        metrics: [
          { label: "Q3 2025 HBM份额", value: "SK hynix约53%、Samsung约35%、Micron约11%", source: "Reuters引述数据", caution: "单季度份额会因客户认证和出货节奏波动。" },
          { label: "另一口径", value: "SK hynix约57%、Samsung约22%、Micron约21%", source: "韩国媒体/Counterpoint相关报道", caution: "说明三巨头垄断确定，但精确份额需核验口径。" }
        ],
        investmentKeys: ["HBM不是普通内存。", "谁能供NVIDIA/AMD/Google，谁就有定价权。"],
        risks: ["客户认证失败", "产能扩张导致价格周期反转", "先进封装瓶颈"],
        trackingIndicators: ["HBM3E/HBM4认证", "NVIDIA/AMD供货份额", "TSV良率", "价格和产能"],
        relatedTerms: ["HBM", "HBM3E", "HBM4", "内存墙", "SK hynix", "Micron"]
      },
      {
        id: "ddr5",
        title: "DDR5 / 服务器内存",
        layer: "存储系统",
        parentId: "memory-storage",
        summary: "CPU与SSD之间的高速中转站，受AI服务器内存容量和HBM挤占产能影响。",
        players: [
          { group: "全球", names: ["Samsung", "SK hynix", "Micron"] },
          { group: "中国", names: ["长鑫存储"] }
        ],
        metrics: [
          { label: "DRAM收入份额", value: "SK hynix一度在Q3 2025以35%收入份额领先", source: "Counterpoint", scope: "2025年前三季度DRAM整体市场" }
        ],
        investmentKeys: ["HBM挤占DRAM产能 -> DDR5供给紧张 -> AI服务器内存成本上升 -> 存储周期强化。"],
        risks: ["存储周期下行", "普通DRAM与HBM逻辑混淆", "库存收益被误认为技术壁垒"],
        trackingIndicators: ["DDR5价格", "服务器内存容量", "HBM产能挤占", "DRAM厂商Capex"],
        relatedTerms: ["DDR5", "DRAM", "服务器内存", "存储周期"]
      },
      {
        id: "enterprise-ssd",
        title: "企业级SSD / eSSD",
        layer: "存储系统",
        parentId: "memory-storage",
        summary: "AI数据中心的数据仓库，承载训练数据、向量数据库、知识库、Checkpoint、模型权重、日志与缓存。",
        players: [
          { group: "NAND原厂", names: ["Samsung", "SK hynix/Solidigm", "Kioxia", "Western Digital", "Micron", "长江存储"] },
          { group: "企业级SSD模组", names: ["Samsung", "Solidigm", "Micron", "Kioxia", "Western Digital", "大普微", "忆恒创源", "江波龙", "佰维存储", "华为存储生态"] }
        ],
        investmentKeys: ["不要只看存储涨价，要看企业级主控、固件算法、云厂商核心机柜进入情况，以及是库存收益还是真实技术壁垒。"],
        risks: ["消费级存储周期误配", "主控和固件短板", "云厂商认证不足"],
        trackingIndicators: ["企业级主控", "固件算法", "云厂商核心机柜认证", "eSSD价格"],
        relatedTerms: ["eSSD", "企业级SSD", "NAND", "向量数据库", "Checkpoint"]
      }
    ]
  },
  {
    id: "server-odm",
    title: "服务器整机 / ODM / OEM",
    layer: "第四主链",
    summary: "把GPU、CPU、HBM、SSD、网卡、PCB、电源和散热组装成AI服务器或AI机柜。",
    players: [
      { group: "全球OEM", names: ["Dell", "HPE", "Supermicro", "Lenovo", "Inspur/浪潮"] },
      { group: "ODM", names: ["Foxconn/工业富联", "Quanta/广达", "Wistron/纬创", "Inventec/英业达", "Wiwynn"] },
      { group: "中国", names: ["工业富联", "浪潮信息", "华为", "新华三", "紫光股份"] }
    ],
    metrics: [
      { label: "2024 AI服务器OEM份额", value: "Dell 20%、HPE 15%、浪潮12%、Lenovo 11%、Supermicro 9%、其他33%", source: "ABI Research", scope: "AI服务器OEM市场" },
      { label: "台湾厂商出货", value: "约80%全球服务器出货、超过90%AI服务器出货", source: "Reuters", caution: "出货口径，不等同利润份额。" },
      { label: "Foxconn收入结构", value: "2025Q2 AI服务器和数据中心网络设备收入首次超过消费电子，占收入约41%", source: "Reuters" }
    ],
    investmentKeys: ["整机厂价值量大，但毛利率通常不如芯片、HBM、光模块。", "要看客户绑定和是否参与整柜级设计。"],
    risks: ["毛利率低", "客户集中", "缺少系统设计能力", "交付节奏波动"],
    trackingIndicators: ["NVIDIA机柜订单", "整柜级设计参与", "北美CSP客户占比", "AI服务器收入占比"],
    relatedTerms: ["AI服务器", "ODM", "OEM", "工业富联", "浪潮信息", "Supermicro"]
  },
  {
    id: "pcb",
    title: "PCB / HDI / 高速材料",
    layer: "第五主链",
    summary: "AI服务器升级要求更高层数、更低损耗材料、更高可靠性、更强散热、更复杂HDI和高速信号完整性。",
    players: [
      { group: "全球/海外", names: ["TTM Technologies", "Ibiden", "Unimicron", "Tripod", "Gold Circuit", "Nippon Mektron", "Samsung Electro-Mechanics", "AT&S"] },
      { group: "中国/A股", names: ["胜宏科技", "沪电股份", "深南电路", "生益电子", "景旺电子", "鹏鼎控股", "崇达技术"] },
      { group: "高速材料", names: ["生益科技", "Panasonic", "Rogers", "Isola"] }
    ],
    metrics: [
      { label: "AI/HPC PCB份额", value: "胜宏科技2025H1约13.8%，全球第一", source: "Frost & Sullivan", scope: "全球AI与HPC PCB市场" }
    ],
    investmentKeys: ["AI服务器PCB不等于普通PCB。", "真正看高多层板、HDI、高速材料、英伟达/AMD/云厂商供应链、交换机PCB和光模块PCB。"],
    risks: ["价格竞争", "材料认证失败", "客户集中", "普通PCB逻辑误判"],
    trackingIndicators: ["高多层板占比", "HDI能力", "高速材料认证", "交换机PCB订单", "光模块PCB订单"],
    relatedTerms: ["PCB", "HDI", "高多层板", "高速材料", "胜宏科技", "沪电股份", "深南电路"]
  },
  {
    id: "scale-up",
    title: "机柜内互联 / Scale-up",
    layer: "第六主链",
    summary: "让多张GPU像一个大GPU一样工作，短距离高速连接和机柜内部通信价值量提升。",
    children: [
      {
        id: "nvlink-nvswitch",
        title: "NVLink / NVSwitch",
        layer: "Scale-up",
        parentId: "scale-up",
        summary: "NVIDIA通过GB200/GB300 NVL72，把72张GPU放进rack-scale NVLink域，推动其从GPU供应商变成系统级AI基础设施供应商。",
        players: [
          { group: "核心生态", names: ["NVIDIA NVLink", "NVIDIA NVSwitch", "NVIDIA/Mellanox InfiniBand"] },
          { group: "NVLink Fusion生态", names: ["NVIDIA", "Marvell", "Broadcom", "MediaTek"] },
          { group: "UALink联盟", names: ["AMD", "Intel", "Broadcom", "Microsoft", "Meta"] }
        ],
        investmentKeys: ["训练集群越大，机柜内互联越关键。", "观察封闭高性能网络与开放互联联盟的份额变化。"],
        risks: ["开放标准替代", "NVIDIA系统绑定弱化", "机柜设计变化"],
        trackingIndicators: ["GB200/GB300 NVL72交付", "NVSwitch用量", "UALink生态进展", "NVLink Fusion伙伴"],
        relatedTerms: ["NVLink", "NVSwitch", "GB200", "GB300", "UALink"]
      },
      {
        id: "copper-connector",
        title: "铜互联 / 连接器",
        layer: "Scale-up",
        parentId: "scale-up",
        summary: "机柜内部短距离高速连接，铜互联增强并不等于光模块被替代，而是机柜内外分工变化。",
        players: [
          { group: "全球", names: ["Amphenol", "TE Connectivity", "Molex", "Credo", "Astera Labs", "Marvell"] },
          { group: "中国映射", names: ["立讯精密", "沃尔核材", "鼎通科技", "瑞可达", "华丰科技", "意华股份"] }
        ],
        investmentKeys: ["机柜内部铜互联增强。", "机柜外部光模块继续升级。", "关键是连接器、线缆、Retimer/SerDes和客户认证。"],
        risks: ["规格变化", "客户认证不及预期", "铜光路线争议"],
        trackingIndicators: ["高速铜缆订单", "连接器认证", "Retimer/SerDes需求", "机柜功率密度"],
        relatedTerms: ["铜互联", "连接器", "高速线缆", "SerDes", "立讯精密", "沃尔核材"]
      }
    ],
    relatedTerms: ["Scale-up", "NVLink", "铜互联", "连接器"]
  },
  {
    id: "scale-out",
    title: "集群网络 / Scale-out",
    layer: "第七主链",
    summary: "连接机柜、GPU集群和数据中心内部网络，训练网络从InfiniBand向以太网扩展。",
    children: [
      {
        id: "switching",
        title: "交换机",
        layer: "Scale-out",
        parentId: "scale-out",
        summary: "连接机柜、GPU集群和数据中心内部网络，AI以太网规模提升。",
        players: [
          { group: "InfiniBand交换机", names: ["NVIDIA/Mellanox"] },
          { group: "AI以太网交换机", names: ["Arista", "NVIDIA", "Cisco", "Celestica", "Accton"] },
          { group: "交换芯片", names: ["Broadcom", "NVIDIA", "Marvell"] },
          { group: "中国网络设备", names: ["华为", "新华三", "锐捷网络", "中兴通讯"] }
        ],
        metrics: [
          { label: "AI Scale-out网络", value: "2025年以太网规模已经超过InfiniBand两倍", source: "Dell'Oro", scope: "AI Scale-out网络" },
          { label: "AI后端以太网", value: "Celestica和NVIDIA合计约50%，Arista第三", source: "Dell'Oro", scope: "2025年AI后端以太网市场" },
          { label: "数据中心以太网交换机", value: "Arista Q4 2025约19%；总以太网约12.6%，Huawei总以太网约10.6%", source: "IDC", scope: "Q4 2025份额口径" }
        ],
        investmentKeys: ["训练网络原来偏InfiniBand，未来以太网占比提升。", "Broadcom吃开放以太网红利，NVIDIA吃封闭高性能网络红利。"],
        risks: ["协议路线切换", "交换机白盒化压低利润", "客户集中"],
        trackingIndicators: ["以太网后端网络订单", "交换芯片出货", "InfiniBand/以太网比例", "RoCE部署"],
        relatedTerms: ["交换机", "InfiniBand", "以太网", "Broadcom", "Arista", "Mellanox"]
      }
    ],
    relatedTerms: ["Scale-out", "交换机", "InfiniBand", "以太网"]
  },
  {
    id: "optical",
    title: "光通信",
    layer: "第七主链",
    summary: "光模块、光器件、CPO和硅光支撑机柜间、交换机间高速传输。",
    children: [
      {
        id: "optical-module",
        title: "光模块",
        layer: "光通信",
        parentId: "optical",
        summary: "把电信号转换成光信号，实现机柜间和交换机间高速传输，速率沿100G、200G、400G、800G、1.6T、3.2T升级。",
        players: [
          { group: "全球", names: ["Coherent", "Lumentum", "Broadcom", "Innolight", "Eoptolink", "Accelink", "Source Photonics", "Fabrinet"] },
          { group: "中国/A股", names: ["中际旭创", "新易盛", "天孚通信", "光迅科技", "华工科技", "太辰光", "剑桥科技"] }
        ],
        metrics: [
          { label: "全球光收发器销售额", value: "2025年238亿美元", source: "LightCounting", scope: "全球光收发器" },
          { label: "中际旭创收入", value: "2025Q4收入18.7亿美元，同比增长105%", source: "LightCounting引用口径", caution: "需核验公司财报和币种口径。" },
          { label: "Coherent数据中心和通信收入", value: "2025Q4达到12亿美元", source: "LightCounting引用口径" },
          { label: "新易盛收入", value: "2025Q4预计超过10亿美元", source: "LightCounting引用口径" },
          { label: "五大供应商", value: "Coherent、Lumentum、Broadcom、光迅科技、Innolight合计约50%", source: "Mordor Intelligence", scope: "2025年全球光收发器收入口径" }
        ],
        investmentKeys: ["最重要不是光模块三个字，而是800G出货、1.6T验证、硅光能力、LPO/CPO路线、海外大客户认证和毛利率是否被压缩。"],
        risks: ["价格战", "客户集中", "CPO替代", "技术路线切换", "毛利率下行"],
        trackingIndicators: ["800G出货", "1.6T验证", "硅光能力", "LPO/CPO路线", "海外大客户占比", "毛利率"],
        relatedTerms: ["光模块", "800G", "1.6T", "硅光", "中际旭创", "新易盛", "天孚通信"]
      },
      {
        id: "cpo-silicon-photonics",
        title: "CPO / 硅光",
        layer: "光通信",
        parentId: "optical",
        summary: "降低高速光互联功耗，把光电转换更靠近交换芯片。",
        players: [
          { group: "CPO/交换芯片", names: ["Broadcom", "NVIDIA", "Marvell"] },
          { group: "硅光平台", names: ["TSMC", "Intel", "GlobalFoundries", "STMicroelectronics"] },
          { group: "光器件", names: ["Coherent", "Lumentum", "II-VI", "天孚通信", "太辰光"] },
          { group: "模块厂", names: ["中际旭创", "新易盛", "光迅科技"] }
        ],
        metrics: [
          { label: "CPO市场", value: "2024年约4600万美元 -> 2030年约81亿美元", source: "Yole", caution: "NVIDIA硅光/CPO路线是重要驱动。" }
        ],
        investmentKeys: ["CPO和硅光是功耗约束下的长期路线，但节奏要看交换芯片平台和大客户验证。"],
        risks: ["商用节奏慢", "传统可插拔路线延寿", "封装和良率风险"],
        trackingIndicators: ["CPO样机", "交换芯片平台", "硅光良率", "客户验证"],
        relatedTerms: ["CPO", "硅光", "LPO", "Broadcom", "NVIDIA", "Marvell"]
      }
    ],
    relatedTerms: ["光模块", "光通信", "CPO", "硅光"]
  },
  {
    id: "cooling",
    title: "液冷 / 散热",
    layer: "第八主链",
    summary: "AI机柜功率密度快速上升后，风冷不够用，液冷变成刚需。",
    players: [
      { group: "全球", names: ["Vertiv", "Schneider Electric", "CoolIT", "Boyd", "Rittal", "Stulz", "Johnson Controls"] },
      { group: "中国/A股", names: ["英维克", "高澜股份", "申菱环境", "同飞股份", "佳力图", "飞荣达", "科创新源"] }
    ],
    metrics: [
      { label: "数据中心液冷份额", value: "Vertiv 2025年超过11.3%，前五合计约35%", source: "GMI", scope: "数据中心液冷市场" },
      { label: "液冷市场规模", value: "2025年约66.5亿美元，2033年294.6亿美元，2026-2033 CAGR约20.1%", source: "Grand View Research", scope: "全球数据中心液冷" }
    ],
    investmentKeys: ["液冷不是概念，要看是否进入北美CSP/英伟达生态，是否有CDU/冷板/快接头完整方案，是否具备工程交付和运维能力。"],
    risks: ["样机多但量产少", "工程交付能力不足", "漏液和可靠性", "客户认证周期长"],
    trackingIndicators: ["冷板液冷", "浸没式液冷", "后门换热", "CDU", "快接头/管路", "北美CSP订单"],
    relatedTerms: ["液冷", "CDU", "冷板", "浸没式液冷", "英维克", "高澜股份"]
  },
  {
    id: "power",
    title: "电力系统",
    layer: "第九主链",
    summary: "给AI数据中心供电、稳压、备电和配电，产业链包括电网接入、高压变压器、中低压配电、UPS、PDU、机柜电源、储能/柴油发电和能源管理系统。",
    players: [
      { group: "电力管理", names: ["Schneider Electric", "Eaton", "ABB", "Siemens", "许继电气", "国电南瑞", "特变电工"] },
      { group: "UPS", names: ["Schneider", "Eaton", "Vertiv", "Huawei", "ABB", "科华数据", "科士达", "易事特"] },
      { group: "配电/PDU", names: ["Schneider", "Vertiv", "Eaton", "Legrand", "良信股份", "公牛集团", "科华数据"] },
      { group: "变压器", names: ["ABB", "Siemens", "Hitachi Energy", "金盘科技", "伊戈尔", "特变电工", "明阳电气"] },
      { group: "储能", names: ["Tesla Energy", "Fluence", "CATL", "BYD", "宁德时代", "阳光电源", "比亚迪", "科陆电子"] },
      { group: "柴油/燃气发电", names: ["Caterpillar", "Cummins", "Rolls-Royce", "潍柴动力", "玉柴国际"] }
    ],
    metrics: [
      { label: "数据中心UPS", value: "Schneider Electric、Vertiv、Eaton、Huawei、ABB合计约40%-42%", source: "MarketsandMarkets", scope: "2025年UPS市场" },
      { label: "数据中心电力市场", value: "2025年351.4亿美元 -> 2030年505.1亿美元，CAGR约7.5%", source: "MarketsandMarkets", scope: "全球数据中心电力市场" }
    ],
    investmentKeys: ["AI数据中心最后拼的是电。", "GPU买得到不代表电网接得上。", "电力设备交付周期可能比GPU更硬。"],
    risks: ["审批延迟", "电网接入不足", "设备交付周期", "能源价格和环保约束"],
    trackingIndicators: ["电网接入", "变压器订单", "UPS订单", "PDU", "储能配置", "PUE"],
    relatedTerms: ["电力", "UPS", "PDU", "变压器", "储能", "数据中心电力"]
  },
  {
    id: "tax-collectors",
    title: "底层收税人",
    layer: "第十主链",
    summary: "EDA、IP、晶圆代工、先进封装、半导体设备和材料构成AI芯片扩张的底层约束与收费环节。",
    children: [
      {
        id: "eda",
        title: "EDA",
        layer: "底层收税人",
        parentId: "tax-collectors",
        summary: "芯片设计工具，云厂商越自研ASIC，EDA越受益。",
        players: [
          { group: "全球", names: ["Synopsys", "Cadence", "Siemens EDA", "Ansys", "Keysight", "Altium", "Silvaco"] },
          { group: "中国映射", names: ["华大九天", "概伦电子", "广立微", "芯和半导体", "国微集团"] }
        ],
        metrics: [
          { label: "全球EDA市场", value: "Synopsys约31%、Cadence约30%、Siemens EDA约13%", source: "TrendForce", scope: "2024年全球EDA市场" }
        ],
        investmentKeys: ["云厂商越自研ASIC，EDA越受益。", "中国EDA受出口管制影响大。"],
        risks: ["出口管制", "国产替代难度高", "客户验证周期长"],
        trackingIndicators: ["ASIC设计数量", "云厂商自研芯片", "国产EDA验证", "出口限制"],
        relatedTerms: ["EDA", "Synopsys", "Cadence", "华大九天"]
      },
      {
        id: "ip",
        title: "IP",
        layer: "底层收税人",
        parentId: "tax-collectors",
        summary: "给芯片提供可复用模块，包括CPU IP、GPU IP、SerDes、PCIe、CXL、DDR控制器、HBM控制器、UCIe、以太网MAC/PHY和安全模块。",
        players: [
          { group: "全球", names: ["ARM", "Synopsys IP", "Cadence IP", "Rambus", "Alphawave Semi"] },
          { group: "中国映射", names: ["芯原股份", "和芯星通等细分IP企业"] }
        ],
        investmentKeys: ["ARM Neoverse CSS降低云厂商自研CPU门槛，支撑AWS、Microsoft、Google、NVIDIA等ARM服务器CPU生态。"],
        risks: ["授权模式变化", "客户自研替代", "出口限制"],
        trackingIndicators: ["ARM服务器渗透", "CXL/UCIe/HBM控制器需求", "SerDes速率升级"],
        relatedTerms: ["IP", "ARM", "SerDes", "CXL", "UCIe", "HBM控制器"]
      },
      {
        id: "foundry",
        title: "晶圆代工",
        layer: "底层收税人",
        parentId: "tax-collectors",
        summary: "把GPU、ASIC、CPU从设计图做成芯片，AI高端芯片等于TSMC先进制程、CoWoS和HBM的组合。",
        players: [
          { group: "全球", names: ["TSMC", "Samsung Foundry", "SMIC", "UMC", "GlobalFoundries", "Intel Foundry"] }
        ],
        metrics: [
          { label: "纯晶圆代工份额", value: "TSMC Q4 2025约70.4%，Samsung Foundry约7.1%", source: "TrendForce", scope: "全球纯晶圆代工" },
          { label: "SMIC份额", value: "Q4 2025约5.3%", source: "Counterpoint", scope: "全球晶圆代工" }
        ],
        investmentKeys: ["先进制程不能单独看，必须和封装一起看。"],
        risks: ["地缘政治", "先进制程产能", "客户集中", "出口管制"],
        trackingIndicators: ["N3/N2产能", "CoWoS配套", "AI客户投片", "SMIC成熟制程景气"],
        relatedTerms: ["晶圆代工", "TSMC", "CoWoS", "SMIC", "先进制程"]
      },
      {
        id: "advanced-packaging",
        title: "先进封装",
        layer: "底层收税人",
        parentId: "tax-collectors",
        summary: "把GPU/ASIC和HBM封在一起，关键技术包括CoWoS、SoIC、Foveros、EMIB、2.5D/3D封装和Hybrid Bonding。",
        players: [
          { group: "CoWoS", names: ["TSMC"], note: "AI GPU所需CoWoS环节是核心瓶颈。" },
          { group: "OSAT先进封装", names: ["ASE", "Amkor", "长电科技", "通富微电", "华天科技"] },
          { group: "Intel路线", names: ["Foveros", "EMIB"] },
          { group: "Samsung路线", names: ["I-Cube", "X-Cube"] },
          { group: "国内", names: ["长电科技", "通富微电", "华天科技", "甬矽电子"] }
        ],
        metrics: [
          { label: "先进封装总体份额", value: "ASE Technology 2025年约26.5%；前五ASE、Amkor、TSMC、长电科技、Intel合计约74.9%", source: "GMI", scope: "先进封装总体市场" },
          { label: "CoWoS产能", value: "TSMC计划到2027年将CoWoS产能扩大超过60%", source: "TrendForce", scope: "CoWoS产能计划" }
        ],
        investmentKeys: ["普通封测不等于AI先进封装。", "真正瓶颈是CoWoS、HBM堆叠、大尺寸中介层、良率和产能排队。"],
        risks: ["产能扩张节奏", "良率", "客户排队变化", "技术路线切换"],
        trackingIndicators: ["CoWoS产能", "HBM堆叠", "大尺寸中介层", "Hybrid Bonding", "良率"],
        relatedTerms: ["先进封装", "CoWoS", "HBM堆叠", "长电科技", "通富微电"]
      },
      {
        id: "semi-equipment",
        title: "半导体设备",
        layer: "底层收税人",
        parentId: "tax-collectors",
        summary: "给晶圆厂和封装厂提供光刻、薄膜沉积、刻蚀、量测检测、离子注入、清洗、涂胶显影和封装设备。",
        players: [
          { group: "光刻机", names: ["ASML", "Nikon", "Canon"] },
          { group: "薄膜沉积", names: ["Applied Materials", "Lam Research", "Tokyo Electron"] },
          { group: "刻蚀", names: ["Lam Research", "Tokyo Electron", "Applied Materials"] },
          { group: "量测检测", names: ["KLA"] },
          { group: "离子注入", names: ["Applied Materials", "Axcelis"] },
          { group: "清洗/涂胶显影", names: ["Screen", "Tokyo Electron"] },
          { group: "封装设备", names: ["ASMPT", "BESI", "Kulicke & Soffa", "DISCO"] },
          { group: "中国映射", names: ["中微公司", "北方华创", "拓荆科技", "盛美上海", "精测电子", "上海睿励", "万业企业/凯世通", "长川科技", "华峰测控", "芯碁微装"] }
        ],
        metrics: [
          { label: "WFE Big Five", value: "ASML、Applied Materials、Lam Research、Tokyo Electron、KLA在2024年合计接近70%", source: "Yole", scope: "WFE市场" },
          { label: "光刻设备", value: "ASML 2024年约94%，Canon和Nikon瓜分剩余约6%", source: "TrendForce", scope: "光刻设备市场" }
        ],
        investmentKeys: ["AI芯片扩产 -> TSMC/SK hynix/Samsung/Intel资本开支 -> 半导体设备订单。", "光刻、刻蚀、沉积、检测、先进封装设备受益。"],
        risks: ["出口管制", "资本开支周期", "国产替代验证慢", "订单节奏波动"],
        trackingIndicators: ["WFE Capex", "先进封装设备", "刻蚀/沉积订单", "量测检测需求"],
        relatedTerms: ["半导体设备", "ASML", "北方华创", "中微公司", "拓荆科技"]
      },
      {
        id: "semi-materials",
        title: "半导体材料",
        layer: "底层收税人",
        parentId: "tax-collectors",
        summary: "半导体材料是晶圆制造和先进封装的底层耗材与工艺约束，和设备、代工、封装共同决定AI芯片扩产弹性。",
        investmentKeys: ["AI芯片扩产不仅拉动设备，也会拉动高纯化学品、光刻胶、靶材、电子气体、封装基板和先进封装材料。"],
        risks: ["材料认证周期长", "国产替代难度高", "客户验证慢", "价格周期波动"],
        trackingIndicators: ["晶圆厂Capex", "先进封装材料", "HBM封装材料", "国产材料认证"],
        relatedTerms: ["半导体材料", "光刻胶", "电子气体", "靶材", "封装材料"]
      }
    ],
    relatedTerms: ["EDA", "IP", "晶圆代工", "先进封装", "半导体设备"]
  }
];

export function flattenAiInfraTree(tree: AiInfraNode[] = AI_INFRA_TREE): AiInfraFlatNode[] {
  const rows: AiInfraFlatNode[] = [];
  const walk = (node: AiInfraNode, depth: number, path: string[], rootId: string) => {
    rows.push({
      ...node,
      depth,
      path: [...path, node.title],
      rootId,
      childCount: node.children?.length ?? 0
    });
    for (const child of node.children ?? []) {
      walk(child, depth + 1, [...path, node.title], rootId);
    }
  };
  for (const node of tree) walk(node, 0, [], node.id);
  return rows;
}

export function findAiInfraNode(id: string, rows: AiInfraFlatNode[] = flattenAiInfraTree()): AiInfraFlatNode | null {
  return rows.find((node) => node.id === id) ?? null;
}
