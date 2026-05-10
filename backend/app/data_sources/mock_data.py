from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from collections.abc import Sequence
from typing import Any


INDUSTRY_SEEDS: list[dict[str, Any]] = [
    {
        "name": "AI算力",
        "description": "AI 服务器、算力基础设施、光模块、液冷等方向。",
        "keywords": ["AI算力", "AI服务器", "光模块", "CPO", "液冷", "HBM"],
    },
    {
        "name": "机器人",
        "description": "人形机器人、工业机器人、传感器、执行器等方向。",
        "keywords": ["机器人", "人形机器人", "减速器", "伺服系统", "传感器"],
    },
    {
        "name": "低空经济",
        "description": "eVTOL、无人机、空管、低空基础设施等方向。",
        "keywords": ["低空经济", "eVTOL", "无人机", "空管系统"],
    },
    {
        "name": "固态电池",
        "description": "固态电池、锂电材料、设备与验证产线。",
        "keywords": ["固态电池", "锂电材料", "电解质", "电池设备"],
    },
    {
        "name": "创新药",
        "description": "创新药、CXO、临床进展和出海授权。",
        "keywords": ["创新药", "ADC", "GLP-1", "临床试验", "出海授权"],
    },
    {
        "name": "军工信息化",
        "description": "军工电子、信息化、卫星通信与自主可控。",
        "keywords": ["军工信息化", "卫星通信", "自主可控", "雷达"],
    },
    {
        "name": "半导体",
        "description": "半导体设计、制造、封测、材料和设备。",
        "keywords": ["半导体", "芯片", "晶圆", "封测", "半导体设备", "EDA"],
    },
    {
        "name": "消费电子",
        "description": "手机、PC、可穿戴、端侧 AI 和电子零部件。",
        "keywords": ["消费电子", "端侧AI", "手机", "可穿戴", "PCB", "摄像头"],
    },
    {
        "name": "软件服务",
        "description": "企业软件、AI 应用、SaaS 和行业数字化。",
        "keywords": ["软件", "SaaS", "AI应用", "企业服务", "数字化", "大模型应用"],
    },
    {
        "name": "网络安全",
        "description": "网络安全、数据安全、信创安全和云安全。",
        "keywords": ["网络安全", "数据安全", "云安全", "信创", "零信任"],
    },
    {
        "name": "新能源车",
        "description": "整车、动力电池、热管理、智能座舱和供应链。",
        "keywords": ["新能源车", "电动车", "智能座舱", "热管理", "动力电池"],
    },
    {
        "name": "智能驾驶",
        "description": "自动驾驶、智驾芯片、激光雷达和车路协同。",
        "keywords": ["智能驾驶", "自动驾驶", "激光雷达", "车路协同", "Robotaxi"],
    },
    {
        "name": "汽车零部件",
        "description": "汽车电子、轻量化、底盘、内外饰和零部件供应链。",
        "keywords": ["汽车零部件", "汽车电子", "轻量化", "线控制动", "热管理"],
    },
    {
        "name": "储能",
        "description": "电化学储能、逆变器、PCS、BMS 和电网侧储能。",
        "keywords": ["储能", "PCS", "BMS", "电网侧储能", "户储"],
    },
    {
        "name": "光伏",
        "description": "硅料、硅片、电池片、组件、逆变器和辅材。",
        "keywords": ["光伏", "TOPCon", "HJT", "逆变器", "硅片", "组件"],
    },
    {
        "name": "风电",
        "description": "风机、海风、塔筒、叶片、轴承和海缆。",
        "keywords": ["风电", "海上风电", "海缆", "塔筒", "叶片"],
    },
    {
        "name": "电力电网",
        "description": "电网设备、特高压、变压器、配网自动化和虚拟电厂。",
        "keywords": ["电力电网", "特高压", "变压器", "虚拟电厂", "配网"],
    },
    {
        "name": "核电",
        "description": "核电设备、核岛、常规岛、核燃料和运营服务。",
        "keywords": ["核电", "核岛", "核燃料", "核电设备"],
    },
    {
        "name": "医疗器械",
        "description": "高值耗材、影像设备、IVD、手术机器人和国产替代。",
        "keywords": ["医疗器械", "IVD", "高值耗材", "手术机器人", "国产替代"],
    },
    {
        "name": "CXO",
        "description": "CRO、CDMO、临床外包和生物药生产服务。",
        "keywords": ["CXO", "CRO", "CDMO", "临床外包", "生物药"],
    },
    {
        "name": "中药",
        "description": "中药创新、品牌中药、院外渠道和消费医疗。",
        "keywords": ["中药", "品牌中药", "院外渠道", "消费医疗"],
    },
    {
        "name": "银行",
        "description": "商业银行、息差、资产质量和分红。",
        "keywords": ["银行", "息差", "资产质量", "分红", "信贷"],
    },
    {
        "name": "保险",
        "description": "寿险、财险、投资收益、NBV 和代理人渠道。",
        "keywords": ["保险", "寿险", "财险", "NBV", "代理人"],
    },
    {
        "name": "券商",
        "description": "证券公司、投行、财富管理、自营和交易活跃度。",
        "keywords": ["券商", "证券", "投行", "财富管理", "成交额"],
    },
    {
        "name": "房地产",
        "description": "地产开发、城中村改造、销售复苏和资产负债表修复。",
        "keywords": ["房地产", "城中村改造", "销售复苏", "保交楼"],
    },
    {
        "name": "白酒",
        "description": "高端白酒、次高端、渠道库存和宴席需求。",
        "keywords": ["白酒", "高端白酒", "渠道库存", "宴席需求"],
    },
    {
        "name": "食品饮料",
        "description": "大众品、调味品、乳制品、软饮和休闲食品。",
        "keywords": ["食品饮料", "调味品", "乳制品", "软饮", "休闲食品"],
    },
    {
        "name": "家电",
        "description": "白电、厨电、小家电、出海和以旧换新。",
        "keywords": ["家电", "白电", "厨电", "小家电", "以旧换新"],
    },
    {
        "name": "游戏传媒",
        "description": "游戏、影视、广告、版权和内容出海。",
        "keywords": ["游戏", "传媒", "影视", "广告", "内容出海"],
    },
    {
        "name": "互联网平台",
        "description": "电商、本地生活、广告、云服务和平台经济。",
        "keywords": ["互联网平台", "电商", "本地生活", "广告", "云服务"],
    },
    {
        "name": "跨境电商",
        "description": "跨境平台、出海品牌、海外仓和供应链服务。",
        "keywords": ["跨境电商", "出海品牌", "海外仓", "供应链服务"],
    },
    {
        "name": "物流快递",
        "description": "快递、供应链物流、跨境物流和航运代理。",
        "keywords": ["物流", "快递", "供应链物流", "跨境物流"],
    },
    {
        "name": "航运港口",
        "description": "集运、油运、干散货、港口和海运周期。",
        "keywords": ["航运", "港口", "集运", "油运", "干散货"],
    },
    {
        "name": "煤炭",
        "description": "动力煤、焦煤、煤化工和高股息能源资产。",
        "keywords": ["煤炭", "动力煤", "焦煤", "煤化工", "高股息"],
    },
    {
        "name": "油气",
        "description": "油气开采、油服、炼化、LNG 和天然气。",
        "keywords": ["油气", "油服", "炼化", "LNG", "天然气"],
    },
    {
        "name": "有色金属",
        "description": "铜、铝、锂、钴、镍等工业金属和能源金属。",
        "keywords": ["有色金属", "铜", "铝", "锂", "钴", "镍"],
    },
    {
        "name": "黄金",
        "description": "黄金矿企、贵金属、避险资产和实际利率。",
        "keywords": ["黄金", "贵金属", "避险", "实际利率"],
    },
    {
        "name": "稀土",
        "description": "稀土矿、磁材、永磁电机和战略资源。",
        "keywords": ["稀土", "磁材", "永磁", "战略资源"],
    },
    {
        "name": "化工材料",
        "description": "化工新材料、氟化工、聚氨酯、钛白粉和周期化工。",
        "keywords": ["化工", "新材料", "氟化工", "聚氨酯", "钛白粉"],
    },
    {
        "name": "工程机械",
        "description": "挖机、起重机、高空作业平台、出海和更新周期。",
        "keywords": ["工程机械", "挖机", "起重机", "高空作业平台", "设备更新"],
    },
    {
        "name": "高铁轨交",
        "description": "高铁、城轨、动车组、信号系统和设备更新。",
        "keywords": ["高铁", "轨交", "动车组", "信号系统"],
    },
    {
        "name": "环保水务",
        "description": "固废、水务、污水处理、节能和碳监测。",
        "keywords": ["环保", "水务", "固废", "污水处理", "碳监测"],
    },
    {
        "name": "农业种业",
        "description": "种业、转基因、农化、粮食安全和农机。",
        "keywords": ["农业", "种业", "转基因", "粮食安全", "农机"],
    },
    {
        "name": "养殖",
        "description": "生猪、白羽鸡、饲料、养殖周期和动保。",
        "keywords": ["养殖", "生猪", "白羽鸡", "饲料", "动保"],
    },
    {
        "name": "建筑建材",
        "description": "建筑工程、水泥、玻璃、陶瓷、装饰材料和基建链条。",
        "keywords": ["建筑建材", "建筑", "建材", "水泥", "玻璃", "陶瓷"],
    },
    {
        "name": "钢铁",
        "description": "普钢、特钢、钢材加工和钢铁周期。",
        "keywords": ["钢铁", "特钢", "钢材", "钢厂"],
    },
    {
        "name": "纺织服饰",
        "description": "纺织、服装、鞋类、家纺和品牌消费。",
        "keywords": ["纺织", "服装", "服饰", "鞋", "家纺"],
    },
    {
        "name": "商业零售",
        "description": "百货、商超、专业零售、免税和线下消费。",
        "keywords": ["零售", "百货", "商超", "免税", "连锁"],
    },
    {
        "name": "旅游酒店",
        "description": "酒店、景区、旅游服务、免税和出行消费。",
        "keywords": ["旅游", "酒店", "景区", "免税", "出行消费"],
    },
    {
        "name": "交通运输",
        "description": "铁路、公路、航空、机场、公交和综合运输。",
        "keywords": ["交通运输", "铁路", "公路", "机场", "航空"],
    },
    {
        "name": "通信设备",
        "description": "通信设备、光纤光缆、交换机、运营商设备和网络基础设施。",
        "keywords": ["通信设备", "光纤", "光缆", "交换机", "运营商设备"],
    },
    {
        "name": "仪器仪表",
        "description": "仪器仪表、检测设备、传感器和工业测量。",
        "keywords": ["仪器仪表", "检测设备", "传感器", "工业测量"],
    },
    {
        "name": "包装造纸",
        "description": "包装印刷、造纸、纸浆和包装材料。",
        "keywords": ["包装", "印刷", "造纸", "纸浆"],
    },
    {
        "name": "家居消费",
        "description": "家具、家居、装饰和地产后周期消费。",
        "keywords": ["家具", "家居", "装饰", "地产后周期"],
    },
    {
        "name": "综合行业",
        "description": "多元经营、开发区、综合控股和暂无法细分的传统行业。",
        "keywords": ["综合", "开发区", "多元经营", "控股平台"],
    },
]


