from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select
from typing import List, Dict, Any, Optional
from collections import Counter
import tempfile
import os
import httpx
import json
import re
import logging
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import feedparser
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging to output to console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler()  # Explicitly add StreamHandler to ensure output to console
    ],
    force=True  # Force reconfiguration if already configured
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Also configure uvicorn logging
import logging as uvicorn_logging
uvicorn_logger = uvicorn_logging.getLogger("uvicorn")
uvicorn_logger.setLevel(uvicorn_logging.INFO)

from database import engine, create_db_and_tables
from models import Holding, NewsAnalysis, BatchJob
from schemas import HoldingResponse, PortfolioStats, SyncResponse
from intellinvest_sync import sync_portfolio_from_intellinvest
from intellinvest_public import sync_portfolio_from_public_url
from fastapi import BackgroundTasks
import asyncio
import threading

# Create FastAPI app
app = FastAPI(
    title="Portfolio API",
    description="API for managing IntelliInvest portfolio data",
    version="1.0.0"
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
def on_startup():
    """Initialize database on startup"""
    create_db_and_tables()
    
    # Import models to ensure tables are created
    from models import NewsAnalysis, BatchJob


@app.get("/", response_class=HTMLResponse)
def root():
    """Homepage - serve the dashboard"""
    return FileResponse("static/index.html")


@app.get("/api")
def api_info():
    """API information endpoint"""
    return {
        "message": "Portfolio API",
        "version": "1.0.0",
        "endpoints": {
            "holdings": "/holdings",
            "holding_by_ticker": "/holdings/{ticker}",
            "stats": "/stats",
            "sync": "/sync"
        }
    }


@app.get("/holdings", response_model=List[HoldingResponse])
def get_holdings(
    skip: int = 0,
    limit: int = 100,
    asset_type: str = None,
    currency: str = None,
    ticker: str = None
):
    """
    Get all holdings with optional filters
    
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    - **asset_type**: Filter by asset type (stock, bond, crypto, etc.)
    - **currency**: Filter by currency (RUB, USD, EUR)
    - **ticker**: Filter by ticker (partial match)
    """
    with Session(engine) as session:
        query = select(Holding)
        
        # Apply filters
        if asset_type:
            query = query.where(Holding.asset_type == asset_type)
        if currency:
            query = query.where(Holding.currency == currency)
        if ticker:
            query = query.where(Holding.ticker.contains(ticker))
        
        # Apply pagination
        query = query.offset(skip).limit(limit)
        
        holdings = session.exec(query).all()
        
        if not holdings:
            return []
        
        # Get sentiment for each holding
        tickers = [h.ticker.upper() for h in holdings]
        sentiment_map = {}
        if tickers:
            try:
                analyses = session.exec(
                    select(NewsAnalysis).where(NewsAnalysis.ticker.in_(tickers))
                ).all()
                for analysis in analyses:
                    # Store by uppercase ticker for consistent lookup
                    sentiment_map[analysis.ticker.upper() if analysis.ticker else ''] = analysis.sentiment
            except Exception as e:
                # If there's an error, just continue without sentiment
                print(f"Error loading sentiment: {e}")
                sentiment_map = {}
        
        # Create response with sentiment
        result = []
        for holding in holdings:
            holding_dict = holding.model_dump()
            holding_dict['sentiment'] = sentiment_map.get(holding.ticker.upper())
            result.append(HoldingResponse(**holding_dict))
        
        return result


@app.get("/holdings/{ticker}", response_model=HoldingResponse)
def get_holding_by_ticker(ticker: str):
    """
    Get holding by ticker
    
    - **ticker**: Ticker symbol (case-insensitive)
    """
    with Session(engine) as session:
        # Get the most recent holding for this ticker
        query = select(Holding).where(Holding.ticker == ticker.upper()).order_by(Holding.as_of.desc())
        holding = session.exec(query).first()
        
        if not holding:
            raise HTTPException(status_code=404, detail=f"Holding with ticker {ticker} not found")
        
        return holding


@app.get("/stats", response_model=PortfolioStats)
def get_portfolio_stats():
    """
    Get portfolio statistics
    
    Returns aggregated statistics about the portfolio including:
    - Total holdings count
    - Total invested and current values
    - Total PnL
    - Breakdown by asset type and currency
    """
    with Session(engine) as session:
        holdings = session.exec(select(Holding)).all()
        
        if not holdings:
            return PortfolioStats(
                total_holdings=0,
                total_invested_value=0.0,
                total_current_value=0.0,
                total_pnl_value=0.0,
                total_pnl_pct=0.0,
                last_sync=None,
                by_asset_type={},
                by_currency={},
                by_currency_value={}
            )
        
        total_invested = sum(h.invested_value for h in holdings)
        total_current = sum(h.current_value for h in holdings)
        total_pnl = sum(h.pnl_value for h in holdings)
        total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0
        
        # Get the most recent sync date (max as_of)
        last_sync = max((h.as_of for h in holdings), default=None)
        
        # Group by asset type with percentages and values
        by_asset_type = Counter(h.asset_type for h in holdings)
        total_holdings_count = len(holdings)
        
        # Calculate value by asset type
        by_asset_type_value = {}
        for holding in holdings:
            asset_type = holding.asset_type
            if asset_type not in by_asset_type_value:
                by_asset_type_value[asset_type] = 0.0
            by_asset_type_value[asset_type] += holding.current_value
        
        by_asset_type_with_pct = {
            asset_type: {
                'count': count,
                'value': by_asset_type_value.get(asset_type, 0.0),
                'pct': round((count / total_holdings_count * 100) if total_holdings_count > 0 else 0, 1),
                'value_pct': round((by_asset_type_value.get(asset_type, 0.0) / total_current * 100) if total_current > 0 else 0, 1)
            }
            for asset_type, count in by_asset_type.items()
        }
        
        # Group by currency with percentages
        by_currency = Counter(h.currency for h in holdings)
        by_currency_with_pct = {
            currency: {
                'count': count,
                'pct': round((count / total_holdings_count * 100) if total_holdings_count > 0 else 0, 1)
            }
            for currency, count in by_currency.items()
        }
        
        # Group by currency value with percentages
        by_currency_value = {}
        for holding in holdings:
            currency = holding.currency
            if currency not in by_currency_value:
                by_currency_value[currency] = 0.0
            by_currency_value[currency] += holding.current_value
        
        by_currency_value_with_pct = {
            currency: {
                'value': value,
                'pct': round((value / total_current * 100) if total_current > 0 else 0, 1)
            }
            for currency, value in by_currency_value.items()
        }
        
        return PortfolioStats(
            total_holdings=len(holdings),
            total_invested_value=total_invested,
            total_current_value=total_current,
            total_pnl_value=total_pnl,
            total_pnl_pct=total_pnl_pct,
            last_sync=last_sync,
            by_asset_type=by_asset_type_with_pct,
            by_currency=by_currency_with_pct,
            by_currency_value=by_currency_value_with_pct
        )


@app.post("/sync", response_model=SyncResponse)
async def sync_portfolio(file: UploadFile = File(...)):
    """
    Sync portfolio from uploaded Excel file
    
    - **file**: Excel file exported from IntelliInvest
    
    Upload an Excel file to sync portfolio data to the database.
    """
    # Validate file type
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload an Excel file (.xlsx or .xls)"
        )
    
    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
        try:
            # Read file content
            content = await file.read()
            tmp_file.write(content)
            tmp_file_path = tmp_file.name
        
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error saving file: {str(e)}")
    
    try:
        # Sync portfolio
        result = sync_portfolio_from_intellinvest(tmp_file_path)
        
        # Convert as_of string to datetime if present
        if result.get("as_of") and isinstance(result["as_of"], str):
            from datetime import datetime
            result["as_of"] = datetime.fromisoformat(result["as_of"])
        
        return SyncResponse(**result)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error syncing portfolio: {str(e)}")
    
    finally:
        # Clean up temporary file
        if os.path.exists(tmp_file_path):
            os.unlink(tmp_file_path)


