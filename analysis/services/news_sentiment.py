"""
News Sentiment Analysis Service - Fetches and analyzes market news for trading signals.
Ported from standalone script with integration for Django system.
"""
import asyncio
import logging
import pickle
import time
from datetime import datetime
from typing import List, Dict, Optional

import aiohttp
import feedparser

from django.conf import settings

logger = logging.getLogger(__name__)

# News caching configuration
NEWS_CACHE_FILE = getattr(settings, 'NEWS_CACHE_FILE', 'news_cache.pkl')
NEWS_CACHE_DURATION = getattr(settings, 'NEWS_CACHE_DURATION', 3600)  # 1 hour

# API Keys
FINNHUB_API_KEY = getattr(settings, 'FINNHUB_API_KEY', '')


class NewsSentimentAnalyzer:
    """Handles news fetching and sentiment analysis for trading signals."""
    
    def __init__(self):
        self.cache_file = NEWS_CACHE_FILE
        self.cache_duration = NEWS_CACHE_DURATION
        self.last_fetch = 0
        
    def load_news_cache(self) -> Optional[List[Dict]]:
        """Load cached news if available and not expired."""
        try:
            import os
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'rb') as f:
                    cache_data = pickle.load(f)
                    cache_time = cache_data.get('timestamp', 0)
                    
                    # Check if cache is still valid
                    if time.time() - cache_time < self.cache_duration:
                        return cache_data.get('articles', [])
        except Exception as e:
            logger.error(f"Error loading news cache: {e}")
        return None
    
    def save_news_cache(self, articles: List[Dict]):
        """Save news articles to cache."""
        try:
            import os
            cache_data = {
                'timestamp': time.time(),
                'articles': articles
            }
            with open(self.cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
        except Exception as e:
            logger.error(f"Error saving news cache: {e}")
    
    async def fetch_market_news(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Enhanced market news fetching with SSL verification handling.
        Returns list of news articles with sentiment analysis.
        """
        try:
            # Check cache first
            cached_news = self.load_news_cache()
            if cached_news:
                logger.info("Using cached news articles")
                return cached_news
            
            # Check if Finnhub API key is available
            if not FINNHUB_API_KEY:
                logger.warning("FINNHUB_API_KEY not set, using fallback news")
                return self.get_fallback_news(symbol)
            
            # Create SSL context
            import ssl
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE  # Only for development
            
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            
            # Format symbol for API
            if symbol and symbol.startswith('frx'):
                formatted_symbol = f"{symbol[3:6]}_{symbol[6:]}"
            else:
                formatted_symbol = symbol or 'GENERAL'
            
            urls = [
                f"https://finnhub.io/api/v1/news?category=forex&token={FINNHUB_API_KEY}",
                f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_API_KEY}"
            ]
            
            all_articles = []
            
            async with aiohttp.ClientSession(connector=connector) as session:
                for url in urls:
                    try:
                        async with session.get(url, timeout=10) as response:
                            if response.status == 200:
                                news = await response.json()
                                if isinstance(news, list):
                                    all_articles.extend(news)
                            elif response.status == 401:
                                logger.error(f"Invalid Finnhub API key, using fallback news")
                                return self.get_fallback_news(symbol)
                    except Exception as e:
                        logger.error(f"Error fetching from {url}: {e}")
                        continue
                
                if not all_articles:
                    # Try RSS feeds with SSL context
                    feeds = [
                        'https://www.forexfactory.com/rss.php',
                        'https://www.investing.com/rss/forex.rss',
                        'https://www.fxstreet.com/rss'
                    ]
                    
                    for feed_url in feeds:
                        try:
                            async with session.get(feed_url, timeout=10) as response:
                                if response.status == 200:
                                    feed_content = await response.text()
                                    feed = feedparser.parse(feed_content)
                                    
                                    for entry in feed.entries[:5]:
                                        article = {
                                            'title': entry.get('title', ''),
                                            'description': entry.get('summary', ''),
                                            'url': entry.get('link', ''),
                                            'publishedAt': datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
                                            'content': entry.get('summary', '')
                                        }
                                        all_articles.append(article)
                        except Exception as e:
                            logger.error(f"Error fetching from RSS feed {feed_url}: {e}")
                            continue
            
            if all_articles:
                # Convert to standard format and add sentiment
                formatted_articles = []
                for article in all_articles:
                    if isinstance(article, dict):
                        sentiment = self.analyze_sentiment(article.get('summary', article.get('content', '')))
                        formatted_article = {
                            'title': article.get('headline', article.get('title', '')),
                            'description': article.get('summary', article.get('description', '')),
                            'url': article.get('url', ''),
                            'image': article.get('image', article.get('thumbnail', '')),
                            'category': article.get('category', 'general'),
                            'publishedAt': (
                                datetime.fromtimestamp(article.get('datetime', 0)).strftime('%Y-%m-%dT%H:%M:%SZ')
                                if article.get('datetime')
                                else datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
                            ),
                            'content': article.get('summary', article.get('content', '')),
                            'sentiment': sentiment,
                            'market_analysis': self.generate_market_analysis(article, sentiment, symbol)
                        }
                        formatted_articles.append(formatted_article)
                
                # Save to cache
                self.save_news_cache(formatted_articles)
                return formatted_articles
            
            # If all else fails, use fallback
            return self.get_fallback_news(symbol)
            
        except Exception as e:
            logger.error(f"Error in fetch_market_news: {e}")
            return self.get_fallback_news(symbol)
    
    def analyze_sentiment(self, text: str) -> float:
        """
        Analyze sentiment of text using simple keyword-based approach.
        Returns sentiment score between -1 (negative) and 1 (positive).
        """
        if not text:
            return 0.0
        
        # Simple keyword-based sentiment analysis
        positive_keywords = [
            'bullish', 'positive', 'growth', 'increase', 'rise', 'gain', 'profit',
            'strong', 'up', 'higher', 'better', 'good', 'excellent', 'rally'
        ]
        
        negative_keywords = [
            'bearish', 'negative', 'decline', 'decrease', 'fall', 'loss', 'drop',
            'weak', 'down', 'lower', 'worse', 'bad', 'poor', 'crash', 'sell'
        ]
        
        text_lower = text.lower()
        positive_count = sum(1 for keyword in positive_keywords if keyword in text_lower)
        negative_count = sum(1 for keyword in negative_keywords if keyword in text_lower)
        
        total = positive_count + negative_count
        if total == 0:
            return 0.0
        
        sentiment = (positive_count - negative_count) / total
        return sentiment
    
    def get_fallback_news(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Enhanced fallback news with market-specific content.
        """
        current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Determine market type from symbol
        if symbol:
            if symbol.startswith('frx'):
                market_type = 'forex'
            elif any(x in symbol for x in ["CRASH", "BOOM", "Jump", "STPRD"]):
                market_type = 'synthetic'
            elif any(x in symbol for x in ["R_", "1HZ"]):
                market_type = 'volatility'
            elif any(x in symbol.upper() for x in ["XAU", "GOLD", "XAG", "OIL", "WTI", "BRENT", "NATGAS"]):
                market_type = 'commodities'
            else:
                market_type = 'general'
        else:
            market_type = 'general'
        
        fallback_news = {
            'forex': [
                {
                    'title': 'Forex Market: Technical Analysis Update',
                    'description': 'Currency markets show mixed signals with major pairs consolidating.',
                    'url': 'https://example.com/forex-analysis',
                    'image': 'https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=400&h=300&fit=crop',
                    'category': 'forex',
                    'publishedAt': current_time,
                    'content': 'Major currency pairs are showing consolidation patterns with key technical levels being tested.',
                    'sentiment': 0.0,
                    'market_analysis': 'This medium impact news indicates neutral sentiment for forex. Traders should monitor for confirmation as this may have limited immediate impact.'
                }
            ],
            'synthetic': [
                {
                    'title': 'Synthetic Indices: Market Patterns Analysis',
                    'description': 'Technical patterns emerge in synthetic markets with volatility indicators showing key levels.',
                    'url': 'https://example.com/synthetic-analysis',
                    'image': 'https://images.unsplash.com/photo-1642543492481-44e81e3914a7?w=400&h=300&fit=crop',
                    'category': 'synthetic',
                    'publishedAt': current_time,
                    'content': 'Synthetic indices are displaying interesting technical patterns with multiple confirmation signals.',
                    'sentiment': 0.0,
                    'market_analysis': 'This medium impact news indicates neutral sentiment for indices. Traders should monitor for confirmation as this may have limited immediate impact.'
                }
            ],
            'volatility': [
                {
                    'title': 'Volatility Markets: Technical Signals Alert',
                    'description': 'Volatility indices show potential breakout patterns forming.',
                    'url': 'https://example.com/volatility-analysis',
                    'image': 'https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?w=400&h=300&fit=crop',
                    'category': 'volatility',
                    'publishedAt': current_time,
                    'content': 'Volatility markets are approaching key technical levels with momentum indicators aligned.',
                    'sentiment': 0.0,
                    'market_analysis': 'This medium impact news indicates neutral sentiment for indices. Traders should monitor for confirmation as this may have limited immediate impact.'
                }
            ],
            'commodities': [
                {
                    'title': 'Commodities: Gold & Precious Metals Update',
                    'description': 'Precious metals show technical levels with gold testing key support and resistance.',
                    'url': 'https://example.com/commodities-analysis',
                    'image': 'https://images.unsplash.com/photo-1611974765270-ca1258634369?w=400&h=300&fit=crop',
                    'category': 'commodities',
                    'publishedAt': current_time,
                    'content': 'Gold and commodities are displaying technical setups with sentiment and momentum indicators.',
                    'sentiment': 0.0,
                    'market_analysis': 'This medium impact news indicates neutral sentiment for commodities. Traders should monitor for confirmation as this may have limited immediate impact.'
                }
            ],
            'general': [
                {
                    'title': 'Market Analysis: Technical Indicators Update',
                    'description': 'General market analysis shows mixed signals across different assets.',
                    'url': 'https://example.com/market-analysis',
                    'image': 'https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?w=400&h=300&fit=crop',
                    'category': 'general',
                    'publishedAt': current_time,
                    'content': 'Markets are showing interesting technical setups with risk management remaining key.',
                    'sentiment': 0.0,
                    'market_analysis': 'This medium impact news indicates neutral sentiment for general. Traders should monitor for confirmation as this may have limited immediate impact.'
                }
            ]
        }
        
        return fallback_news.get(market_type, fallback_news['general'])
    
    def filter_news_by_sentiment(self, news: List[Dict], min_sentiment: float = 0.3) -> List[Dict]:
        """Filter news articles by minimum sentiment score."""
        return [article for article in news if abs(article.get('sentiment', 0)) >= min_sentiment]
    
    def get_overall_sentiment(self, news: List[Dict]) -> float:
        """Calculate overall sentiment from multiple news articles."""
        if not news:
            return 0.0
        
        sentiments = [article.get('sentiment', 0) for article in news]
        return sum(sentiments) / len(sentiments) if sentiments else 0.0
    
    def generate_market_analysis(self, article: Dict, sentiment: float, symbol: Optional[str] = None) -> str:
        """Generate market-specific analysis based on news article and sentiment."""
        title = article.get('headline', article.get('title', '')).lower()
        content = article.get('summary', article.get('description', '')).lower()
        
        # Determine market impact
        impact_keywords = {
            'high': ['crash', 'surge', 'spike', 'plunge', 'rally', 'breakthrough', 'collapse', 'emergency', 'crisis'],
            'medium': ['increase', 'decrease', 'rise', 'fall', 'growth', 'decline', 'report', 'data', 'announcement'],
            'low': ['update', 'comment', 'note', 'meeting', 'schedule']
        }
        
        impact = 'medium'
        for keyword in impact_keywords['high']:
            if keyword in title or keyword in content:
                impact = 'high'
                break
        else:
            for keyword in impact_keywords['low']:
                if keyword in title or keyword in content:
                    impact = 'low'
                    break
        
        # Determine affected markets
        affected_markets = []
        if any(x in title or x in content for x in ['forex', 'currency', 'dollar', 'euro', 'pound', 'yen']):
            affected_markets.append('forex')
        if any(x in title or x in content for x in ['gold', 'oil', 'commodity', 'metal', 'energy']):
            affected_markets.append('commodities')
        if any(x in title or x in content for x in ['stock', 'equity', 'index', 'market']):
            affected_markets.append('indices')
        if not affected_markets:
            affected_markets.append('general')
        
        # Generate analysis based on sentiment and impact
        if sentiment > 0.3:
            direction = 'bullish'
            action = 'consider long positions'
        elif sentiment < -0.3:
            direction = 'bearish'
            action = 'consider short positions or reduce exposure'
        else:
            direction = 'neutral'
            action = 'monitor for confirmation'
        
        analysis = f"This {impact} impact news indicates {direction} sentiment for {', '.join(affected_markets)}. "
        
        if impact == 'high':
            analysis += f"Traders should {action} and expect increased volatility. "
        elif impact == 'medium':
            analysis += f"Traders may {action} with moderate risk. "
        else:
            analysis += f"Traders should {action} as this may have limited immediate impact. "
        
        if symbol:
            analysis += f"Specifically for {symbol}, monitor for price reaction to this news."
        
        return analysis


# Global news sentiment analyzer instance
news_analyzer = NewsSentimentAnalyzer()