STOCK_SEEDS: list[dict[str, Any]] = [
    {
        "code": "300750",
        "name": "宁德时代",
        "market": "A",
        "board": "chinext",
        "exchange": "SZSE",
        "industry_level1": "固态电池",
        "industry_level2": "锂电池",
        "concepts": ["固态电池", "锂电材料", "电池设备"],
        "market_cap": 8200,
        "float_market_cap": 7200,
        "listing_date": date(2018, 6, 11),
        "trend_bias": 0.0012,
    },
    {
        "code": "300308",
        "name": "中际旭创",
        "market": "A",
        "board": "chinext",
        "exchange": "SZSE",
        "industry_level1": "AI算力",
        "industry_level2": "光模块",
        "concepts": ["光模块", "CPO", "AI算力"],
        "market_cap": 1900,
        "float_market_cap": 1700,
        "listing_date": date(2012, 4, 10),
        "trend_bias": 0.0024,
    },
    {
        "code": "300502",
        "name": "新易盛",
        "market": "A",
        "board": "chinext",
        "exchange": "SZSE",
        "industry_level1": "AI算力",
        "industry_level2": "光模块",
        "concepts": ["光模块", "CPO", "AI服务器"],
        "market_cap": 1200,
        "float_market_cap": 980,
        "listing_date": date(2016, 3, 3),
        "trend_bias": 0.0020,
    },
    {
        "code": "601138",
        "name": "工业富联",
        "market": "A",
        "board": "main",
        "exchange": "SSE",
        "industry_level1": "AI算力",
        "industry_level2": "AI服务器",
        "concepts": ["AI服务器", "液冷", "算力"],
        "market_cap": 5200,
        "float_market_cap": 5100,
        "listing_date": date(2018, 6, 8),
        "trend_bias": 0.0016,
    },
    {
        "code": "688256",
        "name": "寒武纪",
        "market": "A",
        "board": "star",
        "exchange": "SSE",
        "industry_level1": "AI算力",
        "industry_level2": "AI芯片",
        "concepts": ["AI算力", "AI芯片", "自主可控"],
        "market_cap": 2600,
        "float_market_cap": 2200,
        "listing_date": date(2020, 7, 20),
        "trend_bias": 0.0017,
    },
    {
        "code": "002050",
        "name": "三花智控",
        "market": "A",
        "board": "main",
        "exchange": "SZSE",
        "industry_level1": "机器人",
        "industry_level2": "执行器",
        "concepts": ["机器人", "执行器", "伺服系统"],
        "market_cap": 980,
        "float_market_cap": 930,
        "listing_date": date(2005, 6, 7),
        "trend_bias": 0.0011,
    },
    {
        "code": "002085",
        "name": "万丰奥威",
        "market": "A",
        "board": "main",
        "exchange": "SZSE",
        "industry_level1": "低空经济",
        "industry_level2": "eVTOL",
        "concepts": ["低空经济", "eVTOL", "无人机"],
        "market_cap": 360,
        "float_market_cap": 330,
        "listing_date": date(2006, 11, 28),
        "trend_bias": 0.0014,
    },
    {
        "code": "688235",
        "name": "百济神州",
        "market": "A",
        "board": "star",
        "exchange": "SSE",
        "industry_level1": "创新药",
        "industry_level2": "创新药",
        "concepts": ["创新药", "临床试验", "出海授权"],
        "market_cap": 2300,
        "float_market_cap": 1900,
        "listing_date": date(2021, 12, 15),
        "trend_bias": 0.0007,
    },
    {
        "code": "835185",
        "name": "贝特瑞",
        "market": "A",
        "board": "bse",
        "exchange": "BSE",
        "industry_level1": "固态电池",
        "industry_level2": "锂电材料",
        "concepts": ["固态电池", "锂电材料", "电解质"],
        "market_cap": 260,
        "float_market_cap": 210,
        "listing_date": date(2015, 12, 28),
        "trend_bias": 0.0009,
    },
    {
        "code": "AAPL",
        "name": "Apple",
        "market": "US",
        "board": "nasdaq",
        "exchange": "NASDAQ",
        "industry_level1": "AI算力",
        "industry_level2": "端侧AI",
        "concepts": ["端侧AI", "AI芯片", "消费电子"],
        "market_cap": 31000,
        "float_market_cap": 30000,
        "listing_date": date(1980, 12, 12),
        "trend_bias": 0.0009,
    },
    {
        "code": "NVDA",
        "name": "NVIDIA",
        "market": "US",
        "board": "nasdaq",
        "exchange": "NASDAQ",
        "industry_level1": "AI算力",
        "industry_level2": "AI芯片",
        "concepts": ["AI算力", "AI芯片", "HBM"],
        "market_cap": 29000,
        "float_market_cap": 28500,
        "listing_date": date(1999, 1, 22),
        "trend_bias": 0.0022,
    },
    {
        "code": "MSFT",
        "name": "Microsoft",
        "market": "US",
        "board": "nasdaq",
        "exchange": "NASDAQ",
        "industry_level1": "AI算力",
        "industry_level2": "云计算",
        "concepts": ["AI服务器", "云计算", "AI应用"],
        "market_cap": 30000,
        "float_market_cap": 29800,
        "listing_date": date(1986, 3, 13),
        "trend_bias": 0.0010,
    },
    {
        "code": "TSLA",
        "name": "Tesla",
        "market": "US",
        "board": "nasdaq",
        "exchange": "NASDAQ",
        "industry_level1": "机器人",
        "industry_level2": "人形机器人",
        "concepts": ["机器人", "自动驾驶", "储能"],
        "market_cap": 8200,
        "float_market_cap": 8000,
        "listing_date": date(2010, 6, 29),
        "trend_bias": 0.0013,
    },
    {
        "code": "00700.HK",
        "name": "腾讯控股",
        "market": "HK",
        "board": "hk_main",
        "exchange": "HKEX",
        "industry_level1": "AI算力",
        "industry_level2": "云与AI应用",
        "concepts": ["AI应用", "云计算", "游戏"],
        "market_cap": 36000,
        "float_market_cap": 35000,
        "listing_date": date(2004, 6, 16),
        "trend_bias": 0.0008,
    },
    {
        "code": "09988.HK",
        "name": "阿里巴巴-W",
        "market": "HK",
        "board": "hk_main",
        "exchange": "HKEX",
        "industry_level1": "AI算力",
        "industry_level2": "云计算",
        "concepts": ["AI服务器", "云计算", "AI应用"],
        "market_cap": 15000,
        "float_market_cap": 14800,
        "listing_date": date(2019, 11, 26),
        "trend_bias": 0.0009,
    },
    {
        "code": "03690.HK",
        "name": "美团-W",
        "market": "HK",
        "board": "hk_main",
        "exchange": "HKEX",
        "industry_level1": "机器人",
        "industry_level2": "本地生活自动化",
        "concepts": ["机器人", "无人配送", "AI应用"],
        "market_cap": 7200,
        "float_market_cap": 7000,
        "listing_date": date(2018, 9, 20),
        "trend_bias": 0.0007,
    },
    {
        "code": "09868.HK",
        "name": "小鹏汽车-W",
        "market": "HK",
        "board": "hk_main",
        "exchange": "HKEX",
        "industry_level1": "低空经济",
        "industry_level2": "飞行汽车",
        "concepts": ["低空经济", "eVTOL", "自动驾驶"],
        "market_cap": 650,
        "float_market_cap": 600,
        "listing_date": date(2021, 7, 7),
        "trend_bias": 0.0012,
    },
]