@app.post("/sync/path", response_model=SyncResponse)
def sync_portfolio_from_path(path: str):
    """
    Sync portfolio from file path (for testing/development)
    
    - **path**: Path to Excel file on server
    """
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    
    result = sync_portfolio_from_intellinvest(path)
    
    # Convert as_of string to datetime if present
    if result.get("as_of") and isinstance(result["as_of"], str):
        from datetime import datetime
        result["as_of"] = datetime.fromisoformat(result["as_of"])
    
    return SyncResponse(**result)


@app.post("/sync/public", response_model=SyncResponse)
def sync_portfolio_from_public(url: str):
    """
    Sync portfolio from IntelliInvest public portfolio URL
    
    - **url**: Public portfolio URL (e.g., https://intelinvest.ru/public-portfolio/757008/)
    
    Fetches data from the public portfolio page and syncs to database.
    """
    try:
        if not url or not url.startswith('http'):
            raise HTTPException(
                status_code=400,
                detail="Invalid URL. Please provide a valid IntelliInvest public portfolio URL"
            )
        
        if 'intelinvest.ru/public-portfolio' not in url:
            raise HTTPException(
                status_code=400,
                detail="URL must be an IntelliInvest public portfolio URL"
            )
        
        result = sync_portfolio_from_public_url(url)
        
        # Convert as_of string to datetime if present
        if result.get("as_of") and isinstance(result["as_of"], str):
            from datetime import datetime
            result["as_of"] = datetime.fromisoformat(result["as_of"])
        
        return SyncResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error syncing from public URL: {str(e)}"
        )


