from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

UNCLASSIFIED_INDUSTRIES = {"", "未分类", "未知", "未知行业", "N/A", "NA", "none", "None"}
MAPPING_VERSION = "industry_mapping_v1"


@dataclass(frozen=True)
class IndustryMappingRule:
    industry: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class IndustryMappingMatch:
    industry: str
    confidence: float
    reason: str
    matched_keywords: tuple[str, ...] = field(default_factory=tuple)
    evidence: tuple[dict[str, str], ...] = field(default_factory=tuple)


NAME_HINTS: dict[str, tuple[str, ...]] = {
    "AI算力": (
        "英伟达",
        "寒武纪",
        "中际旭创",
        "新易盛",
        "工业富联",
        "浪潮信息",
        "海光信息",
        "澜起科技",
        "NVIDIA",
        "Nvidia",
        "Advanced Micro Devices",
        "AMD",
        "Broadcom",
        "Marvell",
        "Super Micro",
        "SMCI",
    ),
    "机器人": ("三花智控", "绿的谐波", "埃斯顿", "汇川技术", "拓斯达", "机器人股份"),
    "低空经济": ("亿航智能", "EHang", "小鹏汇天", "万丰奥威", "中信海直"),
    "固态电池": ("宁德时代", "比亚迪", "亿纬锂能", "国轩高科", "QuantumScape", "Solid Power"),
    "半导体": (
        "台积电",
        "中芯国际",
        "北方华创",
        "中微公司",
        "韦尔股份",
        "兆易创新",
        "长电科技",
        "ASML",
        "应用材料",
        "Applied Materials",
        "LAM RESEARCH",
        "Lam Research",
        "高通",
        "QUALCOMM",
        "Qualcomm",
        "INTEL",
        "Intel",
        "Micron",
        "Texas Instruments",
        "Analog Devices",
    ),
    "消费电子": (
        "苹果",
        "Apple",
        "立讯精密",
        "歌尔股份",
        "京东方",
        "蓝思科技",
        "舜宇光学",
        "小米集团",
        "Sony",
        "Samsung",
    ),
    "软件服务": (
        "微软",
        "Microsoft",
        "甲骨文",
        "Oracle",
        "Salesforce",
        "Adobe",
        "ServiceNow",
        "SAP",
        "Snowflake",
        "用友网络",
        "金山办公",
        "金蝶国际",
        "中国软件",
        "恒生电子",
        "广联达",
    ),
    "网络安全": ("CrowdStrike", "Palo Alto Networks", "Fortinet", "Zscaler", "奇安信", "深信服", "启明星辰"),
    "互联网平台": (
        "阿里巴巴",
        "腾讯",
        "腾讯控股",
        "美团",
        "京东",
        "拼多多",
        "PDD",
        "Meta",
        "Amazon",
        "Alphabet",
        "Google",
        "Netflix",
        "网易",
        "百度",
        "快手",
    ),
    "新能源车": (
        "比亚迪",
        "特斯拉",
        "Tesla",
        "理想汽车",
        "小鹏汽车",
        "蔚来",
        "赛力斯",
        "长城汽车",
        "吉利汽车",
        "Rivian",
        "Lucid",
        "Li Auto",
        "NIO",
        "XPeng",
    ),
    "智能驾驶": ("Mobileye", "Aurora", "小马智行", "文远知行", "禾赛科技", "速腾聚创", "地平线机器人"),
    "汽车零部件": ("福耀玻璃", "拓普集团", "德赛西威", "华域汽车", "Aptiv", "Magna", "BorgWarner"),
    "储能": ("阳光电源", "派能科技", "固德威", "Enphase", "Fluence", "Tesla Energy"),
    "光伏": ("隆基绿能", "通威股份", "晶科能源", "天合光能", "First Solar", "SolarEdge", "Enphase"),
    "风电": ("金风科技", "明阳智能", "东方电缆", "Vestas", "Orsted"),
    "电力电网": ("长江电力", "国电电力", "华能国际", "华电国际", "中国电力", "National Grid", "NextEra", "Duke Energy"),
    "核电": ("中国核电", "中国广核", "中广核电力", "CGN Power", "Cameco", "Constellation Energy"),
    "创新药": (
        "百济神州",
        "恒瑞医药",
        "信达生物",
        "君实生物",
        "翰森制药",
        "康方生物",
        "Moderna",
        "BioNTech",
        "Regeneron",
        "Vertex",
        "Eli Lilly",
        "Merck",
    ),
    "医疗器械": (
        "迈瑞医疗",
        "联影医疗",
        "爱尔眼科",
        "Intuitive Surgical",
        "Stryker",
        "Medtronic",
        "Boston Scientific",
        "Dexcom",
        "Edwards Lifesciences",
    ),
    "CXO": ("药明康德", "药明生物", "凯莱英", "泰格医药", "康龙化成", "ICON", "IQVIA", "Charles River"),
    "中药": ("片仔癀", "云南白药", "同仁堂", "东阿阿胶", "华润三九"),
    "银行": (
        "银行",
        "Bank",
        "Bancorp",
        "JPMorgan",
        "JP Morgan",
        "Citigroup",
        "Bank of America",
        "Wells Fargo",
        "工商银行",
        "建设银行",
        "农业银行",
        "中国银行",
        "招商银行",
        "交通银行",
        "兴业银行",
        "平安银行",
    ),
    "保险": (
        "保险",
        "Insurance",
        "AIG",
        "Allstate",
        "Progressive",
        "中国平安",
        "中国人寿",
        "中国太保",
        "新华保险",
        "友邦保险",
        "Berkshire Hathaway",
    ),
    "券商": (
        "证券",
        "券商",
        "Securities",
        "Morgan Stanley",
        "Goldman Sachs",
        "中信证券",
        "东方财富",
        "华泰证券",
        "招商证券",
        "国泰君安",
        "海通证券",
    ),
    "房地产": ("万科", "保利发展", "华润置地", "龙湖集团", "中国海外发展"),
    "白酒": ("茅台", "贵州茅台", "五粮液", "泸州老窖", "山西汾酒", "洋河股份", "古井贡酒"),
    "食品饮料": (
        "伊利股份",
        "海天味业",
        "双汇发展",
        "农夫山泉",
        "可口可乐",
        "Coca-Cola",
        "Pepsi",
        "Mondelez",
        "Starbucks",
        "McDonald's",
    ),
    "家电": ("美的集团", "格力电器", "海尔智家", "海信家电", "老板电器", "Midea", "Gree", "Haier", "Whirlpool"),
    "游戏传媒": ("网易", "Roblox", "Electronic Arts", "Take-Two", "腾讯音乐", "分众传媒", "三七互娱"),
    "跨境电商": ("安克创新", "焦点科技", "华凯易佰", "Global-e", "Sea Limited", "MercadoLibre"),
    "物流快递": ("顺丰", "圆通", "韵达", "申通", "中通", "京东物流", "UPS", "FedEx", "DHL", "ZTO"),
    "航运港口": ("中远海控", "招商港口", "上港集团", "海丰国际", "东方海外", "Maersk", "Matson", "ZIM"),
    "煤炭": ("中国神华", "兖矿能源", "陕西煤业", "中煤能源", "山西焦煤", "Peabody", "Arch Resources"),
    "油气": (
        "石油",
        "中海油",
        "中国石油",
        "中国石化",
        "中国海油",
        "Exxon",
        "Exxon Mobil",
        "Chevron",
        "ConocoPhillips",
        "Schlumberger",
        "Shell",
        "BP",
    ),
    "有色金属": ("紫金矿业", "洛阳钼业", "中国铝业", "天齐锂业", "赣锋锂业", "Freeport", "Southern Copper", "Albemarle"),
    "黄金": ("山东黄金", "中金黄金", "赤峰黄金", "黄金", "Barrick", "Newmont", "Agnico Eagle", "Gold Fields", "Kinross Gold"),
    "稀土": ("北方稀土", "中国稀土", "盛和资源", "MP Materials"),
    "化工材料": ("万华化学", "华鲁恒升", "龙佰集团", "恒力石化", "宝丰能源", "BASF", "Dow", "LyondellBasell"),
    "工程机械": ("三一重工", "徐工机械", "中联重科", "恒立液压", "Caterpillar", "Deere", "Komatsu"),
    "军工信息化": ("中航沈飞", "中航西飞", "航发动力", "中航光电", "Lockheed Martin", "RTX", "Northrop", "General Dynamics"),
    "高铁轨交": ("中国中车", "中国通号", "时代电气", "京沪高铁", "CRRC"),
    "环保水务": ("北控水务", "首创环保", "瀚蓝环境", "Waste Management", "Republic Services"),
    "农业种业": ("隆平高科", "大北农", "登海种业", "Corteva", "Deere"),
    "养殖": ("牧原股份", "温氏股份", "海大集团", "新希望", "Tyson Foods"),
}