class MockMarketDataClient:
    source = "mock"

    def fetch_stock_list(self, markets: Sequence[str] | None = None) -> list[dict[str, Any]]:
        requested = {item.upper() for item in markets} if markets else {"A", "US", "HK"}
        rows: list[dict[str, Any]] = []
        for seed in STOCK_SEEDS:
            if seed.get("market", "A") not in requested:
                continue
            row = dict(seed)
            row["concepts"] = json.dumps(row["concepts"], ensure_ascii=False)
            row["asset_type"] = "equity"
            row["currency"] = {"A": "CNY", "US": "USD", "HK": "HKD"}.get(str(row.get("market", "A")), "CNY")
            row["listing_status"] = "listed"
            row["delisting_date"] = None
            row["is_st"] = False
            row["is_etf"] = False
            row["is_adr"] = False
            row["is_active"] = True
            row["data_vendor"] = self.source
            row["metadata_json"] = json.dumps({"provider": self.source, "universe": "mvp_seed"}, ensure_ascii=False)
            rows.append(row)
        return rows

    def fetch_fundamentals(self, markets: Sequence[str] | None = None, report_date: date | None = None) -> list[dict[str, Any]]:
        requested = {item.upper() for item in markets} if markets else {"A", "US", "HK"}
        target_report_date = report_date or date(2026, 3, 31)
        rows: list[dict[str, Any]] = []
        for seed in STOCK_SEEDS:
            if seed.get("market", "A") not in requested:
                continue
            code = str(seed["code"])
            code_hash = sum(ord(ch) for ch in code)
            trend_bias = float(seed["trend_bias"])
            growth_anchor = trend_bias * 9000 + (code_hash % 9)
            margin_anchor = 0.18 + (code_hash % 17) / 100
            roe_anchor = 0.08 + (code_hash % 13) / 100
            debt_anchor = 0.25 + (code_hash % 19) / 100
            cashflow_anchor = 0.75 + (code_hash % 8) / 10
            rows.append(
                {
                    "stock_code": code,
                    "report_date": target_report_date,
                    "period": "2026Q1",
                    "revenue_growth_yoy": round(growth_anchor, 2),
                    "profit_growth_yoy": round(growth_anchor * 0.82 + (code_hash % 5), 2),
                    "gross_margin": round(min(0.72, margin_anchor), 4),
                    "roe": round(min(0.38, roe_anchor), 4),
                    "debt_ratio": round(min(0.82, debt_anchor), 4),
                    "cashflow_quality": round(min(1.8, cashflow_anchor), 4),
                    "report_title": f"{seed['name']} 2026Q1 mock 财务快照",
                    "source": self.source,
                    "source_url": f"mock://fundamental/{code}/{target_report_date.isoformat()}",
                }
            )
        return rows

    def fetch_daily_bars(
        self,
        stock_code: str,
        market: str | None = None,
        end_date: date | None = None,
        periods: int = 320,
    ) -> list[dict[str, Any]]:
        end = end_date or date.today()
        seed = next((item for item in STOCK_SEEDS if item["code"] == stock_code), None)
        if seed is None:
            return []

        dates: list[date] = []
        cursor = end
        while len(dates) < periods:
            if cursor.weekday() < 5:
                dates.append(cursor)
            cursor -= timedelta(days=1)
        dates.reverse()

        bias = float(seed["trend_bias"])
        code_noise = (sum(ord(ch) for ch in stock_code) % 17) / 10000
        base_price = 18.0 + (sum(ord(ch) for ch in stock_code) % 80)
        pre_close = base_price
        rows: list[dict[str, Any]] = []

        for idx, trade_date in enumerate(dates):
            cycle = math.sin(idx / 14.0) * 0.012 + math.cos(idx / 47.0) * 0.008
            late_acceleration = max(idx - periods * 0.62, 0) / periods * bias * 8
            daily_return = bias + code_noise + cycle + late_acceleration
            close = max(2.0, pre_close * (1 + daily_return))
            open_price = pre_close * (1 + cycle * 0.2)
            high = max(open_price, close) * (1 + 0.012 + abs(cycle) * 0.4)
            low = min(open_price, close) * (1 - 0.012 - abs(cycle) * 0.25)
            volume = 900_000 + idx * 4200 + (sum(ord(ch) for ch in stock_code) % 11) * 45_000
            if idx > periods * 0.72:
                volume *= 1.25 + bias * 120
            amount = volume * close
            pct_chg = (close / pre_close - 1) * 100
            rows.append(
                {
                    "stock_code": stock_code,
                    "trade_date": trade_date,
                    "open": round(open_price, 3),
                    "high": round(high, 3),
                    "low": round(low, 3),
                    "close": round(close, 3),
                    "pre_close": round(pre_close, 3),
                    "volume": round(volume, 2),
                    "amount": round(amount, 2),
                    "pct_chg": round(pct_chg, 4),
                    "adj_factor": 1.0,
                    "source": self.source,
                }
            )
            pre_close = close
        return rows