@app.post("/recommendations")
async def get_portfolio_recommendations():
    """
    Get AI-powered portfolio recommendations using OpenRouter API
    
    Analyzes the current portfolio and provides personalized recommendations.
    """
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
    # Use free model by default, can be overridden with OPENROUTER_MODEL env var
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.2-3b-instruct:free")
    
    if not OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="OPENROUTER_API_KEY environment variable is not set"
        )
    
    try:
        # Get portfolio data
        with Session(engine) as session:
            holdings = session.exec(select(Holding)).all()
            
            if not holdings:
                return JSONResponse({
                    "status": "error",
                    "message": "No portfolio data available. Please sync your portfolio first."
                })
            
            # Calculate statistics
            total_invested = sum(h.invested_value for h in holdings)
            total_current = sum(h.current_value for h in holdings)
            total_pnl = sum(h.pnl_value for h in holdings)
            total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0
            
            # Group by asset type
            by_asset_type = Counter(h.asset_type for h in holdings)
            by_asset_type_value = {}
            for holding in holdings:
                asset_type = holding.asset_type
                if asset_type not in by_asset_type_value:
                    by_asset_type_value[asset_type] = 0.0
                by_asset_type_value[asset_type] += holding.current_value
            
            # Group by currency
            by_currency_value = {}
            for holding in holdings:
                currency = holding.currency
                if currency not in by_currency_value:
                    by_currency_value[currency] = 0.0
                by_currency_value[currency] += holding.current_value
            
            # Get top holdings by value
            top_holdings = sorted(holdings, key=lambda h: h.current_value, reverse=True)[:10]
            
            # Prepare portfolio summary for LLM
            portfolio_summary = {
                "total_holdings": len(holdings),
                "total_invested": total_invested,
                "total_current": total_current,
                "total_pnl": total_pnl,
                "total_pnl_pct": total_pnl_pct,
                "asset_type_distribution": {
                    asset_type: {
                        "count": count,
                        "value": by_asset_type_value.get(asset_type, 0.0),
                        "percentage": round((by_asset_type_value.get(asset_type, 0.0) / total_current * 100) if total_current > 0 else 0, 1)
                    }
                    for asset_type, count in by_asset_type.items()
                },
                "currency_distribution": {
                    currency: {
                        "value": value,
                        "percentage": round((value / total_current * 100) if total_current > 0 else 0, 1)
                    }
                    for currency, value in by_currency_value.items()
                },
                "top_holdings": [
                    {
                        "ticker": h.ticker,
                        "name": h.name,
                        "asset_type": h.asset_type,
                        "currency": h.currency,
                        "quantity": h.qty,
                        "current_value": h.current_value,
                        "pnl_pct": h.pnl_pct,
                        "share_pct": h.share_pct
                    }
                    for h in top_holdings
                ]
            }
            
            # Create prompt for LLM
            prompt = f"""You are a financial advisor analyzing a portfolio. Based on the following portfolio data, provide actionable recommendations.

Portfolio Summary:
- Total Holdings: {portfolio_summary['total_holdings']}
- Total Invested: {portfolio_summary['total_invested']:.2f} RUB
- Current Value: {portfolio_summary['total_current']:.2f} RUB
- Total P&L: {portfolio_summary['total_pnl']:.2f} RUB ({portfolio_summary['total_pnl_pct']:.2f}%)

Asset Type Distribution:
{json.dumps(portfolio_summary['asset_type_distribution'], indent=2)}

Currency Distribution:
{json.dumps(portfolio_summary['currency_distribution'], indent=2)}

Top 10 Holdings by Value:
{json.dumps(portfolio_summary['top_holdings'], indent=2)}

Please provide:
1. Overall portfolio assessment (2-3 sentences)
2. Diversification analysis and recommendations
3. Risk assessment
4. Specific actionable recommendations (3-5 items)
5. Areas of concern or opportunities

Format your response in clear, concise bullet points. Be specific and actionable."""
            
            # Call OpenRouter API
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    OPENROUTER_API_URL,
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "http://localhost:8000",
                        "X-Title": "Portfolio Advisor"
                    },
                    json={
                        "model": OPENROUTER_MODEL,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are an experienced financial advisor specializing in portfolio analysis and investment recommendations. Provide clear, actionable advice."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "temperature": 0.7,
                        "max_tokens": 2000
                    }
                )
                
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=500,
                        detail=f"OpenRouter API error: {response.status_code} - {response.text}"
                    )
                
                result = response.json()
                recommendations = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                if not recommendations:
                    raise HTTPException(
                        status_code=500,
                        detail="No recommendations received from AI"
                    )
                
                return JSONResponse({
                    "status": "success",
                    "recommendations": recommendations
                })
                
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Request to AI service timed out. Please try again."
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error connecting to AI service: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating recommendations: {str(e)}"
        )