CURATED_INDUSTRY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "AI算力": ("GPU", "AI芯片", "AI服务器", "数据中心", "算力租赁", "液冷服务器", "光通信", "交换芯片"),
    "半导体": ("Foundry", "晶圆代工", "芯片设计", "封装测试", "刻蚀设备", "光刻胶", "存储芯片", "功率半导体"),
    "互联网平台": ("搜索广告", "社交平台", "电商平台", "外卖", "本地生活", "云计算平台", "短视频"),
    "软件服务": ("企业软件", "ERP", "CRM", "办公软件", "数据库", "云软件", "SaaS", "AI应用", "大模型应用"),
    "创新药": ("Biotech", "生物制药", "单抗", "双抗", "ADC", "GLP-1", "肿瘤药", "免疫治疗"),
    "医疗器械": ("影像设备", "IVD", "诊断设备", "高值耗材", "心血管器械", "手术机器人", "糖尿病器械"),
    "油气": ("Oil", "Gas", "天然气", "LNG", "页岩油", "油服", "炼化", "海上油气"),
    "煤炭": ("动力煤", "焦煤", "煤化工", "煤矿", "焦炭"),
    "有色金属": ("铜矿", "铝业", "锂矿", "钴镍", "钼", "铜", "铝", "锂", "镍"),
    "黄金": ("金矿", "贵金属", "Gold Miner", "黄金矿企"),
    "电力电网": ("电力", "水电", "火电", "绿电", "配电", "输电", "智能电网", "变压器", "特高压"),
    "核电": ("核电站", "核燃料", "核岛", "铀", "核电运营"),
    "家电": ("白电", "空调", "冰箱", "洗衣机", "厨电", "小家电"),
    "白酒": ("高端白酒", "次高端白酒", "酱香酒", "浓香酒"),
    "食品饮料": ("乳制品", "调味品", "软饮料", "休闲食品", "速冻食品", "连锁餐饮"),
    "物流快递": ("快递", "综合物流", "供应链物流", "货运代理", "包裹配送"),
    "航运港口": ("集装箱航运", "油运", "干散货", "码头", "港口运营"),
    "工程机械": ("挖掘机", "起重机", "混凝土机械", "矿山机械", "高空作业平台"),
    "军工信息化": ("航空装备", "航天装备", "导弹", "军工电子", "雷达", "防务", "Defense"),
    "消费电子": ("智能手机", "PC", "可穿戴", "显示面板", "光学镜头", "声学器件"),
    "新能源车": ("电动车", "动力电池", "整车", "智能座舱", "新能源汽车", "EV"),
}

