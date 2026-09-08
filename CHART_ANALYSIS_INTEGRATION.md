# Chart-to-Analysis Integration

## Overview
This integration enables the analysis backend to get market data directly from the browser TradingView chart instead of maintaining a separate WebSocket connection. This reduces redundancy and ensures the analysis uses the same data that users see on the chart.

## Architecture

### Before Integration
```
Browser Chart → Separate WebSocket → Deriv API
Analysis Backend → Separate WebSocket → Deriv API
(Live Signals Page → Separate WebSocket → Deriv API)
```
**Problem**: 3 separate WebSocket connections to the same API

### After Integration
```
Browser Chart → Centralized Market Data Service → Deriv API
                          ↓
                    WebSocket Consumer → Cache
                          ↓
                  Analysis Backend → Cache → Chart Data
```
**Solution**: Single WebSocket connection with data sharing

## Implementation Details

### 1. Centralized Market Data Service (`market_data_service.js`)
- Single WebSocket connection to Deriv API
- Subscription-based API for real-time updates
- Automatic reconnection and error handling
- Methods for loading historical data and managing symbol subscriptions
- Caching and state management for current market data

### 2. Enhanced WebSocket Consumer (`consumers.py`)
- Receives chart data from browser via WebSocket
- Stores chart data in Django cache for backend access
- Handles symbol changes and broadcasts updates
- Two consumer groups:
  - `ANALYSIS_GROUP`: For analysis updates
  - `CHART_DATA_GROUP`: For chart data synchronization

### 3. Updated Deriv Client (`deriv_client.py`)
- Modified `get_dataframe()` to check cache first
- Falls back to WebSocket buffer if chart data unavailable
- Maintains backward compatibility with existing system

### 4. Analysis Loop Enhancements (`run_analysis.py`)
- Prioritizes current chart symbol in analysis
- Logs data source (chart vs WebSocket) for debugging
- Maintains WebSocket feed as fallback for non-chart symbols

### 5. Frontend Integration (`index.html`)
- WebSocket connection to backend for real-time data transmission
- Automatic symbol change detection and notification
- Periodic chart data updates (every 5 seconds)
- Fallback HTTP endpoint for symbol changes

## Data Flow

### Chart Data Transmission
1. TradingView chart updates market data
2. Market data service receives updates via WebSocket
3. Frontend sends chart data to backend via WebSocket
4. Backend consumer stores data in cache
5. Analysis loop retrieves data from cache
6. Signal generation uses chart data

### Symbol Change Handling
1. User changes symbol in chart
2. Frontend detects change and sends to backend
3. Backend updates cache with current symbol
4. Analysis loop prioritizes current symbol
5. Other symbols continue to be analyzed in background

## Cache Structure

### Chart Data Cache
- **Key**: `chart_data_{symbol}`
- **Value**: 
  ```json
  {
    "symbol": "R_100",
    "price": 12345.67890,
    "candle": {...},
    "timestamp": "2026-08-25T22:15:32",
    "historical": [...]
  }
  ```
- **TTL**: 60 seconds

### Current Symbol Cache
- **Key**: `current_chart_symbol`
- **Value**: `"R_100"`
- **TTL**: 300 seconds

## Testing

### Manual Testing
1. Open browser console and run:
   ```javascript
   testIntegration()
   ```

2. Monitor integration:
   ```javascript
   monitorIntegration()
   ```

### Backend Logs
Look for these log messages to verify integration:
- `"Using chart data for {symbol} (from browser)"` - Chart data is being used
- `"Using WebSocket data for {symbol} (from server)"` - Fallback to WebSocket
- `"Prioritizing current chart symbol: {symbol}"` - Symbol prioritization working
- `"Chart data integration active"` - Integration is active

### Expected Behavior
1. Chart loads and connects to Deriv API
2. Market data service establishes connection
3. Analysis WebSocket connects to backend
4. Chart data is transmitted to backend
5. Backend logs show chart data usage
6. Analysis uses chart data for signal generation

## Benefits

1. **Reduced Redundancy**: Single WebSocket connection instead of multiple
2. **Data Consistency**: Analysis uses same data as displayed on chart
3. **Better Performance**: Reduced API load and network overhead
4. **User Experience**: Analysis reflects what user sees on chart
5. **Maintainability**: Centralized data management
6. **Fallback Support**: System still works if chart integration fails

## Troubleshooting

### Chart Data Not Reaching Backend
- Check browser console for WebSocket errors
- Verify analysis WebSocket connection status
- Check backend logs for consumer errors
- Ensure cache backend is configured properly

### Analysis Still Using WebSocket Data
- Check if chart data is being cached properly
- Verify cache key format matches expectations
- Check cache TTL settings
- Look for "Using chart data" logs in backend

### Symbol Changes Not Detected
- Check frontend symbol change detection logic
- Verify WebSocket message format
- Check backend symbol change handler
- Ensure cache is being updated

## Configuration

### Required Settings
```python
# settings.py
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
```

### Optional Settings
```python
# Analysis interval
ANALYSIS_INTERVAL_SECONDS = 30

# Deriv API settings
DERIV_APP_ID = '1089'
DERIV_API_TOKEN = None  # For public access
```

## Future Enhancements

1. **Real-time Bidirectional Sync**: Full two-way data synchronization
2. **Multiple Chart Support**: Handle multiple chart instances
3. **Advanced Caching**: Implement cache warming and preloading
4. **Performance Monitoring**: Add metrics for data flow
5. **Error Recovery**: Enhanced fallback mechanisms
