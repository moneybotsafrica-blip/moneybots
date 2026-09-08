/*
 * TradingView Advanced Charts implementation for Deriv
 * Uses the TradingView Charting Library with Deriv WebSocket datafeed
 */
(function () {
    window.initTradingViewChart = function ({ containerId, defaultSymbol }) {
        const container = document.getElementById(containerId);
        if (!container || typeof TradingView === 'undefined') return null;

        function formatSymbol(sym) {
            // Internal symbol names are already in correct Deriv API format
            return sym;
        }

        // Deriv Datafeed implementation
        class DerivDatafeed {
            constructor() {
                this.appId = window.DERIV_APP_ID || 1089;
                this.apiToken = window.DERIV_API_TOKEN || null;
                this.ws = null;
                this.reqId = 1;
                this.pending = {};
                this.subscriptions = new Set();
                this.connected = false;
                this.connectionPromise = null;
                this.currentCandle = null; // Track current candle for tick updates
                this.currentSymbol = null;
                this.authorized = false;
                this.activeSymbols = []; // Cache of active symbols from API
                this.activeSymbolsLoaded = false;
            }

            onReady(callback) {
                console.log('Datafeed onReady called');
                setTimeout(() => callback({
                    supports_time: true,
                    supports_marks: false,
                    supports_time_scale: true,
                    supported_resolutions: ['1', '5', '15', '30', '60', '240', 'D'],
                    supports_search: true,
                    supports_group_request: false,
                    // Symbol types for all available Deriv markets
                    symbolsTypes: [
                        { name: "Volatility Indices", value: "Volatility Indices" },
                        { name: "Crash/Boom Indices", value: "Derived" },
                        { name: "Jump Indices", value: "Derived" },
                        { name: "Step Indices", value: "Derived" },
                        { name: "Range Indices", value: "Derived" },
                        { name: "Forex Baskets", value: "Forex Baskets" },
                        { name: "Cryptocurrencies", value: "Cryptocurrencies" },
                        { name: "Forex", value: "Forex" },
                        { name: "Commodities", value: "Commodities" },
                        { name: "Indices", value: "Indices" },
                    ],
                    exchanges: [
                        { name: "DERIV", value: "DERIV" },
                    ],
                }), 0);
                
                // Pre-load active symbols in background
                this.fetchActiveSymbols().catch(console.error);
            }

            resolveSymbol(symbolName, onSymbolResolvedCallback, onResolveErrorCallback) {
                console.log('Resolving symbol:', symbolName);
                const symbol = formatSymbol(symbolName);
                
                // Determine symbol type and appropriate settings
                let symbolType = 'cfd';
                let session = '24x7';
                let pricescale = 10000;
                let minmov = 1;
                let description = symbol;
                let timezone = 'Etc/UTC';
                
                // Adjust settings based on symbol patterns
                if (symbol.startsWith('R_') || symbol.startsWith('1HZ')) {
                    symbolType = 'Volatility Indices';
                    pricescale = 10000;
                } else if (symbol.startsWith('BOOM') || symbol.startsWith('CRASH')) {
                    symbolType = 'Derived';
                    pricescale = 10000;
                } else if (symbol.startsWith('JD')) {
                    symbolType = 'Derived';
                    pricescale = 10000;
                } else if (symbol.startsWith('stpRNG') || symbol.startsWith('RB')) {
                    symbolType = 'Derived';
                    pricescale = 10000;
                } else if (symbol.startsWith('frxXAU') || symbol.startsWith('frxXAG')) {
                    symbolType = 'Commodities';
                    session = '24x5';
                    timezone = 'America/New_York';
                    pricescale = 100;
                    description = symbol.startsWith('frxXAU') ? 'Gold/USD' : 'Silver/USD';
                } else if (symbol.startsWith('frx')) {
                    symbolType = 'Forex';
                    session = '24x5';
                    timezone = 'America/New_York';
                    const pair = symbol.substring(3);
                    description = pair.replace(/([A-Z]{3})([A-Z]{3})/, '$1/$2');
                    pricescale = pair.includes('JPY') ? 1000 : 100000;
                } else if (symbol.startsWith('cry')) {
                    symbolType = 'Cryptocurrencies';
                    pricescale = 100;
                } else if (symbol.startsWith('WLD')) {
                    symbolType = 'Forex Baskets';
                    pricescale = 10000;
                } else if (symbol.startsWith('OTC_')) {
                    symbolType = 'Indices';
                    pricescale = 100;
                    session = '0900-1630';
                    timezone = 'America/New_York';
                }
                
                console.log('Symbol resolved:', { symbol, symbolType, pricescale, session, description });
                
                setTimeout(() => onSymbolResolvedCallback({
                    name: symbol,
                    ticker: symbol,
                    full_name: symbol,
                    description: description,
                    type: symbolType,
                    session: session,
                    timezone: timezone,
                    exchange: 'DERIV',
                    listed_exchange: 'DERIV',
                    minmov: minmov,
                    pricescale: pricescale,
                    has_intraday: true,
                    has_daily: true,
                    has_no_volume: true,
                    has_empty_bars: false,
                    supported_resolutions: ['1', '5', '15', '30', '60', '240', 'D'],
                    intraday_multipliers: ['1', '5', '15', '30', '60', '240'],
                    data_status: 'streaming',
                    visible_plots_count: 1,
                }), 0);
            }

            async fetchActiveSymbols() {
                if (this.activeSymbolsLoaded) {
                    return this.activeSymbols;
                }

                try {
                    // This matches the Deriv datafeed bundled in the supplied
                    // library: trading_times contains the complete chartable
                    // market tree, unlike active_symbols which can be empty
                    // for public app IDs.
                    const date = new Date().toISOString().slice(0, 10);
                    const data = await this.send({ trading_times: date });
                    const markets = data.trading_times?.markets || [];
                    
                    // Enhanced symbol extraction with comprehensive market coverage
                    this.activeSymbols = markets.flatMap(market => {
                        const marketName = market.name || 'Unknown';
                        return (market.submarkets || []).flatMap(submarket => {
                            const submarketName = submarket.name || 'Unknown';
                            return (submarket.symbols || [])
                                .filter(item => item.symbol)
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
                        if (window.marketDataService) {
                            window.marketDataService.setChartSymbols(this.activeSymbols);
                        }
                        return this.activeSymbols;
                    }
                } catch (error) {
                    console.warn('Deriv trading_times catalogue is unavailable:', error);
                }

                // Keep the API migration fallback for sessions where Deriv
                // temporarily does not provide trading_times.
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
                        if (window.marketDataService) {
                            window.marketDataService.setChartSymbols(this.activeSymbols);
                        }
                    }
                    return this.activeSymbols;
                } catch (error) {
                    console.warn('Deriv active-symbol fallback is unavailable:', error);
                }
                return [];
            }

            async searchSymbols(userInput, exchange, symbolType, onResultReadyCallback) {
                console.log('Searching symbols:', userInput, 'exchange:', exchange, 'type:', symbolType);
                
                // Fetch active symbols from API (like official Deriv charts)
                const allSymbols = await this.fetchActiveSymbols();
                console.log('Total symbols available for search:', allSymbols.length);
                
                if (allSymbols.length === 0) {
                    console.log('Using fallback symbols due to API failure');
                    // Fallback with verified Deriv symbols from public API
                    const fallbackSymbols = [
                        // Volatility Indices
                        { symbol: 'R_10', full_name: 'R_10', description: 'Volatility 10 Index', exchange: 'DERIV', type: 'Volatility Indices' },
                        { symbol: 'R_25', full_name: 'R_25', description: 'Volatility 25 Index', exchange: 'DERIV', type: 'Volatility Indices' },
                        { symbol: 'R_50', full_name: 'R_50', description: 'Volatility 50 Index', exchange: 'DERIV', type: 'Volatility Indices' },
                        { symbol: 'R_75', full_name: 'R_75', description: 'Volatility 75 Index', exchange: 'DERIV', type: 'Volatility Indices' },
                        { symbol: 'R_100', full_name: 'R_100', description: 'Volatility 100 Index', exchange: 'DERIV', type: 'Volatility Indices' },
                        // 1-Second Volatility Indices
                        { symbol: '1HZ10V', full_name: '1HZ10V', description: 'Volatility 10 (1s) Index', exchange: 'DERIV', type: 'Volatility Indices' },
                        { symbol: '1HZ15V', full_name: '1HZ15V', description: 'Volatility 15 (1s) Index', exchange: 'DERIV', type: 'Volatility Indices' },
                        { symbol: '1HZ25V', full_name: '1HZ25V', description: 'Volatility 25 (1s) Index', exchange: 'DERIV', type: 'Volatility Indices' },
                        { symbol: '1HZ30V', full_name: '1HZ30V', description: 'Volatility 30 (1s) Index', exchange: 'DERIV', type: 'Volatility Indices' },
                        { symbol: '1HZ50V', full_name: '1HZ50V', description: 'Volatility 50 (1s) Index', exchange: 'DERIV', type: 'Volatility Indices' },
                        { symbol: '1HZ75V', full_name: '1HZ75V', description: 'Volatility 75 (1s) Index', exchange: 'DERIV', type: 'Volatility Indices' },
                        { symbol: '1HZ90V', full_name: '1HZ90V', description: 'Volatility 90 (1s) Index', exchange: 'DERIV', type: 'Volatility Indices' },
                        { symbol: '1HZ100V', full_name: '1HZ100V', description: 'Volatility 100 (1s) Index', exchange: 'DERIV', type: 'Volatility Indices' },
                        // Boom/Crash Indices
                        { symbol: 'BOOM1000', full_name: 'BOOM1000', description: 'Boom 1000 Index', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'BOOM150N', full_name: 'BOOM150N', description: 'Boom 150 Index', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'BOOM300N', full_name: 'BOOM300N', description: 'Boom 300 Index', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'BOOM50', full_name: 'BOOM50', description: 'Boom 50 Index', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'BOOM500', full_name: 'BOOM500', description: 'Boom 500 Index', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'BOOM600', full_name: 'BOOM600', description: 'Boom 600 Index', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'BOOM900', full_name: 'BOOM900', description: 'Boom 900 Index', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'CRASH1000', full_name: 'CRASH1000', description: 'Crash 1000 Index', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'CRASH150N', full_name: 'CRASH150N', description: 'Crash 150 Index', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'CRASH300N', full_name: 'CRASH300N', description: 'Crash 300 Index', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'CRASH50', full_name: 'CRASH50', description: 'Crash 50 Index', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'CRASH500', full_name: 'CRASH500', description: 'Crash 500 Index', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'CRASH600', full_name: 'CRASH600', description: 'Crash 600 Index', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'CRASH900', full_name: 'CRASH900', description: 'Crash 900 Index', exchange: 'DERIV', type: 'Derived' },
                        // Jump Indices
                        { symbol: 'JD10', full_name: 'JD10', description: 'Jump 10 Index', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'JD25', full_name: 'JD25', description: 'Jump 25 Index', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'JD50', full_name: 'JD50', description: 'Jump 50 Index', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'JD75', full_name: 'JD75', description: 'Jump 75 Index', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'JD100', full_name: 'JD100', description: 'Jump 100 Index', exchange: 'DERIV', type: 'Derived' },
                        // Bear/Bull Indices
                        { symbol: 'RDBEAR', full_name: 'RDBEAR', description: 'Bear Market Index', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'RDBULL', full_name: 'RDBULL', description: 'Bull Market Index', exchange: 'DERIV', type: 'Derived' },
                        // Step Indices
                        { symbol: 'stpRNG', full_name: 'stpRNG', description: 'Step Index 100', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'stpRNG2', full_name: 'stpRNG2', description: 'Step Index 200', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'stpRNG3', full_name: 'stpRNG3', description: 'Step Index 300', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'stpRNG4', full_name: 'stpRNG4', description: 'Step Index 400', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'stpRNG5', full_name: 'stpRNG5', description: 'Step Index 500', exchange: 'DERIV', type: 'Derived' },
                        // Range Indices
                        { symbol: 'RB100', full_name: 'RB100', description: 'Range Break 100 Index', exchange: 'DERIV', type: 'Derived' },
                        { symbol: 'RB200', full_name: 'RB200', description: 'Range Break 200 Index', exchange: 'DERIV', type: 'Derived' },
                        // Forex Baskets
                        { symbol: 'WLDAUD', full_name: 'WLDAUD', description: 'AUD Basket', exchange: 'DERIV', type: 'Forex Baskets' },
                        { symbol: 'WLDEUR', full_name: 'WLDEUR', description: 'EUR Basket', exchange: 'DERIV', type: 'Forex Baskets' },
                        { symbol: 'WLDGBP', full_name: 'WLDGBP', description: 'GBP Basket', exchange: 'DERIV', type: 'Forex Baskets' },
                        { symbol: 'WLDUSD', full_name: 'WLDUSD', description: 'USD Basket', exchange: 'DERIV', type: 'Forex Baskets' },
                        { symbol: 'WLDXAU', full_name: 'WLDXAU', description: 'Gold Basket', exchange: 'DERIV', type: 'Forex Baskets' },
                        // Cryptocurrencies
                        { symbol: 'cryBTCUSD', full_name: 'cryBTCUSD', description: 'BTC/USD', exchange: 'DERIV', type: 'Cryptocurrencies' },
                        { symbol: 'cryETHUSD', full_name: 'cryETHUSD', description: 'ETH/USD', exchange: 'DERIV', type: 'Cryptocurrencies' },
                        // Major Forex Pairs
                        { symbol: 'frxEURUSD', full_name: 'frxEURUSD', description: 'EUR/USD', exchange: 'DERIV', type: 'Forex' },
                        { symbol: 'frxGBPUSD', full_name: 'frxGBPUSD', description: 'GBP/USD', exchange: 'DERIV', type: 'Forex' },
                        { symbol: 'frxUSDJPY', full_name: 'frxUSDJPY', description: 'USD/JPY', exchange: 'DERIV', type: 'Forex' },
                        { symbol: 'frxAUDUSD', full_name: 'frxAUDUSD', description: 'AUD/USD', exchange: 'DERIV', type: 'Forex' },
                        { symbol: 'frxUSDCAD', full_name: 'frxUSDCAD', description: 'USD/CAD', exchange: 'DERIV', type: 'Forex' },
                        { symbol: 'frxUSDCHF', full_name: 'frxUSDCHF', description: 'USD/CHF', exchange: 'DERIV', type: 'Forex' },
                        // Cross Currency Pairs
                        { symbol: 'frxEURGBP', full_name: 'frxEURGBP', description: 'EUR/GBP', exchange: 'DERIV', type: 'Forex' },
                        { symbol: 'frxEURJPY', full_name: 'frxEURJPY', description: 'EUR/JPY', exchange: 'DERIV', type: 'Forex' },
                        { symbol: 'frxEURCHF', full_name: 'frxEURCHF', description: 'EUR/CHF', exchange: 'DERIV', type: 'Forex' },
                        { symbol: 'frxGBPJPY', full_name: 'frxGBPJPY', description: 'GBP/JPY', exchange: 'DERIV', type: 'Forex' },
                        { symbol: 'frxAUDJPY', full_name: 'frxAUDJPY', description: 'AUD/JPY', exchange: 'DERIV', type: 'Forex' },
                        { symbol: 'frxEURAUD', full_name: 'frxEURAUD', description: 'EUR/AUD', exchange: 'DERIV', type: 'Forex' },
                        { symbol: 'frxEURCAD', full_name: 'frxEURCAD', description: 'EUR/CAD', exchange: 'DERIV', type: 'Forex' },
                        { symbol: 'frxGBPAUD', full_name: 'frxGBPAUD', description: 'GBP/AUD', exchange: 'DERIV', type: 'Forex' },
                        { symbol: 'frxGBPCAD', full_name: 'frxGBPCAD', description: 'GBP/CAD', exchange: 'DERIV', type: 'Forex' },
                        { symbol: 'frxNZDUSD', full_name: 'frxNZDUSD', description: 'NZD/USD', exchange: 'DERIV', type: 'Forex' },
                        { symbol: 'frxUSDCAD', full_name: 'frxUSDCAD', description: 'USD/CAD', exchange: 'DERIV', type: 'Forex' },
                        // Commodities
                        { symbol: 'frxXAUUSD', full_name: 'frxXAUUSD', description: 'Gold/USD', exchange: 'DERIV', type: 'Commodities' },
                        { symbol: 'frxXAGUSD', full_name: 'frxXAGUSD', description: 'Silver/USD', exchange: 'DERIV', type: 'Commodities' },
                        // OTC Indices
                        { symbol: 'OTC_DJI', full_name: 'OTC_DJI', description: 'Wall Street 30', exchange: 'DERIV', type: 'Indices' },
                        { symbol: 'OTC_NDX', full_name: 'OTC_NDX', description: 'US Tech 100', exchange: 'DERIV', type: 'Indices' },
                        { symbol: 'OTC_SPC', full_name: 'OTC_SPC', description: 'US 500', exchange: 'DERIV', type: 'Indices' },
                        { symbol: 'OTC_FTSE', full_name: 'OTC_FTSE', description: 'UK 100', exchange: 'DERIV', type: 'Indices' },
                        { symbol: 'OTC_GDAXI', full_name: 'OTC_GDAXI', description: 'Germany 40', exchange: 'DERIV', type: 'Indices' },
                        { symbol: 'OTC_N225', full_name: 'OTC_N225', description: 'Japan 225', exchange: 'DERIV', type: 'Indices' },
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
                
                // Enhanced search with market/type filtering
                const searchLower = (userInput || '').toLowerCase();
                const filtered = allSymbols.filter(s => {
                    const matchesSymbol = s.symbol.toLowerCase().includes(searchLower);
                    const matchesDescription = s.description.toLowerCase().includes(searchLower);
                    const matchesType = s.type && s.type.toLowerCase().includes(searchLower);
                    const matchesMarket = s.market && s.market.toLowerCase().includes(searchLower);
                    const matchesSubmarket = s.submarket && s.submarket.toLowerCase().includes(searchLower);
                    
                    return matchesSymbol || matchesDescription || matchesType || matchesMarket || matchesSubmarket;
                });
                
                // If exchange or symbolType is specified, further filter results
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

            connect() {
                if (this.connectionPromise) {
                    return this.connectionPromise;
                }
                
                this.connectionPromise = new Promise((resolve, reject) => {
                    this.ws = new WebSocket(`wss://ws.binaryws.com/websockets/v3?app_id=${this.appId}`);
                    
                    this.ws.onopen = () => {
                        console.log('Deriv Datafeed connected');
                        this.connected = true;
                        
                        // Only authorize if we have a valid non-empty token
                        if (this.apiToken && this.apiToken.trim() !== "") {
                            this.authorize().then(() => resolve()).catch((err) => {
                                console.error('Authorization failed:', err);
                                // Still resolve connection even if auth fails
                                resolve();
                            });
                        } else {
                            resolve();
                        }
                    };

                    this.ws.onerror = (error) => {
                        console.error('Deriv Datafeed error:', error);
                        this.connected = false;
                        reject(error);
                    };

                    this.ws.onclose = () => {
                        console.log('Deriv Datafeed disconnected');
                        this.connected = false;
                        this.authorized = false;
                        this.connectionPromise = null;
                    };

                    this.ws.onmessage = (evt) => {
                        const data = JSON.parse(evt.data);
                        
                        // Log all message types for debugging
                        console.log('Received message type:', data.msg_type, data);
                        
                        // Log any errors
                        if (data.error) {
                            console.error('API Error:', data.error);
                        }
                        
                        if (data.req_id && this.pending[data.req_id]) {
                            this.pending[data.req_id](data);
                            delete this.pending[data.req_id];
                        }

                        // Handle authorization response
                        if (data.msg_type === "authorize") {
                            if (data.error) {
                                console.error('Authorization error:', data.error);
                                this.authorized = false;
                            } else {
                                console.log('Authorization successful');
                                this.authorized = true;
                            }
                        }

                        // Handle OHLC updates for real-time candle movement
                        if (data.msg_type === "ohlc" && data.ohlc) {
                            console.log('Received OHLC update:', data.ohlc);
                            this.handleOHLC(data.ohlc);
                        }
                        
                        // Handle tick updates for real-time chart movement
                        if (data.msg_type === "tick" && data.tick) {
                            console.log('Received tick:', data.tick);
                            this.handleTick(data.tick);
                        }
                    };
                });
                
                return this.connectionPromise;
            }

            async authorize() {
                if (!this.apiToken) {
                    console.log('No API token provided, skipping authorization');
                    return Promise.resolve();
                }
                
                return new Promise((resolve, reject) => {
                    const authReq = {
                        authorize: this.apiToken
                    };
                    
                    this.ws.send(JSON.stringify(authReq));
                    
                    // Wait for authorization response with timeout
                    const timeout = setTimeout(() => {
                        console.log('Authorization timeout, proceeding without auth');
                        resolve();
                    }, 3000);
                    
                    const authHandler = (data) => {
                        if (data.msg_type === "authorize") {
                            clearTimeout(timeout);
                            if (data.error) {
                                console.error('Authorization failed:', data.error);
                                // Proceed without authorization rather than failing
                                resolve();
                            } else {
                                console.log('Authorization successful');
                                resolve(data);
                            }
                        }
                    };
                    
                    // Add temporary handler for auth response
                    const tempReqId = this.reqId++;
                    this.pending[tempReqId] = authHandler;
                });
            }

            async send(req) {
                if (!this.connected) {
                    await this.connect();
                }
                
                return new Promise((resolve, reject) => {
                    req.req_id = this.reqId++;
                    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                        this.ws.send(JSON.stringify(req));
                        this.pending[req.req_id] = resolve;
                    } else {
                        reject(new Error('WebSocket not connected'));
                    }
                });
            }

            mapCandles(candles) {
                return (candles || []).map((c) => ({
                    time: Number(c.epoch) * 1000,
                    open: parseFloat(c.open),
                    high: parseFloat(c.high),
                    low: parseFloat(c.low),
                    close: parseFloat(c.close),
                })).filter((bar) => (
                    bar.time > 0 &&
                    Number.isFinite(bar.open) &&
                    Number.isFinite(bar.high) &&
                    Number.isFinite(bar.low) &&
                    Number.isFinite(bar.close)
                )).sort((a, b) => a.time - b.time);
            }

            async getBars(symbolInfo, resolution, periodParams, onHistoryCallback, onErrorCallback) {
                let from;
                let to;
                let countBack = 500;
                let onResult = onHistoryCallback;
                let onError = onErrorCallback;

                // Charting Library v28 passes PeriodParams; older copies pass from/to numbers.
                if (periodParams && typeof periodParams === 'object') {
                    from = periodParams.from;
                    to = periodParams.to;
                    countBack = periodParams.countBack || 500;
                } else {
                    from = periodParams;
                    to = onHistoryCallback;
                    onResult = onErrorCallback;
                    onError = arguments[5];
                }

                const deliver = (bars, noData) => {
                    if (typeof onResult === 'function') {
                        onResult(bars, { noData: Boolean(noData) || bars.length === 0 });
                    }
                };
                const fail = (message) => {
                    if (typeof onError === 'function') {
                        onError(String(message || 'API Error'));
                    } else {
                        deliver([], true);
                    }
                };

                try {
                    const symbol = formatSymbol(symbolInfo.ticker || symbolInfo.name);
                    const granularity = this.getGranularity(resolution);
                    const count = Math.min(Math.max(countBack || 500, 50), 5000);
                    const end = (typeof to === 'number' && to > 0) ? Math.floor(to) : 'latest';

                    const req = {
                        ticks_history: symbol,
                        style: 'candles',
                        granularity: granularity,
                        adjust_start_time: 1,
                        end: end,
                        count: count,
                    };

                    console.log('Fetching historical data for:', symbol, 'resolution:', resolution, 'granularity:', granularity);
                    const data = await this.send(req);

                    if (data.error) {
                        console.error('API Error for', symbol, ':', data.error);
                        fail(data.error.message || data.error.code || 'API Error');
                        return;
                    }

                    let bars = this.mapCandles(data.candles);
                    if (typeof from === 'number' && from > 0) {
                        bars = bars.filter((bar) => bar.time / 1000 >= from);
                    }
                    if (typeof to === 'number' && to > 0) {
                        bars = bars.filter((bar) => bar.time / 1000 <= to);
                    }

                    console.log('Loaded', bars.length, 'candles for', symbol);
                    if (window.marketDataService) {
                        window.marketDataService.ingestChartBars(symbol, bars);
                    }
                    deliver(bars, bars.length === 0);
                } catch (error) {
                    console.error('Failed to load history:', error);
                    fail(error && error.message ? error.message : error);
                }
            }

            subscribeBars(symbolInfo, resolution, onRealtimeCallback, subscriberUID, onResetCacheNeededCallback) {
                const symbol = formatSymbol(symbolInfo.ticker || symbolInfo.name);
                this.currentSymbol = symbol;
                this.currentGranularity = this.getGranularity(resolution);
                this.subscriptions.add(subscriberUID);
                this.onRealtimeCallback = onRealtimeCallback;
                this.currentCandle = null;
                window.currentChartSymbol = symbol;

                this.send({ ticks: symbol, subscribe: 1 }).catch(() => {});
                this.send({
                    ticks_history: symbol,
                    style: 'candles',
                    granularity: this.currentGranularity,
                    adjust_start_time: 1,
                    subscribe: 1,
                    count: 1,
                    end: 'latest',
                }).then((data) => {
                    const bars = this.mapCandles(data.candles);
                    if (bars.length) {
                        this.currentCandle = bars[bars.length - 1];
                        window.currentChartPrice = this.currentCandle.close;
                        window.currentCandleData = this.currentCandle;
                        onRealtimeCallback(this.currentCandle);
                    }
                }).catch((error) => {
                    console.error('Failed to seed live candle:', error);
                });

                if (this.pollInterval) clearInterval(this.pollInterval);
                this.pollInterval = setInterval(() => {
                    this.send({
                        ticks_history: symbol,
                        style: 'candles',
                        granularity: this.currentGranularity,
                        count: 1,
                        end: 'latest',
                    }).then((data) => {
                        const bars = this.mapCandles(data.candles);
                        if (!bars.length) return;
                        const bar = bars[bars.length - 1];
                        if (this.currentCandle && bar.time === this.currentCandle.time) {
                            bar.close = this.currentCandle.close;
                            bar.high = Math.max(bar.high, this.currentCandle.high);
                            bar.low = Math.min(bar.low, this.currentCandle.low);
                        }
                        this.currentCandle = bar;
                        onRealtimeCallback(bar);
                    }).catch(() => {});
                }, 30000);
            }

            startPolling() {}

            unsubscribeBars(subscriberUID) {
                this.subscriptions.delete(subscriberUID);
                
                // Clear polling interval
                if (this.pollInterval) {
                    clearInterval(this.pollInterval);
                    this.pollInterval = null;
                }
            }

            handleOHLC(ohlc) {
                if (this.onRealtimeCallback) {
                    const bar = {
                        time: ohlc.open_time * 1000,
                        open: parseFloat(ohlc.open),
                        high: parseFloat(ohlc.high),
                        low: parseFloat(ohlc.low),
                        close: parseFloat(ohlc.close),
                    };
                    console.log('Received OHLC update:', bar);
                    this.onRealtimeCallback(bar);
                    // Update current candle reference
                    this.currentCandle = bar;
                    window.currentCandleData = bar;
                }
            }

            handleTick(tick) {
                if (tick.symbol && this.currentSymbol && tick.symbol !== this.currentSymbol) {
                    return;
                }
                if (!this.onRealtimeCallback) {
                    return;
                }
                
                const price = parseFloat(tick.quote);
                const tickTime = tick.epoch * 1000;
                window.currentChartPrice = price;
                if (window.marketDataService) {
                    window.marketDataService.setCurrentPrice(price);
                }
                window.dispatchEvent(new CustomEvent('tick-update', { 
                    detail: { 
                        price: price, 
                        time: tickTime,
                        symbol: tick.symbol || this.currentSymbol 
                    } 
                }));
                
                if (!this.currentCandle) {
                    const granularity = this.currentGranularity || 60;
                    const candleStartTime = Math.floor(tickTime / (granularity * 1000)) * (granularity * 1000);
                    this.currentCandle = {
                        time: candleStartTime,
                        open: price,
                        high: price,
                        low: price,
                        close: price,
                    };
                    this.onRealtimeCallback(this.currentCandle);
                    window.currentCandleData = this.currentCandle;
                    return;
                }

                const candleTime = this.currentCandle.time;
                const granularity = this.currentGranularity || 60;
                const candleEndTime = candleTime + (granularity * 1000);

                if (tickTime < candleEndTime) {
                    const updatedCandle = {
                        time: this.currentCandle.time,
                        open: this.currentCandle.open,
                        high: Math.max(this.currentCandle.high, price),
                        low: Math.min(this.currentCandle.low, price),
                        close: price,
                    };
                    this.onRealtimeCallback(updatedCandle);
                    this.currentCandle = updatedCandle;
                    window.currentCandleData = updatedCandle;
                } else {
                    const newCandleStartTime = Math.floor(tickTime / (granularity * 1000)) * (granularity * 1000);
                    this.currentCandle = {
                        time: newCandleStartTime,
                        open: price,
                        high: price,
                        low: price,
                        close: price,
                    };
                    this.onRealtimeCallback(this.currentCandle);
                    window.currentCandleData = this.currentCandle;
                }
            }

            getGranularity(resolution) {
                const map = {
                    '1': 60,
                    '5': 300,
                    '15': 900,
                    '30': 1800,
                    '60': 3600,
                    '240': 14400,
                    'D': 86400,
                    '1D': 86400,
                };
                return map[resolution] || 60;
            }
        }

        // Initialize datafeed
        const datafeed = new DerivDatafeed();
        datafeed.connect().catch(console.error);

        // Create TradingView widget
        const widget = new TradingView.widget({
            container_id: containerId,
            // The searchable dialog uses Deriv's live active_symbols catalogue.
            symbol: defaultSymbol || "R_100",
            datafeed: datafeed,
            interval: "60",
            timezone: "Etc/UTC",
            theme: "light",
            style: "candles",
            locale: "en",
            toolbar_bg: "#ffffff",
            enable_publishing: false,
            allow_symbol_change: true,
            hide_side_toolbar: false,
            studies: [
                "MASimple@tv-basicstudies",
                "RSI@tv-basicstudies",
                "MACD@tv-basicstudies",
            ],
            container: container,
            library_path: "/static/charting_library/",
            width: "100%",
            height: "100%",
            drawing_tools: true,
            // Enhanced symbol search configuration
            symbol_search_request_delay: 0,
            // Ensure candlestick style is enforced for all symbols
            disabled_features: ["use_localstorage_for_settings"],
            enabled_features: ["study_templates"],
            // Force candlestick display
            custom_css_url: "",
            // Additional settings to ensure candlestick display
            overrides: {
                "mainSeriesProperties.candleStyle.upColor": "#26a69a",
                "mainSeriesProperties.candleStyle.downColor": "#ef5350",
                "mainSeriesProperties.candleStyle.borderUpColor": "#26a69a",
                "mainSeriesProperties.candleStyle.borderDownColor": "#ef5350",
                "mainSeriesProperties.candleStyle.wickUpColor": "#26a69a",
                "mainSeriesProperties.candleStyle.wickDownColor": "#ef5350",
            },
        });

        // Set initial symbol and track symbol changes
        widget.onChartReady(() => {
            const activeChart = widget.activeChart();
            window.currentChartSymbol = activeChart.symbol();
            
            console.log('Chart ready, symbol:', window.currentChartSymbol);
            
            // Hide loader when chart is ready
            const loader = document.getElementById('chart-loader');
            if (loader) {
                loader.classList.remove('active');
            }
            
            // Force candlestick style for all symbols
            activeChart.setChartType(1); // 1 = candlestick chart type
            console.log('Set chart type to candlestick');
            
            // Also set the style via widget options
            widget.applyOptions({
                style: 'candles',
            });
            
            activeChart.onSymbolChanged().subscribe(null, (symbolInfo) => {
                window.currentChartSymbol = symbolInfo.name;
                console.log('Symbol changed to:', symbolInfo.name);
                
                // Show loader when symbol changes
                const loader = document.getElementById('chart-loader');
                if (loader) {
                    loader.classList.add('active');
                    document.querySelector('.loader-text').textContent = `Loading ${symbolInfo.name}...`;
                }
                
                window.dispatchEvent(new CustomEvent('chart-symbol-changed', { detail: { symbol: symbolInfo.name } }));
                
                // Re-enforce candlestick style on symbol change
                setTimeout(() => {
                    activeChart.setChartType(1);
                    widget.applyOptions({
                        style: 'candles',
                    });
                    console.log('Re-enforced candlestick style for:', symbolInfo.name);
                    
                    // Hide loader after a delay
                    setTimeout(() => {
                        if (loader) {
                            loader.classList.remove('active');
                        }
                    }, 1000);
                }, 100);
            });
            
            // Listen for ticker symbol selection
            window.addEventListener('ticker-symbol-selected', (event) => {
                const symbol = event.detail.symbol;
                console.log('Ticker selected symbol:', symbol, 'changing chart');
                
                // Show loader when symbol changes
                const loader = document.getElementById('chart-loader');
                if (loader) {
                    loader.classList.add('active');
                    document.querySelector('.loader-text').textContent = `Loading ${symbol}...`;
                }
                
                activeChart.setSymbol(symbol);
                
                // Ensure candlestick style after symbol change
                setTimeout(() => {
                    activeChart.setChartType(1);
                    widget.applyOptions({
                        style: 'candles',
                    });
                    console.log('Ensured candlestick style after ticker selection for:', symbol);
                    
                    // Hide loader after a delay
                    setTimeout(() => {
                        if (loader) {
                            loader.classList.remove('active');
                        }
                    }, 1500);
                }, 200);
            });
        });

        // Expose widget globally for AI interaction
        window.tradingViewWidget = widget;

        return {
            widget,
            datafeed,
            destroy() {
                if (datafeed.ws) datafeed.ws.close();
            },
        };
    };
})();