CODE_HINTS: dict[str, tuple[str, ...]] = {
    "AI算力": ("NVDA", "AMD", "AVGO", "MRVL", "SMCI", "300308", "300502", "601138", "000977", "688256", "688041"),
    "半导体": ("TSM", "ASML", "AMAT", "LRCX", "QCOM", "INTC", "MU", "TXN", "ADI", "688981", "002371", "688012", "603501", "603986", "600584"),
    "互联网平台": ("BABA", "9988.HK", "09988.HK", "700", "0700.HK", "00700.HK", "PDD", "JD", "9618.HK", "09618.HK", "3690.HK", "03690.HK", "META", "AMZN", "GOOG", "GOOGL", "NTES", "BIDU", "1024.HK", "01024.HK"),
    "软件服务": ("MSFT", "ORCL", "CRM", "ADBE", "NOW", "SAP", "SNOW", "INTU", "600588", "688111", "0268.HK", "00268.HK", "600536", "600570", "002410"),
    "新能源车": ("TSLA", "002594", "1211.HK", "01211.HK", "NIO", "9866.HK", "09866.HK", "XPEV", "9868.HK", "09868.HK", "LI", "2015.HK", "02015.HK", "601127"),
    "消费电子": ("AAPL", "002475", "002241", "000725", "300433", "2382.HK", "02382.HK", "1810.HK", "01810.HK", "SONY"),
    "创新药": ("600276", "688235", "6160.HK", "06160.HK", "1801.HK", "01801.HK", "1877.HK", "01877.HK", "BGNE", "MRNA", "BNTX", "REGN", "VRTX", "LLY", "MRK"),
    "医疗器械": ("300760", "688271", "ISRG", "SYK", "MDT", "BSX", "DXCM", "EW", "ALGN"),
    "银行": ("601398", "1398.HK", "01398.HK", "601939", "0939.HK", "00939.HK", "601288", "1288.HK", "01288.HK", "601988", "3988.HK", "03988.HK", "600036", "3968.HK", "03968.HK", "000001", "JPM", "BAC", "WFC", "C", "USB"),
    "保险": ("601318", "2318.HK", "02318.HK", "601628", "2628.HK", "02628.HK", "601601", "2601.HK", "02601.HK", "AIG", "PGR", "ALL", "BRK.B"),
    "券商": ("600030", "6030.HK", "06030.HK", "300059", "601688", "6886.HK", "06886.HK", "600999", "601211", "2611.HK", "02611.HK", "GS", "MS", "SCHW"),
    "白酒": ("600519", "000858", "000568", "600809", "002304", "000596"),
    "食品饮料": ("600887", "603288", "000895", "9633.HK", "09633.HK", "KO", "PEP", "MDLZ", "SBUX", "MCD"),
    "家电": ("000333", "000651", "600690", "6690.HK", "06690.HK", "000921", "WHR"),
    "物流快递": ("002352", "600233", "002120", "002468", "2057.HK", "02057.HK", "ZTO", "UPS", "FDX"),
    "航运港口": ("601919", "1919.HK", "01919.HK", "001872", "600018", "0316.HK", "00316.HK", "MATX", "ZIM"),
    "煤炭": ("601088", "1088.HK", "01088.HK", "600188", "1171.HK", "01171.HK", "601225", "1898.HK", "01898.HK", "BTU"),
    "油气": ("601857", "0857.HK", "00857.HK", "600028", "0386.HK", "00386.HK", "600938", "0883.HK", "00883.HK", "XOM", "CVX", "COP", "SLB", "SHEL", "BP"),
    "有色金属": ("601899", "2899.HK", "02899.HK", "603993", "3993.HK", "03993.HK", "601600", "2600.HK", "02600.HK", "002466", "002460", "FCX", "SCCO", "ALB"),
    "黄金": ("600547", "1787.HK", "01787.HK", "600489", "600988", "NEM", "GOLD", "AEM"),
    "电力电网": ("600900", "600011", "0902.HK", "00902.HK", "600027", "2380.HK", "02380.HK", "NEE", "DUK", "SO", "NGG"),
    "核电": ("601985", "003816", "1816.HK", "01816.HK", "CCJ", "CEG"),
    "工程机械": ("600031", "000425", "000157", "601100", "CAT", "DE", "KMTUY"),
    "军工信息化": ("600760", "000768", "600893", "002179", "LMT", "RTX", "NOC", "GD"),
}

