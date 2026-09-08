/**
 * Test script for Market Data Service
 * Run this in browser console to test the service
 */
function testMarketDataService() {
    console.log('Testing Market Data Service...');
    
    if (!window.marketDataService) {
        console.error('Market data service not found');
        return;
    }
    
    const service = window.marketDataService;
    
    // Test 1: Connection status
    console.log('1. Connection status:', service.connected ? 'Connected' : 'Not connected');
    
    // Test 2: Current data
    console.log('2. Current data:', service.getCurrentData());
    
    // Test 3: Subscribe to price updates
    const unsubscribe = service.subscribe('price', function(price) {
        console.log('3. Price update received:', price);
    });
    
    // Test 4: Load historical data for a symbol
    service.loadHistoricalData('R_100', {
        granularity: 60,
        count: 10
    }).then(function(candles) {
        console.log('4. Historical data loaded:', candles.length, 'candles');
        console.log('   Latest candle:', candles[candles.length - 1]);
    }).catch(function(error) {
        console.error('4. Failed to load historical data:', error);
    });
    
    // Test 5: Change symbol
    setTimeout(function() {
        console.log('5. Changing symbol to R_50...');
        service.changeSymbol('R_50');
    }, 5000);
    
    // Cleanup after 10 seconds
    setTimeout(function() {
        unsubscribe();
        console.log('Test completed. Unsubscribed from price updates.');
    }, 10000);
}

// Run test when service is ready
if (window.marketDataService) {
    testMarketDataService();
} else {
    console.log('Waiting for market data service to load...');
    setTimeout(testMarketDataService, 2000);
}
