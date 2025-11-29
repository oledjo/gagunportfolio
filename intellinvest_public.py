import re
import json
from datetime import datetime
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup
from sqlmodel import Session
from database import engine, create_db_and_tables
from models import Holding


def extract_portfolio_id(url: str) -> Optional[str]:
    """
    Extract portfolio ID from IntelliInvest public portfolio URL
    
    Args:
        url: URL like https://intelinvest.ru/public-portfolio/757008/
        
    Returns:
        Portfolio ID or None
    """
    match = re.search(r'/public-portfolio/(\d+)', url)
    return match.group(1) if match else None


def fetch_public_portfolio_data(url: str) -> Dict:
    """
    Fetch and parse data from IntelliInvest public portfolio page
    
    Args:
        url: Public portfolio URL
        
    Returns:
        Dictionary with portfolio data
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find script tags with portfolio data
        scripts = soup.find_all('script')
        portfolio_data = None
        
        for script in scripts:
            if script.string and 'overview' in script.string:
                # Try to extract JSON-like data from JavaScript
                script_content = script.string
                
                # Look for overview object
                overview_match = re.search(r'overview:\s*({[^}]+})', script_content)
                if overview_match:
                    # Try to parse as JSON (may need more sophisticated parsing)
                    try:
                        # Extract key-value pairs from JavaScript object
                        overview_str = overview_match.group(1)
                        # Simple extraction of key values
                        portfolio_data = {
                            'total_cost': _extract_value(overview_str, 'currCost'),
                            'daily_change': _extract_value(overview_str, 'dailyPl'),
                            'profit': _extract_value(overview_str, 'profit'),
                            'profit_percent': _extract_value(overview_str, 'percProfit'),
                        }
                    except:
                        pass
        
        # Alternative: try to find data in window.__NUXT__ or similar
        for script in scripts:
            if script.string:
                script_content = script.string
                
                # Look for any script with portfolio data
                if any(keyword in script_content for keyword in ['ticker', 'portfolioParams', 'overview', 'currCost', 'aWu', 'aWH']):
                    # Try to extract holdings data using improved parser
                    holdings = _extract_holdings_from_script(script_content)
                    if holdings:
                        return {
                            'holdings': holdings,
                            'source': 'intellinvest_public',
                            'url': url
                        }
        
        # Try a more aggressive approach - look for all ticker patterns
        # and try to reconstruct holdings from the minified code
        for script in scripts:
            if script.string and len(script.string) > 10000:  # Large scripts likely contain data
                script_content = script.string
                holdings = _extract_holdings_aggressive(script_content)
                if holdings:
                    return {
                        'holdings': holdings,
                        'source': 'intellinvest_public',
                        'url': url
                    }
        
        # If we can't parse from script, try to parse HTML tables
        holdings = _parse_holdings_from_html(soup)
        
        # If still no holdings, try one more aggressive method
        if not holdings:
            # Look for any script and try aggressive parsing
            for script in scripts:
                if script.string and len(script.string) > 5000:
                    aggressive_holdings = _extract_holdings_aggressive(script.string)
                    if aggressive_holdings:
                        holdings = aggressive_holdings
                        break
        
        return {
            'holdings': holdings,
            'source': 'intellinvest_public',
            'url': url,
            'raw_data': portfolio_data
        }
        
    except Exception as e:
        raise Exception(f"Error fetching portfolio data: {str(e)}")


def _extract_value(js_string: str, key: str) -> Optional[str]:
    """Extract value from JavaScript object string"""
    pattern = rf'{key}:\s*"([^"]+)"|{key}:\s*([\d.]+)'
    match = re.search(pattern, js_string)
    return match.group(1) or match.group(2) if match else None


def _extract_holdings_from_script(script_content: str) -> List[Dict]:
    """
    Extract holdings data from JavaScript code in the page
    
    The page uses minified JavaScript with data embedded.
    We'll try to extract structured data from JavaScript objects.
    """
    holdings = []
    
    # The data is in minified JS, so we need to find patterns
    # Look for sequences that look like holdings objects
    
    # Pattern: Find objects with ticker, name, qty, currCost, etc.
    # Since JS is minified, properties might be single letters or short names
    
    # Try to find ticker patterns (could be "ticker:" or "ticker=" or just the value)
    # Look for patterns like: ticker:"AAPL" or ticker:"LRN"
    ticker_pattern = r'(?:ticker|id):\s*"([A-Z0-9.]+)"'
    tickers = re.findall(ticker_pattern, script_content)
    
    # Look for name patterns
    name_pattern = r'(?:name|shortname):\s*"([^"]+)"'
    names = re.findall(name_pattern, script_content)
    
    # Look for quantity (could be qty, quantity, openPositionQty)
    qty_pattern = r'(?:qty|quantity|openPositionQty):\s*([\d.]+)'
    quantities = re.findall(qty_pattern, script_content)
    
    # Look for current value (currCost, currentValue)
    cost_pattern = r'(?:currCost|currentValue):\s*"([^"]+)"'
    costs = re.findall(cost_pattern, script_content)
    
    # Look for invested value (bcost, investedValue)
    invested_pattern = r'(?:bcost|investedValue):\s*"([^"]+)"'
    invested_values = re.findall(invested_pattern, script_content)
    
    # Look for PnL
    pnl_pattern = r'(?:profit|pnl):\s*"([^"]+)"'
    pnls = re.findall(pnl_pattern, script_content)
    
    # Look for PnL percent
    pnl_pct_pattern = r'(?:profitPercent|pnlPercent|percProfit):\s*"([^"]+)"'
    pnl_pcts = re.findall(pnl_pct_pattern, script_content)
    
    # Try to match holdings by finding object boundaries
    # Look for patterns that suggest a holding object
    # This is complex because JS is minified, so we'll use a different approach
    
    # Alternative: Look for JSON-like structures in the script
    # Try to find arrays of objects
    json_match = re.search(r'\[({[^}]+}(?:,{[^}]+})*)\]', script_content)
    if json_match:
        # Try to parse as JSON
        try:
            json_str = json_match.group(0)
            data = json.loads(json_str)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and 'ticker' in item:
                        holdings.append(item)
        except:
            pass
    
    # If we found tickers, try to build holdings from them
    # This is a fallback - we'll match by position (not ideal but works for basic data)
    if tickers and not holdings:
        for i, ticker in enumerate(tickers[:50]):  # Limit to avoid too many
            holding = {
                'ticker': ticker,
                'name': names[i] if i < len(names) else '',
                'qty': float(quantities[i]) if i < len(quantities) else 0.0,
                'current_value': _parse_currency(costs[i]) if i < len(costs) else 0.0,
                'invested_value': _parse_currency(invested_values[i]) if i < len(invested_values) else 0.0,
                'pnl_value': _parse_currency(pnls[i]) if i < len(pnls) else 0.0,
                'pnl_pct': float(pnl_pcts[i]) if i < len(pnl_pcts) and pnl_pcts[i] else 0.0,
            }
            holdings.append(holding)
    
    return holdings


def _extract_holdings_aggressive(script_content: str) -> List[Dict]:
    """
    More aggressive extraction of holdings from minified JavaScript
    Tries to find patterns that indicate holdings data
    """
    holdings = []
    
    # Look for patterns like: ticker:"LRN" or ticker:fP (minified variable)
    # Try multiple patterns
    patterns = [
        r'ticker:\s*"([A-Z0-9.]+)"',  # ticker:"LRN"
        r'ticker:\s*([a-zA-Z]+)',      # ticker:fP (minified)
        r'\.ticker\s*=\s*"([A-Z0-9.]+)"',  # .ticker = "LRN"
    ]
    
    all_tickers = []
    for pattern in patterns:
        matches = re.findall(pattern, script_content)
        all_tickers.extend(matches)
    
    # Remove duplicates and filter valid tickers
    unique_tickers = list(set([t for t in all_tickers if len(t) >= 2 and t[0].isupper()]))
    
    # Look for names near tickers
    # Pattern: name:"Stride" or shortname:"Stride"
    name_patterns = [
        r'name:\s*"([^"]+)"',
        r'shortname:\s*"([^"]+)"',
    ]
    
    all_names = []
    for pattern in name_patterns:
        matches = re.findall(pattern, script_content)
        all_names.extend(matches)
    
    # Look for quantities
    qty_patterns = [
        r'quantity:\s*([\d.]+)',
        r'qty:\s*([\d.]+)',
        r'openPositionQty:\s*([\d.]+)',
    ]
    
    all_quantities = []
    for pattern in qty_patterns:
        matches = re.findall(pattern, script_content)
        all_quantities.extend([float(m) for m in matches])
    
    # Look for current cost (currCost)
    cost_patterns = [
        r'currCost:\s*"([^"]+)"',
        r'currentValue:\s*"([^"]+)"',
    ]
    
    all_costs = []
    for pattern in cost_patterns:
        matches = re.findall(pattern, script_content)
        all_costs.extend(matches)
    
    # Build holdings from found data
    # Match by index (imperfect but better than nothing)
    max_items = min(len(unique_tickers), 200)  # Limit to reasonable number
    
    for i in range(max_items):
        ticker = unique_tickers[i] if i < len(unique_tickers) else ''
        if not ticker:
            continue
            
        # Determine currency from ticker (base currency of the instrument)
        currency = _determine_currency_from_ticker(ticker)
        
        holding = {
            'ticker': ticker,
            'name': all_names[i] if i < len(all_names) else '',
            'qty': all_quantities[i] if i < len(all_quantities) else 0.0,
            'current_value': _parse_currency(all_costs[i]) if i < len(all_costs) else 0.0,
            'invested_value': 0.0,
            'pnl_value': 0.0,
            'pnl_pct': 0.0,
            'share_pct': 0.0,
            'asset_type': 'unknown',
            'currency': currency
        }
        holdings.append(holding)
    
    return holdings


def _determine_currency_from_ticker(ticker: str) -> str:
    """Determine base currency from ticker symbol"""
    ticker_upper = ticker.upper()
    
    # Known US tickers (NYSE/NASDAQ) - base currency is USD
    us_tickers = {"AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "TSLA", "META", "NVDA", "NFLX", 
                 "LRN", "DATA", "OXY", "TAO", "AAPLX", "SPY", "QQQ", "VTI", "VOO"}
    
    # Known crypto tickers - base currency is USD
    crypto_tickers = {"BTC", "ETH", "TON", "USDT", "BNB", "XLM", "ADA", "SOL", "DOGE"}
    
    if ticker_upper in us_tickers:
        return "USD"
    elif ticker_upper in crypto_tickers:
        return "USD"
    elif ticker_upper.endswith((".ME", ".RM", ".RT")):
        return "RUB"
    elif any(ticker_upper.endswith(suffix) for suffix in [".DE", ".FR", ".NL", ".IT", ".ES"]):
        return "EUR"
    elif "USD" in ticker_upper:
        return "USD"
    elif "EUR" in ticker_upper:
        return "EUR"
    else:
        return "RUB"  # Default to RUB


def _parse_currency(value: str) -> float:
    """Parse currency value like 'RUB 1234.56' or 'USD 100'"""
    if not value:
        return 0.0
    # Extract number part
    match = re.search(r'[\d.]+', str(value))
    if match:
        try:
            return float(match.group(0))
        except:
            return 0.0
    return 0.0


def _parse_holdings_from_html(soup: BeautifulSoup) -> List[Dict]:
    """
    Parse holdings from HTML tables (fallback method)
    """
    holdings = []
    
    # Look for tables with portfolio data
    tables = soup.find_all('table')
    
    for table in tables:
        rows = table.find_all('tr')
        headers = [th.get_text(strip=True) for th in rows[0].find_all(['th', 'td'])]
        
        # Check if this looks like a holdings table
        if any(keyword in ' '.join(headers).lower() for keyword in ['тикер', 'ticker', 'название', 'количество']):
            for row in rows[1:]:
                cells = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]
                if len(cells) >= 3:
                    holding = {
                        'ticker': cells[0] if len(cells) > 0 else '',
                        'name': cells[1] if len(cells) > 1 else '',
                        'qty': _parse_number(cells[2]) if len(cells) > 2 else 0.0,
                    }
                    holdings.append(holding)
    
    return holdings


def _parse_number(value: str) -> float:
    """Parse number from string, handling various formats"""
    if not value:
        return 0.0
    # Remove spaces and currency symbols
    cleaned = re.sub(r'[^\d.,-]', '', str(value))
    # Replace comma with dot if needed
    cleaned = cleaned.replace(',', '.')
    try:
        return float(cleaned)
    except:
        return 0.0


def load_public_portfolio(url: str) -> List[Dict]:
    """
    Load portfolio data from public IntelliInvest URL
    
    Args:
        url: Public portfolio URL
        
    Returns:
        List of dictionaries with normalized holding data
    """
    data = fetch_public_portfolio_data(url)
    holdings_data = data.get('holdings', [])
    
    # Normalize holdings data
    normalized = []
    as_of = datetime.now()
    
    for holding in holdings_data:
        ticker = holding.get("ticker", "").strip()
        # Determine currency if not already set
        currency = holding.get("currency")
        if not currency or currency == "RUB":
            currency = _determine_currency_from_ticker(ticker)
        
        normalized_holding = {
            "source": "intellinvest_public",
            "as_of": as_of.isoformat(),
            "ticker": ticker,
            "name": holding.get("name", "").strip(),
            "qty": float(holding.get("qty", 0)) if holding.get("qty") else 0.0,
            "avg_price": float(holding.get("avg_price", 0)) if holding.get("avg_price") else 0.0,
            "invested_value": float(holding.get("invested_value", 0)) if holding.get("invested_value") else 0.0,
            "current_value": float(holding.get("current_value", 0)) if holding.get("current_value") else 0.0,
            "pnl_value": float(holding.get("pnl_value", 0)) if holding.get("pnl_value") else 0.0,
            "pnl_pct": float(holding.get("pnl_pct", 0)) if holding.get("pnl_pct") else 0.0,
            "share_pct": float(holding.get("share_pct", 0)) if holding.get("share_pct") else 0.0,
            "asset_type": holding.get("asset_type", "unknown"),
            "currency": currency
        }
        normalized.append(normalized_holding)
    
    return normalized


def sync_portfolio_from_public_url(url: str) -> Dict:
    """
    Sync portfolio from IntelliInvest public URL to database
    
    Args:
        url: Public portfolio URL
        
    Returns:
        Dictionary with sync status and results
    """
    try:
        # Load data from public URL
        holdings_data = load_public_portfolio(url)
        
        if not holdings_data:
            return {
                "status": "error",
                "message": "No holdings found in public portfolio. The page structure may have changed or data is not accessible. Please try exporting the portfolio as Excel and using the file upload instead.",
                "count": 0,
                "source": "intellinvest_public"
            }
        
        # Create database and tables if not exist
        create_db_and_tables()
        
        # Open database session
        with Session(engine) as session:
            # Delete old holdings from the same source before adding new ones
            # This prevents duplicates when importing the same file multiple times
            from sqlmodel import select
            old_holdings = session.exec(
                select(Holding).where(Holding.source == "intellinvest_public")
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
                "source": "intellinvest_public",
                "url": url
            }
            
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "count": 0,
            "source": "intellinvest_public"
        }