GENERIC_NAME_KEYWORDS = {
    "ai",
    "ev",
    "科技",
    "技术",
    "控股",
    "集团",
    "股份",
    "软件",
    "服务",
    "数字化",
    "云",
    "数据",
    "传媒",
    "广告",
    "游戏",
    "汽车",
    "电子",
    "能源",
    "材料",
    "化工",
    "农业",
    "黄金",
    "有色",
}

NAME_PATTERN_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "半导体",
        (
            "半导体",
            "集成电路",
            "微电子",
            "芯源",
            "芯原",
            "芯微",
            "芯碁",
            "纳芯",
            "龙芯",
            "华虹",
            "中芯",
            "存储",
            "晶圆",
            "封测",
            "拓荆",
            "安集",
            "长川科技",
            "思瑞浦",
            "圣邦股份",
            "科磊",
            "闪迪",
            "西部数据",
            "Arm Holdings",
            "Microchip",
            "Monolithic Power",
        ),
    ),
    (
        "通信设备",
        (
            "光纤",
            "光缆",
            "光通信",
            "光模块",
            "光子",
            "通信",
            "瑞可达",
            "天孚通信",
            "长飞光纤",
            "光库科技",
            "太辰光",
            "剑桥科技",
            "Ciena",
            "思科",
            "Cisco",
            "诺基亚",
            "Nokia",
        ),
    ),
    (
        "AI算力",
        (
            "服务器",
            "数据中心",
            "胜宏科技",
            "沪电股份",
            "深南电路",
            "鹏鼎控股",
            "戴尔科技",
            "Dell",
            "Vertiv",
        ),
    ),
    (
        "消费电子",
        (
            "消费电子",
            "电子",
            "光电",
            "光学",
            "电路",
            "精密",
            "水晶光电",
            "蓝特光学",
            "中润光学",
            "凌云光",
            "康宁",
            "Corning",
        ),
    ),
    (
        "创新药",
        (
            "生物",
            "医药",
            "药业",
            "制药",
            "阿斯利康",
            "AstraZeneca",
            "强生",
            "Johnson",
            "Therapeutics",
            "Pharma",
            "Biotech",
        ),
    ),
    (
        "医疗器械",
        (
            "医疗",
            "健康",
            "器械",
            "联合健康",
            "UnitedHealth",
        ),
    ),
    (
        "固态电池",
        (
            "电池",
            "锂",
            "天赐材料",
            "恩捷股份",
            "湖南裕能",
            "容百科技",
            "德福科技",
        ),
    ),
    (
        "化工材料",
        (
            "材料",
            "新材",
            "气体",
            "特气",
            "化学",
            "纳微",
            "华特气体",
            "广钢气体",
        ),
    ),
    (
        "电力电网",
        (
            "电力",
            "电气",
            "电网",
            "新能",
            "GE Vernova",
            "广达服务",
            "Quanta Services",
            "Comfort Systems",
        ),
    ),
    (
        "工程机械",
        (
            "机械",
            "数控",
            "装备",
            "康明斯",
            "Cummins",
        ),
    ),
    (
        "军工信息化",
        (
            "航天",
            "卫星",
            "中船",
            "航空",
            "防务",
            "Aerospace",
        ),
    ),
    (
        "商业零售",
        (
            "沃尔玛",
            "Walmart",
            "开市客",
            "Costco",
            "固安捷",
            "Grainger",
        ),
    ),
    (
        "银行",
        (
            "银行",
            "皇家银行",
            "道明银行",
            "三菱日联金融",
            "Bank",
            "Banc",
            "Financial",
        ),
    ),
    (
        "有色金属",
        (
            "矿业",
            "金属",
            "必和必拓",
            "力拓",
            "BHP",
            "Rio Tinto",
        ),
    ),
    (
        "食品饮料",
        (
            "食品",
            "饮料",
            "百威",
            "Anheuser",
        ),
    ),
    (
        "软件服务",
        (
            "软件",
            "数据",
            "Datadog",
        ),
    ),
)


