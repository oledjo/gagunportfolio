from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class HoldingResponse(BaseModel):
    """Response schema for holding"""
    id: int
    as_of: datetime
    source: str
    ticker: str
    name: str
    qty: float
    avg_price: float
    invested_value: float
    current_value: float
    pnl_value: float
    pnl_pct: float
    share_pct: float
    asset_type: str
    currency: str
    sentiment: Optional[str] = None  # positive, negative, neutral

    class Config:
        from_attributes = True


class PortfolioStats(BaseModel):
    """Portfolio statistics"""
    total_holdings: int
    total_invested_value: float
    total_current_value: float
    total_pnl_value: float
    total_pnl_pct: float
    last_sync: Optional[datetime] = None
    by_asset_type: dict[str, dict[str, float]]  # {asset_type: {'count': int, 'pct': float}}
    by_currency: dict[str, dict[str, float]]  # {currency: {'count': int, 'pct': float}}
    by_currency_value: dict[str, dict[str, float]]  # {currency: {'value': float, 'pct': float}}


class SyncResponse(BaseModel):
    """Response schema for sync operation"""
    status: str
    count: int
    as_of: Optional[datetime] = None
    source: str
    message: Optional[str] = None