def fetch_stock_news(ticker: str, max_articles: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch recent news articles for a given stock ticker.
    Uses multiple sources to get comprehensive news coverage.
    """
    news_articles = []
    
    try:
        # Try Yahoo Finance RSS feed
        yahoo_rss_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
        
        try:
            feed = feedparser.parse(yahoo_rss_url)
            for entry in feed.entries[:max_articles]:
                news_articles.append({
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", ""),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "source": "Yahoo Finance"
                })
        except Exception as e:
            print(f"Error fetching Yahoo Finance RSS: {e}")
        
        # If we don't have enough articles, try Google News search
        if len(news_articles) < max_articles:
            try:
                google_news_url = f"https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en"
                feed = feedparser.parse(google_news_url)
                for entry in feed.entries[:max_articles - len(news_articles)]:
                    # Avoid duplicates
                    if not any(art["title"] == entry.get("title", "") for art in news_articles):
                        news_articles.append({
                            "title": entry.get("title", ""),
                            "summary": entry.get("summary", ""),
                            "link": entry.get("link", ""),
                            "published": entry.get("published", ""),
                            "source": "Google News"
                        })
            except Exception as e:
                print(f"Error fetching Google News: {e}")
        
        # Limit to max_articles
        news_articles = news_articles[:max_articles]
        
    except Exception as e:
        print(f"Error fetching news: {e}")
    
    return news_articles


@app.get("/news/{ticker}")
async def get_stock_news(ticker: str):
    """
    Get recent news articles for a stock ticker
    """
    try:
        news = fetch_stock_news(ticker.upper(), max_articles=10)
        return JSONResponse({
            "status": "success",
            "ticker": ticker.upper(),
            "articles": news,
            "count": len(news)
        })
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching news: {str(e)}"
        )


@app.post("/analyze-news/{ticker}")
async def analyze_stock_news(ticker: str):
    """
    Fetch news for a stock and analyze it using LLM to provide recommendations
    """
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
    # Use free model by default, can be overridden with OPENROUTER_MODEL env var
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.2-3b-instruct:free")
    
    if not OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="OPENROUTER_API_KEY environment variable is not set"
        )
    
    try:
        # Normalize ticker to uppercase
        ticker_upper = ticker.upper()
        
        # Get holding information
        with Session(engine) as session:
            # Try to find holding by ticker (case-insensitive search)
            holdings = session.exec(select(Holding)).all()
            holding = None
            for h in holdings:
                if h.ticker.upper() == ticker_upper:
                    holding = h
                    break
            
            if not holding:
                return JSONResponse(
                    status_code=404,
                    content={
                        "status": "error",
                        "message": f"Holding with ticker {ticker_upper} not found in portfolio. Available tickers: {', '.join([h.ticker for h in holdings[:10]])}"
                    }
                )
            
            # Fetch news
            news_articles = fetch_stock_news(ticker_upper, max_articles=10)
            
            if not news_articles:
                return JSONResponse({
                    "status": "error",
                    "message": f"No recent news found for {ticker_upper}. Please try again later."
                })
            
            # Prepare news summary for LLM
            news_summary = "\n\n".join([
                f"Article {i+1}:\n"
                f"Title: {article['title']}\n"
                f"Summary: {article.get('summary', 'No summary available')}\n"
                f"Source: {article.get('source', 'Unknown')}\n"
                f"Published: {article.get('published', 'Unknown')}"
                for i, article in enumerate(news_articles[:5])  # Use top 5 articles
            ])
            
            # Create prompt for LLM
            prompt = f"""You are a financial analyst. Analyze the following news articles about {ticker_upper} ({holding.name}) and provide actionable investment recommendations.

Current Portfolio Position:
- Ticker: {holding.ticker}
- Company: {holding.name}
- Quantity: {holding.qty}
- Average Price: {holding.avg_price} {holding.currency}
- Current Value: {holding.current_value} {holding.currency}
- P&L: {holding.pnl_value} {holding.currency} ({holding.pnl_pct:.2f}%)
- Share of Portfolio: {holding.share_pct:.2f}%

Recent News Articles:
{news_summary}

Please provide:
1. **Summary of News**: Brief overview of the key news and events (2-3 sentences)
2. **Sentiment Analysis**: Overall sentiment (positive/negative/neutral) with reasoning
3. **Key Risks**: Identify any risks or concerns mentioned in the news
4. **Key Opportunities**: Identify any opportunities or positive developments
5. **Action Recommendation**: Specific recommendation (Hold/Buy more/Sell/Reduce position) with reasoning
6. **Price Impact**: Expected short-term price impact based on the news
7. **Timeline**: When to review this position again

Format your response in clear markdown with headings and bullet points. Be specific and actionable."""
            
            # Call OpenRouter API
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    OPENROUTER_API_URL,
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "http://localhost:8000",
                        "X-Title": "Stock News Analyzer"
                    },
                    json={
                        "model": OPENROUTER_MODEL,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are an experienced financial analyst specializing in stock analysis and investment recommendations. Provide clear, actionable advice based on news analysis."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "temperature": 0.7,
                        "max_tokens": 2000
                    }
                )
                
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=500,
                        detail=f"OpenRouter API error: {response.status_code} - {response.text}"
                    )
                
                result = response.json()
                analysis = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                if not analysis:
                    raise HTTPException(
                        status_code=500,
                        detail="No analysis received from AI"
                    )
                
                return JSONResponse({
                    "status": "success",
                    "ticker": ticker_upper,
                    "holding": {
                        "ticker": holding.ticker,
                        "name": holding.name,
                        "current_value": holding.current_value,
                        "pnl_pct": holding.pnl_pct,
                        "share_pct": holding.share_pct
                    },
                    "news_count": len(news_articles),
                    "news_articles": news_articles,
                    "analysis": analysis
                })
                
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Request to AI service timed out. Please try again."
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error connecting to AI service: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error analyzing news: {str(e)}"
        )


# Global variable to track current batch job
current_batch_job_id = None
batch_job_lock = threading.Lock()


def extract_sentiment_from_analysis(analysis_text: str) -> str:
    """Extract sentiment from LLM analysis text"""
    if not analysis_text:
        return None
    
    # Look for sentiment patterns in the analysis
    text_lower = analysis_text.lower()
    
    # Check for explicit sentiment mentions
    if re.search(r'sentiment[:\s]*(positive|bullish|optimistic|favorable)', text_lower):
        return "positive"
    elif re.search(r'sentiment[:\s]*(negative|bearish|pessimistic|unfavorable)', text_lower):
        return "negative"
    elif re.search(r'sentiment[:\s]*(neutral|mixed)', text_lower):
        return "neutral"
    
    # Check for action recommendations that imply sentiment
    if re.search(r'(buy|buy more|increase|add)', text_lower):
        return "positive"
    elif re.search(r'(sell|reduce|decrease|exit)', text_lower):
        return "negative"
    elif re.search(r'(hold|maintain|keep)', text_lower):
        return "neutral"
    
    # Default to neutral if can't determine
    return "neutral"


async def analyze_holding_news(holding: Holding, batch_job_id: int):
    """Analyze news for a single holding and save to database"""
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
    # Use free model by default, can be overridden with OPENROUTER_MODEL env var
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.2-3b-instruct:free")
    
    if not OPENROUTER_API_KEY:
        error_msg = "OPENROUTER_API_KEY environment variable is not set"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    log_msg = f"🔄 Starting analysis for ticker: {holding.ticker.upper()} ({holding.name})"
    logger.info(log_msg)
    print(log_msg, flush=True)  # Also print to ensure immediate output
    
    with Session(engine) as session:
        # Create or update NewsAnalysis record
        analysis = session.exec(
            select(NewsAnalysis).where(NewsAnalysis.ticker == holding.ticker.upper())
        ).first()
        
        if not analysis:
            analysis = NewsAnalysis(
                ticker=holding.ticker.upper(),
                holding_id=holding.id,
                status="pending"
            )
            session.add(analysis)
        else:
            analysis.status = "pending"
            analysis.holding_id = holding.id
        
        session.commit()
        session.refresh(analysis)
        
        try:
            # Fetch news
            log_msg = f"📰 Fetching news for {holding.ticker.upper()}..."
            logger.info(log_msg)
            print(log_msg, flush=True)
            news_articles = fetch_stock_news(holding.ticker.upper(), max_articles=10)
            
            if not news_articles:
                log_msg = f"⚠️  No news found for {holding.ticker.upper()}"
                logger.warning(log_msg)
                print(log_msg, flush=True)
                analysis.status = "failed"
                analysis.error_message = f"No recent news found for {holding.ticker.upper()}"
                session.commit()
                return False
            
            log_msg = f"✅ Found {len(news_articles)} news articles for {holding.ticker.upper()}"
            logger.info(log_msg)
            print(log_msg, flush=True)
            
            # Prepare news summary for LLM
            news_summary = "\n\n".join([
                f"Article {i+1}:\n"
                f"Title: {article['title']}\n"
                f"Summary: {article.get('summary', 'No summary available')}\n"
                f"Source: {article.get('source', 'Unknown')}\n"
                f"Published: {article.get('published', 'Unknown')}"
                for i, article in enumerate(news_articles[:5])
            ])
            
            # Create prompt for LLM
            prompt = f"""You are a financial analyst. Analyze the following news articles about {holding.ticker.upper()} ({holding.name}) and provide actionable investment recommendations.

Current Portfolio Position:
- Ticker: {holding.ticker}
- Company: {holding.name}
- Quantity: {holding.qty}
- Average Price: {holding.avg_price} {holding.currency}
- Current Value: {holding.current_value} {holding.currency}
- P&L: {holding.pnl_value} {holding.currency} ({holding.pnl_pct:.2f}%)
- Share of Portfolio: {holding.share_pct:.2f}%

Recent News Articles:
{news_summary}

Please provide:
1. **Summary of News**: Brief overview of the key news and events (2-3 sentences)
2. **Sentiment Analysis**: Overall sentiment (positive/negative/neutral) with reasoning
3. **Key Risks**: Identify any risks or concerns mentioned in the news
4. **Key Opportunities**: Identify any opportunities or positive developments
5. **Action Recommendation**: Specific recommendation (Hold/Buy more/Sell/Reduce position) with reasoning
6. **Price Impact**: Expected short-term price impact based on the news
7. **Timeline**: When to review this position again

Format your response in clear markdown with headings and bullet points. Be specific and actionable."""
            
            # Call OpenRouter API
            log_msg = f"🤖 Sending news to LLM for {holding.ticker.upper()}..."
            logger.info(log_msg)
            print(log_msg, flush=True)
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    OPENROUTER_API_URL,
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "http://localhost:8000",
                        "X-Title": "Stock News Analyzer"
                    },
                    json={
                        "model": OPENROUTER_MODEL,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are an experienced financial analyst specializing in stock analysis and investment recommendations. Provide clear, actionable advice based on news analysis."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "temperature": 0.7,
                        "max_tokens": 2000
                    }
                )
                
                if response.status_code != 200:
                    raise Exception(f"OpenRouter API error: {response.status_code} - {response.text}")
                
                result = response.json()
                analysis_text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                if not analysis_text:
                    raise Exception("No analysis received from AI")
                
                log_msg = f"📝 Received LLM analysis for {holding.ticker.upper()} ({len(analysis_text)} characters)"
                logger.info(log_msg)
                print(log_msg, flush=True)
                
                # Extract sentiment from analysis text
                sentiment = extract_sentiment_from_analysis(analysis_text)
                log_msg = f"💭 LLM sentiment for {holding.ticker.upper()}: {sentiment.upper()}"
                logger.info(log_msg)
                print(log_msg, flush=True)
                
                # Save results
                analysis.status = "completed"
                analysis.news_count = len(news_articles)
                analysis.set_news_articles(news_articles)
                analysis.analysis = analysis_text
                analysis.sentiment = sentiment
                analysis.error_message = None
                session.commit()
                session.refresh(analysis)  # Refresh to ensure data is saved
                
                # Verify the save
                verify_analysis = session.get(NewsAnalysis, analysis.id)
                if verify_analysis and verify_analysis.sentiment:
                    log_msg = f"✅ Successfully saved analysis for {holding.ticker.upper()} with sentiment: {sentiment.upper()}"
                    logger.info(log_msg)
                    print(log_msg, flush=True)
                else:
                    log_msg = f"⚠️  Warning: Analysis saved but sentiment not verified for {holding.ticker.upper()}"
                    logger.warning(log_msg)
                    print(log_msg, flush=True)
                
                # Update batch job progress
                batch_job = session.get(BatchJob, batch_job_id)
                if batch_job:
                    batch_job.processed_holdings += 1
                    batch_job.successful_holdings += 1
                    session.commit()
                
                return True
                
        except Exception as e:
            error_msg = str(e)
            log_msg = f"❌ Error analyzing {holding.ticker.upper()}: {error_msg}"
            logger.error(log_msg)
            print(log_msg, flush=True)
            analysis.status = "failed"
            analysis.error_message = error_msg
            session.commit()
            
            # Update batch job progress
            batch_job = session.get(BatchJob, batch_job_id)
            if batch_job:
                batch_job.processed_holdings += 1
                batch_job.failed_holdings += 1
                session.commit()
            
            return False


def run_batch_analysis(batch_job_id: int):
    """Run batch analysis in background thread"""
    log_msg = f"🚀 Starting batch analysis job #{batch_job_id}"
    logger.info(log_msg)
    print(log_msg, flush=True)
    
    with Session(engine) as session:
        batch_job = session.get(BatchJob, batch_job_id)
        if not batch_job:
            logger.error(f"❌ Batch job #{batch_job_id} not found")
            return
        
        batch_job.status = "running"
        batch_job.started_at = datetime.now()
        session.commit()
        
        # Get all holdings with non-zero quantity
        holdings = session.exec(
            select(Holding).where(Holding.qty > 0.0001)
        ).all()
        
        batch_job.total_holdings = len(holdings)
        session.commit()
        
        log_msg = f"📊 Processing {len(holdings)} holdings in batch job #{batch_job_id}"
        logger.info(log_msg)
        print(log_msg, flush=True)
        
        # Process each holding
        for idx, holding in enumerate(holdings, 1):
            log_msg = f"📈 Processing [{idx}/{len(holdings)}] {holding.ticker.upper()} ({holding.name})"
            logger.info(log_msg)
            print(log_msg, flush=True)
            try:
                # Run async function in sync context
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                success = loop.run_until_complete(analyze_holding_news(holding, batch_job_id))
                loop.close()
            except Exception as e:
                log_msg = f"❌ Error processing {holding.ticker.upper()}: {e}"
                logger.error(log_msg)
                print(log_msg, flush=True)
                with Session(engine) as update_session:
                    update_batch_job = update_session.get(BatchJob, batch_job_id)
                    if update_batch_job:
                        update_batch_job.processed_holdings += 1
                        update_batch_job.failed_holdings += 1
                        update_session.commit()
        
        # Mark batch job as completed
        with Session(engine) as final_session:
            final_batch_job = final_session.get(BatchJob, batch_job_id)
            if final_batch_job:
                final_batch_job.status = "completed"
                final_batch_job.completed_at = datetime.now()
                final_session.commit()
                log_msg = f"✅ Batch job #{batch_job_id} completed. Processed: {final_batch_job.processed_holdings}/{final_batch_job.total_holdings}, Success: {final_batch_job.successful_holdings}, Failed: {final_batch_job.failed_holdings}"
                logger.info(log_msg)
                print(log_msg, flush=True)


@app.post("/batch-analyze-news")
async def start_batch_analysis(background_tasks: BackgroundTasks):
    """Start batch analysis for all non-zero holdings"""
    global current_batch_job_id
    
    with batch_job_lock:
        # Check if there's already a running batch job
        with Session(engine) as session:
            running_job = session.exec(
                select(BatchJob).where(BatchJob.status == "running")
            ).first()
            
            if running_job:
                return JSONResponse({
                    "status": "error",
                    "message": "Batch job is already running",
                    "job_id": running_job.id
                })
            
            # Create new batch job
            batch_job = BatchJob(
                status="pending",
                total_holdings=0,
                processed_holdings=0,
                successful_holdings=0,
                failed_holdings=0
            )
            session.add(batch_job)
            session.commit()
            session.refresh(batch_job)
            
            current_batch_job_id = batch_job.id
            
            # Start background task
            thread = threading.Thread(target=run_batch_analysis, args=(batch_job.id,))
            thread.daemon = True
            thread.start()
            
            return JSONResponse({
                "status": "success",
                "message": "Batch analysis started",
                "job_id": batch_job.id
            })


@app.get("/batch-analyze-news/status")
async def get_batch_status():
    """Get current batch job status"""
    with Session(engine) as session:
        # Get the most recent batch job
        batch_job = session.exec(
            select(BatchJob).order_by(BatchJob.created_at.desc())
        ).first()
        
        if not batch_job:
            return JSONResponse({
                "status": "no_job",
                "message": "No batch job found"
            })
        
        return JSONResponse({
            "status": "success",
            "job": {
                "id": batch_job.id,
                "status": batch_job.status,
                "created_at": batch_job.created_at.isoformat() if batch_job.created_at else None,
                "started_at": batch_job.started_at.isoformat() if batch_job.started_at else None,
                "completed_at": batch_job.completed_at.isoformat() if batch_job.completed_at else None,
                "total_holdings": batch_job.total_holdings,
                "processed_holdings": batch_job.processed_holdings,
                "successful_holdings": batch_job.successful_holdings,
                "failed_holdings": batch_job.failed_holdings,
                "error_message": batch_job.error_message,
                "progress_pct": round((batch_job.processed_holdings / batch_job.total_holdings * 100) if batch_job.total_holdings > 0 else 0, 1)
            }
        })


@app.get("/news-analysis/{ticker}")
async def get_news_analysis(ticker: str):
    """Get saved news analysis for a ticker"""
    with Session(engine) as session:
        analysis = session.exec(
            select(NewsAnalysis).where(NewsAnalysis.ticker == ticker.upper())
        ).first()
        
        if not analysis:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "error",
                    "message": f"No analysis found for {ticker.upper()}"
                }
            )
        
        return JSONResponse({
            "status": "success",
            "ticker": analysis.ticker,
            "created_at": analysis.created_at.isoformat(),
            "status": analysis.status,  # Use 'status' for consistency with frontend
            "analysis_status": analysis.status,  # Keep for backward compatibility
            "news_count": analysis.news_count,
            "news_articles": analysis.get_news_articles(),
            "analysis": analysis.analysis,
            "sentiment": analysis.sentiment,
            "error_message": analysis.error_message
        })

