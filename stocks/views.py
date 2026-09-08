from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import requests
import json
from datetime import datetime, timedelta
import random

from dashboard.context import base_context


def stocks_page(request):
    """Stocks page with TradingView integration for stock market analysis."""
    ctx = base_context(active_nav="stocks")
    ctx.update({
        'default_symbol': request.GET.get('symbol', 'AAPL'),
        'default_exchange': request.GET.get('exchange', 'NASDAQ'),
    })
    return render(request, "stocks/stocks.html", ctx)


@csrf_exempt
def analyze_gaps(request):
    """API endpoint to analyze stock gaps for a given symbol."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        symbol = data.get('symbol', 'AAPL')
        exchange = data.get('exchange', 'NASDAQ')
        
        # Fetch historical data from TradingView or similar API
        # For now, we'll simulate gap analysis with sample data
        gaps = detect_gaps(symbol, exchange)
        
        return JsonResponse({
            'success': True,
            'symbol': symbol,
            'exchange': exchange,
            'gaps': gaps,
            'gap_stats': calculate_gap_stats(gaps)
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def get_stock_ticker(request):
    """API endpoint to get stock ticker data."""
    try:
        # In production, this would fetch real data from an API like Alpha Vantage, IEX, etc.
        # For now, we'll simulate ticker data
        ticker_data = get_simulated_ticker_data()
        
        return JsonResponse({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'stocks': ticker_data
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def get_simulated_ticker_data():
    """Generate simulated stock ticker data."""
    popular_stocks = [
        {'symbol': 'AAPL', 'name': 'Apple Inc.', 'base_price': 175.50},
        {'symbol': 'GOOGL', 'name': 'Alphabet Inc.', 'base_price': 135.25},
        {'symbol': 'MSFT', 'name': 'Microsoft Corp.', 'base_price': 330.75},
        {'symbol': 'TSLA', 'name': 'Tesla Inc.', 'base_price': 245.80},
        {'symbol': 'AMZN', 'name': 'Amazon.com Inc.', 'base_price': 145.30},
        {'symbol': 'META', 'name': 'Meta Platforms Inc.', 'base_price': 305.20},
        {'symbol': 'NVDA', 'name': 'NVIDIA Corp.', 'base_price': 460.15},
        {'symbol': 'JPM', 'name': 'JPMorgan Chase & Co.', 'base_price': 155.40},
        {'symbol': 'V', 'name': 'Visa Inc.', 'base_price': 250.85},
        {'symbol': 'JNJ', 'name': 'Johnson & Johnson', 'base_price': 160.25},
        {'symbol': 'WMT', 'name': 'Walmart Inc.', 'base_price': 165.30},
        {'symbol': 'PG', 'name': 'Procter & Gamble Co.', 'base_price': 155.90},
    ]
    
    ticker_data = []
    for stock in popular_stocks:
        # Simulate price movement
        price_change = random.uniform(-2.5, 2.5)
        current_price = stock['base_price'] + price_change
        change_percent = (price_change / stock['base_price']) * 100
        
        ticker_data.append({
            'symbol': stock['symbol'],
            'name': stock['name'],
            'price': round(current_price, 2),
            'change': round(price_change, 2),
            'change_percent': round(change_percent, 2),
            'volume': random.randint(1000000, 50000000),
            'high': round(current_price + random.uniform(0.5, 2.0), 2),
            'low': round(current_price - random.uniform(0.5, 2.0), 2),
        })
    
    return ticker_data


def detect_gaps(symbol, exchange):
    """Detect gaps in stock price data."""
    # This is a placeholder implementation
    # In production, you would fetch real historical data from an API
    # and analyze it for gaps
    
    # Simulated gap data
    return [
        {
            'date': '2026-09-01',
            'type': 'gap_up',
            'previous_close': 150.25,
            'open': 152.50,
            'gap_size': 1.50,
            'gap_percentage': 1.0,
            'filled': False,
            'fill_date': None
        },
        {
            'date': '2026-08-28',
            'type': 'gap_down',
            'previous_close': 148.75,
            'open': 146.50,
            'gap_size': -2.25,
            'gap_percentage': -1.5,
            'filled': True,
            'fill_date': '2026-08-30'
        },
        {
            'date': '2026-08-25',
            'type': 'gap_up',
            'previous_close': 145.00,
            'open': 147.25,
            'gap_size': 2.25,
            'gap_percentage': 1.55,
            'filled': True,
            'fill_date': '2026-08-26'
        }
    ]


def calculate_gap_stats(gaps):
    """Calculate statistics for detected gaps."""
    if not gaps:
        return {}
    
    total_gaps = len(gaps)
    gap_ups = len([g for g in gaps if g['type'] == 'gap_up'])
    gap_downs = len([g for g in gaps if g['type'] == 'gap_down'])
    filled_gaps = len([g for g in gaps if g['filled']])
    
    avg_gap_size = sum([abs(g['gap_size']) for g in gaps]) / total_gaps
    avg_gap_percentage = sum([abs(g['gap_percentage']) for g in gaps]) / total_gaps
    
    fill_rate = (filled_gaps / total_gaps) * 100 if total_gaps > 0 else 0
    
    return {
        'total_gaps': total_gaps,
        'gap_ups': gap_ups,
        'gap_downs': gap_downs,
        'filled_gaps': filled_gaps,
        'unfilled_gaps': total_gaps - filled_gaps,
        'fill_rate': round(fill_rate, 2),
        'avg_gap_size': round(avg_gap_size, 2),
        'avg_gap_percentage': round(avg_gap_percentage, 2)
    }