def build_mapping_rules(industry_keywords: dict[str, list[str]]) -> list[IndustryMappingRule]:
    """Build deterministic rules from industry keywords plus curated stock-name hints."""
    rules: list[IndustryMappingRule] = []
    for industry, keywords in industry_keywords.items():
        combined = list(dict.fromkeys([industry, *keywords, *CURATED_INDUSTRY_KEYWORDS.get(industry, ()), *NAME_HINTS.get(industry, ())]))
        rules.append(IndustryMappingRule(industry=industry, keywords=tuple(item for item in combined if item)))
    return rules


def map_stock_industry(stock: Any, rules: list[IndustryMappingRule], *, allow_override: bool = False) -> IndustryMappingMatch | None:
    if not allow_override and not is_unclassified(getattr(stock, "industry_level1", "")):
        return None

    fields = _stock_text_fields(stock)
    if not any(value for _, value in fields):
        return None

    scored: list[tuple[float, IndustryMappingRule, list[str], list[dict[str, str]]]] = []
    for rule in rules:
        score = 0.0
        matched: list[str] = []
        evidence: list[dict[str, str]] = []
        code_hint = _matched_code_hint(stock, rule.industry)
        if code_hint:
            score += 3.2
            matched.append(code_hint)
            evidence.append({"field": "code", "keyword": code_hint})
        for keyword in rule.keywords:
            normalized_keyword = keyword.lower()
            for field_name, value in fields:
                if not value or not _keyword_matches_field(field_name, value, keyword, rule.industry, normalized_keyword):
                    continue
                field_score = _field_weight(field_name, keyword, rule.industry)
                score += field_score
                if keyword not in matched:
                    matched.append(keyword)
                evidence.append({"field": field_name, "keyword": keyword})
        if score > 0:
            scored.append((score, rule, matched, evidence))

    if not scored:
        return _fallback_name_pattern_match(stock)

    scored.sort(key=lambda item: (item[0], len(item[2])), reverse=True)
    best_score, best_rule, matched, evidence = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    confidence = _confidence(best_score, second_score)
    reason = _reason(best_rule.industry, confidence, matched, evidence, second_score)
    return IndustryMappingMatch(
        industry=best_rule.industry,
        confidence=confidence,
        reason=reason,
        matched_keywords=tuple(matched),
        evidence=tuple(evidence),
    )


