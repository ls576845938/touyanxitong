from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from loguru import logger


SINA_SECTOR_TO_INDUSTRY: dict[str, str] = {
    "玻璃行业": "建筑建材",
    "船舶制造": "军工信息化",
    "传媒娱乐": "游戏传媒",
    "电力行业": "电力电网",
    "电器行业": "电力电网",
    "电子器件": "半导体",
    "电子信息": "消费电子",
    "房地产": "房地产",
    "发电设备": "电力电网",
    "飞机制造": "军工信息化",
    "纺织行业": "纺织服饰",
    "纺织机械": "纺织服饰",
    "服装鞋类": "纺织服饰",
    "公路桥梁": "交通运输",
    "供水供气": "环保水务",
    "钢铁行业": "钢铁",
    "环保行业": "环保水务",
    "化工行业": "化工材料",
    "化纤行业": "化工材料",
    "家电行业": "家电",
    "酒店旅游": "旅游酒店",
    "家具行业": "家居消费",
    "金融行业": "银行",
    "交通运输": "交通运输",
    "机械行业": "工程机械",
    "建筑建材": "建筑建材",
    "开发区": "综合行业",
    "酿酒行业": "白酒",
    "摩托车": "汽车零部件",
    "煤炭行业": "煤炭",
    "农林牧渔": "农业种业",
    "农药化肥": "农业种业",
    "汽车制造": "新能源车",
    "其它行业": "综合行业",
    "塑料制品": "化工材料",
    "水泥行业": "建筑建材",
    "食品行业": "食品饮料",
    "次新股": "综合行业",
    "生物制药": "创新药",
    "商业百货": "商业零售",
    "石油行业": "油气",
    "陶瓷行业": "建筑建材",
    "物资外贸": "跨境电商",
    "医疗器械": "医疗器械",
    "仪器仪表": "仪器仪表",
    "印刷包装": "包装造纸",
    "有色金属": "有色金属",
    "综合行业": "综合行业",
    "造纸行业": "包装造纸",
}


@dataclass(frozen=True)
class SectorIndustryMember:
    code: str
    name: str
    raw_sector: str
    industry: str
    source: str = "sina_sector"


class SectorMappingClient(Protocol):
    source: str

    def fetch_a_share_members(self) -> list[SectorIndustryMember]:
        ...


class SinaSectorMappingClient:
    source = "sina_sector"

    def fetch_a_share_members(self) -> list[SectorIndustryMember]:
        import akshare as ak  # type: ignore[import-not-found]

        sectors = ak.stock_sector_spot()
        members: list[SectorIndustryMember] = []
        for row in sectors.to_dict("records"):
            label = str(row.get("label") or "").strip()
            raw_sector = str(row.get("板块") or "").strip()
            if not label or not raw_sector:
                continue
            industry = SINA_SECTOR_TO_INDUSTRY.get(raw_sector, raw_sector)
            try:
                detail = ak.stock_sector_detail(sector=label)
            except Exception as exc:  # pragma: no cover - depends on external source
                logger.warning("sina sector detail failed: sector={} label={} error={}", raw_sector, label, exc)
                continue
            for member in detail.to_dict("records"):
                code = str(member.get("code") or "").strip().zfill(6)
                name = str(member.get("name") or "").strip()
                if not code or not name:
                    continue
                members.append(
                    SectorIndustryMember(
                        code=code,
                        name=name,
                        raw_sector=raw_sector,
                        industry=industry,
                    )
                )
        return members


def get_sector_mapping_client() -> SectorMappingClient:
    return SinaSectorMappingClient()