class MockNewsClient:
    source = "mock"
    source_kind = "mock"
    source_confidence = 0.3

    def fetch_articles(self, published_date: date | None = None) -> list[dict[str, Any]]:
        day = published_date or date.today()
        timestamp = datetime(day.year, day.month, day.day, 9, 0, tzinfo=timezone.utc)
        article_templates = [
            ("AI算力订单延续增长，光模块与液冷环节关注度提升", ["AI算力", "光模块", "CPO", "液冷"], ["AI算力"], ["300308", "300502", "601138", "NVDA", "MSFT", "09988.HK"]),
            ("人形机器人产业链进入密集验证期，执行器和传感器环节被频繁提及", ["机器人", "人形机器人", "执行器"], ["机器人"], ["002050", "TSLA", "03690.HK"]),
            ("低空经济地方试点继续推进，eVTOL 与空管系统热度上升", ["低空经济", "eVTOL", "空管系统"], ["低空经济"], ["002085", "09868.HK"]),
            ("固态电池中试线进展受关注，材料与设备验证仍需跟踪", ["固态电池", "电池设备"], ["固态电池"], ["300750", "835185"]),
            ("创新药出海授权和临床进展成为医药板块重要催化线索", ["创新药", "临床试验", "出海授权"], ["创新药"], ["688235"]),
            ("军工信息化与卫星通信主题活跃，但订单兑现节奏需要继续验证", ["军工信息化", "卫星通信"], ["军工信息化"], []),
        ]
        rows: list[dict[str, Any]] = []
        for idx, (title, keywords, industries, stocks) in enumerate(article_templates):
            rows.append(
                {
                    "title": title,
                    "content": f"{title}。本文为 AlphaRadar mock 数据，用于验证产业热度和证据链生成流程。",
                    "summary": title,
                    "source": self.source,
                    "source_kind": self.source_kind,
                    "source_confidence": self.source_confidence,
                    "source_url": f"mock://news/{day.isoformat()}/{idx}",
                    "published_at": timestamp + timedelta(minutes=idx * 20),
                    "matched_keywords": json.dumps(keywords, ensure_ascii=False),
                    "related_industries": json.dumps(industries, ensure_ascii=False),
                    "related_stocks": json.dumps(stocks, ensure_ascii=False),
                }
            )
        return rows