def _fallback_name_pattern_match(stock: Any) -> IndustryMappingMatch | None:
    name = str(getattr(stock, "name", "") or "")
    if not name:
        return None
    normalized_name = name.lower()
    for industry, keywords in NAME_PATTERN_HINTS:
        for keyword in keywords:
            if keyword.lower() in normalized_name:
                confidence = 0.43 if keyword in {"电子", "材料", "数据"} else 0.52
                return IndustryMappingMatch(
                    industry=industry,
                    confidence=confidence,
                    reason=f"名称模式映射到{industry}：股票名称包含“{keyword}”，置信度={confidence:.2f}。",
                    matched_keywords=(keyword,),
                    evidence=({"field": "name_pattern", "keyword": keyword},),
                )
    return None


def is_unclassified(industry_level1: str | None) -> bool:
    value = (industry_level1 or "").strip()
    return value in UNCLASSIFIED_INDUSTRIES


def mapping_metadata(match: IndustryMappingMatch) -> dict[str, Any]:
    return {
        "version": MAPPING_VERSION,
        "industry": match.industry,
        "confidence": match.confidence,
        "reason": match.reason,
        "matched_keywords": list(match.matched_keywords),
        "evidence": list(match.evidence),
    }


def merge_mapping_metadata(raw_metadata: str | None, match: IndustryMappingMatch) -> str:
    try:
        metadata = json.loads(raw_metadata or "{}")
    except json.JSONDecodeError:
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    metadata[MAPPING_VERSION] = mapping_metadata(match)
    return json.dumps(metadata, ensure_ascii=False, sort_keys=True)


