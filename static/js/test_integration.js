/**
 * Integration test for chart-to-analysis data flow
 * This script tests that the analysis page can get market data from the chart
 */
function testChartAnalysisIntegration() {
    console.log('=== Testing Chart-to-Analysis Integration ===');
    
    // Test 1: Check if market data service is available
    if (!window.marketDataService) {
        console.error('❌ Market data service not available');
        return;
    }
    console.log('✅ Market data service is available');
    
    // Test 2: Check if TradingView chart variables are available
    if (window.currentChartSymbol) {
        console.log('✅ Chart symbol available:', window.currentChartSymbol);
    } else {
        console.log('⚠️ Chart symbol not yet set (waiting for chart initialization)');
    }
    
    if (window.currentChartPrice) {
        console.log('✅ Chart price available:', window.currentChartPrice);
    } else {
        console.log('⚠️ Chart price not yet set (waiting for chart initialization)');
    }
    
    // Test 3: Check market data service connection
    const service = window.marketDataService;
    console.log('Service connection status:', service.connected ? '✅ Connected' : '❌ Not connected');
    
    // Test 4: Get current data from service
    const currentData = service.getCurrentData();
    console.log('Current data from service:', currentData);
    
    // Test 5: Test backend endpoint
    if (window.currentChartSymbol) {
        fetch('/api/analysis/current-symbol/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ symbol: window.currentChartSymbol })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                console.log('✅ Backend endpoint working:', data);
            } else {
                console.error('❌ Backend endpoint error:', data);
            }
        })
        .catch(error => {
            console.error('❌ Backend endpoint failed:', error);
        });
    }
    
    // Test 6: Subscribe to price updates
    const unsubscribe = service.subscribe('price', function(price) {
        console.log('✅ Price update received:', price);
    });
    
    console.log('=== Integration Test Complete ===');
    console.log('Note: Some tests may show warnings until chart is fully initialized');
    
    // Cleanup after 10 seconds
    setTimeout(function() {
        unsubscribe();
        console.log('Test cleanup completed');
    }, 10000);
}

// Run test when page is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', testChartAnalysisIntegration);
} else {
    testChartAnalysisIntegration();
}
