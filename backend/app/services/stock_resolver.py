from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Stock


STOCK_ALIAS_CODES: dict[str, str] = {
    "ACCELINK": "002281",
    "ALPHABET": "GOOGL",
    "AMAZON": "AMZN",
    "AMPHENOL": "APH",
    "APPLIEDMATERIALS": "AMAT",
    "ARISTA": "ANET",
    "ARISTANETWORKS": "ANET",
    "ASE": "ASX",
    "ASTERALABS": "ALAB",
    "AWS": "AMZN",
    "AWSTRAINIUM": "AMZN",
    "AWSINFERENTIA": "AMZN",
    "BROADCOM": "AVGO",
    "CATL": "300750",
    "CISCO": "CSCO",
    "COHERENT": "COHR",
    "CREDO": "CRDO",
    "DELL": "DELL",
    "EOPTOLINK": "300502",
    "FOXCONN": "601138",
    "FOXCONN/工业富联": "601138",
    "GLOBALFOUNDRIES": "GFS",
    "GOOGLE": "GOOG",
    "GOOGLEAXION": "GOOG",
    "GOOGLETPU": "GOOG",
    "HPE": "HPE",
    "IBIDEN": "4062.T",
    "INNOLIGHT": "300308",
    "INSPUR": "000977",
    "INSPUR/浪潮": "000977",
    "INTELFOUNDRY": "INTC",
    "INTELGAUDI": "INTC",
    "INTELXEON": "INTC",
    "LAMRESEARCH": "LRCX",
    "LENOVO": "0992.HK",
    "LITE": "LITE",
    "LUMENTUM": "LITE",
    "MARVELL": "MRVL",
    "META": "META",
    "MICROSOFT": "MSFT",
    "MICROSOFTCOBALT": "MSFT",
    "MICROSOFTMAIA": "MSFT",
    "MICRON": "MU",
    "NVIDIA": "NVDA",
    "NVIDIAGRACE": "NVDA",
    "NVIDIAMELLANOX": "NVDA",
    "NVIDIA/MELLANOX": "NVDA",
    "NVIDIANVLINK": "NVDA",
    "NVIDIANVSWITCH": "NVDA",
    "ORACLE": "ORCL",
    "SKHYNIX": "000660.KS",
    "SAMSUNG": "005930.KS",
    "SAMSUNGFOUNDRY": "005930.KS",
    "SMIC": "688981",
    "SUPERMICRO": "SMCI",
    "SUPERMICROCOMPUTER": "SMCI",
    "SYNOPSYS": "SNPS",
    "TSMC": "TSM",
    "WESTERNDIGITAL": "WDC",
    "台积电": "TSM",
    "日月光": "ASX",
    "英伟达": "NVDA",
    "阿里云": "BABA",
}


def alias_code_for_identifier(identifier: str | None) -> str | None:
    key = _alias_key(identifier)
    if not key:
        return None
    return STOCK_ALIAS_CODES.get(key)


def resolve_stock(session: Session, identifier: str) -> Stock | None:
    raw = (identifier or "").strip()
    if not raw:
        return None

    stock = session.scalar(select(Stock).where(Stock.code == raw))
    if stock is not None:
        return stock

    lowered = raw.lower()
    stock = session.scalar(select(Stock).where(func.lower(Stock.code) == lowered).limit(1))
    if stock is not None:
        return stock

    alias_code = alias_code_for_identifier(raw)
    if alias_code:
        stock = session.scalar(select(Stock).where(Stock.code == alias_code).limit(1))
        if stock is not None:
            return stock

    stock = session.scalar(select(Stock).where(Stock.name == raw).order_by(Stock.is_etf.asc(), Stock.is_active.desc()).limit(1))
    if stock is not None:
        return stock

    return session.scalars(
        select(Stock)
        .where(or_(func.lower(Stock.name) == lowered, func.lower(Stock.code) == lowered))
        .order_by(Stock.is_etf.asc(), Stock.is_active.desc())
        .limit(1)
    ).first()


def _alias_key(identifier: str | None) -> str:
    value = (identifier or "").strip()
    if not value:
        return ""
    return (
        value.upper()
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
        .replace(".", "")
        .replace("&", "AND")
    )