def extract_mapping_metadata(raw_metadata: str | None) -> dict[str, Any]:
    try:
        metadata = json.loads(raw_metadata or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(metadata, dict):
        return {}
    value = metadata.get(MAPPING_VERSION, {})
    return value if isinstance(value, dict) else {}


def _stock_text_fields(stock: Any) -> list[tuple[str, str]]:
    concepts = _loads_concepts(getattr(stock, "concepts", "[]"))
    return [
        ("name", str(getattr(stock, "name", "") or "")),
        ("concepts", " ".join(concepts)),
        ("industry_level2", str(getattr(stock, "industry_level2", "") or "")),
    ]


def _loads_concepts(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item) for item in raw if item]
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return [raw]
    if isinstance(parsed, list):
        return [str(item) for item in parsed if item]
    return [str(parsed)] if parsed else []


def _field_weight(field_name: str, keyword: str, industry: str) -> float:
    if field_name == "concepts":
        return 2.4 if keyword != industry else 1.8
    if field_name == "industry_level2":
        return 2.2 if keyword != industry else 1.7
    if field_name == "name":
        return 2.0 if keyword in NAME_HINTS.get(industry, ()) else 1.0
    return 1.0


def _keyword_matches_field(
    field_name: str,
    value: str,
    keyword: str,
    industry: str,
    normalized_keyword: str,
) -> bool:
    normalized_value = value.lower()
    if field_name != "name":
        return normalized_keyword in normalized_value
    if keyword not in NAME_HINTS.get(industry, ()):
        if _is_generic_name_keyword(keyword):
            return False
        return normalized_keyword in normalized_value
    if len(keyword) <= 2:
        return normalized_value == normalized_keyword
    return normalized_keyword in normalized_value


def _matched_code_hint(stock: Any, industry: str) -> str | None:
    identifiers = _stock_identifiers(stock)
    if not identifiers:
        return None
    for hint in CODE_HINTS.get(industry, ()):
        if _normalize_identifier(hint) in identifiers:
            return hint
    return None


def _stock_identifiers(stock: Any) -> set[str]:
    values: set[str] = set()
    for field_name in ("code", "symbol", "ticker"):
        raw = str(getattr(stock, field_name, "") or "").strip()
        if not raw:
            continue
        normalized = _normalize_identifier(raw)
        values.add(normalized)
        if "." in normalized:
            base = normalized.split(".", 1)[0]
            values.add(base)
            if base:
                values.add(base.lstrip("0") or "0")
    return values


def _normalize_identifier(value: str) -> str:
    return value.strip().upper().replace(" ", "")


def _is_generic_name_keyword(keyword: str) -> bool:
    normalized = keyword.strip().lower()
    if normalized in GENERIC_NAME_KEYWORDS:
        return True
    cjk_chars = [char for char in keyword if "\u4e00" <= char <= "\u9fff"]
    if cjk_chars and len(cjk_chars) <= 2:
        return True
    return len(normalized) <= 2


def _confidence(best_score: float, second_score: float) -> float:
    separation = max(best_score - second_score, 0.0)
    raw = 0.34 + min(best_score, 7.0) * 0.08 + min(separation, 4.0) * 0.035
    if second_score and separation < 1.0:
        raw -= 0.08
    return round(max(0.35, min(raw, 0.96)), 2)


def _reason(
    industry: str,
    confidence: float,
    matched: list[str],
    evidence: list[dict[str, str]],
    second_score: float,
) -> str:
    fields = sorted({item["field"] for item in evidence})
    conflict_note = "；存在近似候选，按得分最高规则落位" if second_score else ""
    return (
        f"规则映射到{industry}：匹配字段={','.join(fields)}，"
        f"关键词={','.join(matched[:8])}，置信度={confidence:.2f}{conflict_note}。"
    )
