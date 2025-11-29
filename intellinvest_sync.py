import pandas as pd
from datetime import datetime
from typing import List, Dict
from sqlmodel import Session
from database import engine, create_db_and_tables
from models import Holding


def load_intellinvest_excel(path: str) -> List[Dict]:
    """
    Load and parse IntelliInvest Excel file from "Все бумаги" sheet
    
    Args:
        path: Path to Excel file
        
    Returns:
        List of dictionaries with normalized holding data
    """
    # Load Excel file from "Все бумаги" sheet, skip first 2 rows (header rows)
    df = pd.read_excel(path, sheet_name="Все бумаги", header=None, skiprows=2)
    
    # Column indices mapping (0-based):
    # 0: Тип (Type/Asset Type)
    # 1: Тикер (Ticker)
    # 2: Название (Name)
    # 3: Количество, шт. (Quantity)
    # 4: Средняя цена (Average Price)
    # 6: Стоимость покупок (Invested Value)
    # 8: Текущая стоимость (Current Value)
    # 11: Текущая прибыль (PnL Value)
    # 12: Текущая прибыль, % (PnL %)
    # 23: Текущая доля (Share %)
    
    # Filter rows without tickers (column 1)
    df = df[df.iloc[:, 1].notna() & (df.iloc[:, 1] != "")]
    
    # Prepare result list
    holdings = []
    as_of = datetime.now()
    
    for _, row in df.iterrows():
        # Extract values by column index
        asset_type_raw = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else "unknown"
        ticker = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        name = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
        
        # Skip if ticker is empty or is a header row
        if not ticker or ticker == "Тикер":
            continue
        
        # Normalize asset type
        asset_type_map = {
            "Акции": "stock",
            "Актив": "asset",
            "Облигации": "bond",
            "ПИФ": "mutual_fund",
            "ETF": "etf",
            "Криптовалюта": "crypto",
            "Деньги": "cash",
            "Депозит": "deposit",
            "Фьючерс": "futures",
            "NFT": "nft"
        }
        asset_type = asset_type_map.get(asset_type_raw, asset_type_raw.lower() if asset_type_raw != "unknown" else "unknown")
        
        # All values in Excel are already in RUB, so set currency to RUB
        currency = "RUB"
        
        holding = {
            "source": "intellinvest",
            "as_of": as_of.isoformat(),
            "ticker": ticker,
            "name": name,
            "qty": float(row.iloc[3]) if pd.notna(row.iloc[3]) else 0.0,
            "avg_price": float(row.iloc[4]) if pd.notna(row.iloc[4]) else 0.0,
            "invested_value": float(row.iloc[6]) if pd.notna(row.iloc[6]) else 0.0,
            "current_value": float(row.iloc[8]) if pd.notna(row.iloc[8]) else 0.0,
            "pnl_value": float(row.iloc[11]) if pd.notna(row.iloc[11]) else 0.0,
            "pnl_pct": float(row.iloc[12]) if pd.notna(row.iloc[12]) else 0.0,
            "share_pct": float(row.iloc[23]) if len(row) > 23 and pd.notna(row.iloc[23]) else 0.0,
            "asset_type": asset_type,
            "currency": currency
        }
        holdings.append(holding)
    
    return holdings


def sync_portfolio_from_intellinvest(path: str) -> Dict:
    """
    Sync portfolio from IntelliInvest Excel file to database
    
    Args:
        path: Path to Excel file
        
    Returns:
        Dictionary with sync status and results
    """
    try:
        # Load data from Excel
        holdings_data = load_intellinvest_excel(path)
        
        if not holdings_data:
            return {
                "status": "error",
                "message": "No holdings found in Excel file",
                "count": 0
            }
        
        # Create database and tables if not exist
        create_db_and_tables()
        
        # Open database session
        with Session(engine) as session:
            # Delete old holdings from the same source before adding new ones
            # This prevents duplicates when importing the same file multiple times
            from sqlmodel import select
            old_holdings = session.exec(
                select(Holding).where(Holding.source == "intellinvest")
            ).all()
            
            for old_holding in old_holdings:
                session.delete(old_holding)
            
            # Commit deletion first
            session.commit()
            
            # Convert dicts to Holding models
            holdings = []
            as_of = None
            
            for data in holdings_data:
                # Parse as_of datetime
                as_of = datetime.fromisoformat(data["as_of"])
                
                holding = Holding(
                    as_of=as_of,
                    source=data["source"],
                    ticker=data["ticker"],
                    name=data["name"],
                    qty=data["qty"],
                    avg_price=data["avg_price"],
                    invested_value=data["invested_value"],
                    current_value=data["current_value"],
                    pnl_value=data["pnl_value"],
                    pnl_pct=data["pnl_pct"],
                    share_pct=data["share_pct"],
                    asset_type=data["asset_type"],
                    currency=data["currency"]
                )
                holdings.append(holding)
            
            # Add all holdings to session
            for holding in holdings:
                session.add(holding)
            
            # Commit to database
            session.commit()
            
            # Return result
            return {
                "status": "success",
                "count": len(holdings),
                "as_of": as_of.isoformat() if as_of else None,
                "source": "intellinvest"
            }
            
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "count": 0
        }

