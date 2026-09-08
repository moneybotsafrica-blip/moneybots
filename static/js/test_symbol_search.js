/*
 * Test script for symbol search functionality
 * This script can be loaded in the browser console to test the symbol search
 */

// Test the enhanced symbol search
async function testSymbolSearch() {
    console.log('Testing Symbol Search Functionality');
    console.log('=====================================');
    
    // Simulate the datafeed structure
    const testDatafeed = {
        appId: 1089,
        ws: null,
        reqId: 1,
        pending: {},
        connected: false,
        activeSymbols: [],
        activeSymbolsLoaded: false,
        
        async send(req) {
            // Mock implementation for testing
            console.log('Mock send request:', req);
            return new Promise(resolve => {
                // Simulate trading_times response
                if (req.trading_times) {
                    resolve({
                        trading_times: {
                            markets: [
                                {
                                    name: 'Volatility Indices',
                                    submarkets: [
                                        {
                                            name: 'Volatility 10',
                                            symbols: [
                                                { symbol: 'R_10', name: 'Volatility 10 Index', feed_license: 'realtime' },
                                                { symbol: 'R_25', name: 'Volatility 25 Index', feed_license: 'realtime' }
                                            ]
                                        }
                                    ]
                                },
                                {
                                    name: 'Derived',
                                    submarkets: [
                                        {
                                            name: 'Boom/Crash',
                                            symbols: [
                                                { symbol: 'BOOM1000', name: 'Boom 1000 Index', feed_license: 'realtime' },
                                                { symbol: 'CRASH1000', name: 'Crash 1000 Index', feed_license: 'realtime' }
                                            ]
                                        }
                                    ]
                                }
                            ]
                        }
                    });
                } else if (req.active_symbols) {
                    resolve({
                        active_symbols: [
                            { symbol: 'R_100', display_name: 'Volatility 100 Index', symbol_type: 'index' },
                            { symbol: 'BOOM1000', display_name: 'Boom 1000 Index', symbol_type: 'index' }
                        ]
                    });
                } else {
                    resolve({});
                }
            });
        },
        
        async fetchActiveSymbols() {
            if (this.activeSymbolsLoaded) {
                return this.activeSymbols;
            }

            try {
                const date = new Date().toISOString().slice(0, 10);
                const data = await this.send({ trading_times: date });
                const markets = data.trading_times?.markets || [];
                
                // Enhanced symbol extraction with comprehensive market coverage
                this.activeSymbols = markets.flatMap(market => {
                    const marketName = market.name || 'Unknown';
                    return (market.submarkets || []).flatMap(submarket => {
                        const submarketName = submarket.name || 'Unknown';
                        return (submarket.symbols || [])
                            .filter(item => item.symbol && item.feed_license !== 'chartonly')
                            .map(item => ({
                                symbol: item.symbol,
                                full_name: item.symbol,
                                ticker: item.symbol,
                                description: item.name || item.symbol,
                                exchange: 'DERIV',
                                type: marketName,
                                market: marketName,
                                submarket: submarketName,
                                display_name: item.display_name || item.name,
                            }));
                    });
                }).sort((a, b) => a.description.localeCompare(b.description));
                
                if (this.activeSymbols.length) {
                    this.activeSymbolsLoaded = true;
                    console.log('Loaded', this.activeSymbols.length, 'Deriv chart symbols from trading_times');
                    console.log('Markets covered:', [...new Set(this.activeSymbols.map(s => s.market))].join(', '));
                    return this.activeSymbols;
                }
            } catch (error) {
                console.warn('Deriv trading_times catalogue is unavailable:', error);
            }

            // Fallback
            try {
                const data = await this.send({ active_symbols: 'brief' });
                this.activeSymbols = (data.active_symbols || [])
                    .filter(s => (s.underlying_symbol || s.symbol) && !s.is_trading_suspended)
                    .map(s => {
                        const symbol = s.underlying_symbol || s.symbol;
                        return { 
                            symbol, 
                            full_name: symbol, 
                            ticker: symbol,
                            description: s.underlying_symbol_name || s.display_name || symbol,
                            exchange: 'DERIV', 
                            type: s.underlying_symbol_type || s.symbol_type || s.market || 'cfd',
                            market: s.market || 'Unknown',
                            display_name: s.display_name || s.underlying_symbol_name || symbol,
                        };
                    });
                if (this.activeSymbols.length) {
                    this.activeSymbolsLoaded = true;
                    console.log('Loaded', this.activeSymbols.length, 'Deriv chart symbols from active_symbols fallback');
                }
                return this.activeSymbols;
            } catch (error) {
                console.warn('Deriv active-symbol fallback is unavailable:', error);
            }
            return [];
        },
        
        async searchSymbols(userInput, exchange, symbolType, onResultReadyCallback) {
            console.log('Searching symbols:', userInput, 'exchange:', exchange, 'type:', symbolType);
            
            const allSymbols = await this.fetchActiveSymbols();
            console.log('Total symbols available for search:', allSymbols.length);
            
            if (allSymbols.length === 0) {
                console.log('Using fallback symbols due to API failure');
                const fallbackSymbols = [
                    { symbol: 'R_100', full_name: 'R_100', description: 'Volatility 100 Index', exchange: 'DERIV', type: 'Volatility Indices' },
                    { symbol: 'R_75', full_name: 'R_75', description: 'Volatility 75 Index', exchange: 'DERIV', type: 'Volatility Indices' },
                ];
                
                const filtered = fallbackSymbols.filter(s => 
                    s.symbol.toLowerCase().includes(userInput.toLowerCase()) ||
                    s.description.toLowerCase().includes(userInput.toLowerCase()) ||
                    s.type.toLowerCase().includes(userInput.toLowerCase())
                );
                
                console.log('Fallback search results:', filtered.length);
                onResultReadyCallback(filtered);
                return;
            }
            
            const searchLower = (userInput || '').toLowerCase();
            const filtered = allSymbols.filter(s => {
                const matchesSymbol = s.symbol.toLowerCase().includes(searchLower);
                const matchesDescription = s.description.toLowerCase().includes(searchLower);
                const matchesType = s.type && s.type.toLowerCase().includes(searchLower);
                const matchesMarket = s.market && s.market.toLowerCase().includes(searchLower);
                const matchesSubmarket = s.submarket && s.submarket.toLowerCase().includes(searchLower);
                
                return matchesSymbol || matchesDescription || matchesType || matchesMarket || matchesSubmarket;
            });
            
            let finalResults = filtered;
            if (exchange && exchange !== 'DERIV') {
                finalResults = finalResults.filter(s => s.exchange === exchange);
            }
            if (symbolType) {
                finalResults = finalResults.filter(s => 
                    s.type === symbolType || 
                    s.market === symbolType ||
                    s.submarket === symbolType
                );
            }
            
            console.log('Search filtered results:', finalResults.length);
            console.log('Sample results:', finalResults.slice(0, 5));
            
            onResultReadyCallback(finalResults);
        }
    };
    
    // Test different search scenarios
    console.log('\nTest 1: Search for "R_"');
    await testDatafeed.searchSymbols('R_', '', '', (results) => {
        console.log('Results for "R_":', results);
    });
    
    console.log('\nTest 2: Search for "Volatility"');
    await testDatafeed.searchSymbols('Volatility', '', '', (results) => {
        console.log('Results for "Volatility":', results);
    });
    
    console.log('\nTest 3: Search for "Boom" (market)');
    await testDatafeed.searchSymbols('Boom', '', '', (results) => {
        console.log('Results for "Boom":', results);
    });
    
    console.log('\nTest 4: Search with type filter');
    await testDatafeed.searchSymbols('', '', 'Volatility Indices', (results) => {
        console.log('Results with type filter "Volatility Indices":', results);
    });
    
    console.log('\n=====================================');
    console.log('Symbol Search Test Complete');
}

// Run the test
testSymbolSearch().catch(console.error);