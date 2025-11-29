from datetime import datetime
from sqlmodel import SQLModel, Field
from typing import Optional
import json


class Holding(SQLModel, table=True):
    """Model for portfolio holdings"""
    id: Optional[int] = Field(default=None, primary_key=True)
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


class NewsAnalysis(SQLModel, table=True):
    """Model for storing news analysis results"""
    id: Optional[int] = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    holding_id: Optional[int] = Field(default=None, foreign_key="holding.id")
    created_at: datetime = Field(default_factory=datetime.now)
    status: str = Field(default="pending")  # pending, completed, failed
    news_count: int = Field(default=0)
    news_articles: str = Field(default="[]")  # JSON string of articles
    analysis: Optional[str] = Field(default=None)  # LLM analysis text
    sentiment: Optional[str] = Field(default=None)  # positive, negative, neutral
    error_message: Optional[str] = Field(default=None)
    
    def get_news_articles(self) -> list:
        """Parse news_articles JSON string to list"""
        try:
            return json.loads(self.news_articles) if self.news_articles else []
        except:
            return []
    
    def set_news_articles(self, articles: list):
        """Set news_articles as JSON string"""
        self.news_articles = json.dumps(articles, ensure_ascii=False)


class BatchJob(SQLModel, table=True):
    """Model for tracking batch job status"""
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    status: str = Field(default="pending")  # pending, running, completed, failed
    total_holdings: int = Field(default=0)
    processed_holdings: int = Field(default=0)
    successful_holdings: int = Field(default=0)
    failed_holdings: int = Field(default=0)
    error_message: Optional[str] = Field(default=None)

