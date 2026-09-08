/*
 * Datafeed adapter that connects the TradingView Advanced Charting Library
 * straight to Deriv's public WebSocket API (same "ticks_history" / "ohlc"
 * calls the old Lightweight-Charts version used) — no Django proxy needed.
 *
 * Implements the classic IDatafeedChartApi contract shipped with this copy
 * of the library (see datafeed-api.d.ts): getBars(..., rangeStartDate,
 * rangeEndDate, ..., isFirstCall) rather than the newer PeriodParams object.
 */
(function (global) {
    // Internal symbol names are already in correct Deriv API format
    function formatSymbol(sym) {
        if (!sym || typeof sym !== 'string' || !sym.trim()) return "R_100";
        return sym.trim();
    }

    const AVAILABLE_SYMBOLS = [
        // Volatility Indices
        { symbol: "R_10", name: "Volatility 10 Index", type: "index", market: "Volatility Indices" },
        { symbol: "R_25", name: "Volatility 25 Index", type: "index", market: "Volatility Indices" },
        { symbol: "R_50", name: "Volatility 50 Index", type: "index", market: "Volatility Indices" },
        { symbol: "R_75", name: "Volatility 75 Index", type: "index", market: "Volatility Indices" },
        { symbol: "R_100", name: "Volatility 100 Index", type: "index", market: "Volatility Indices" },
        // 1-Second Volatility Indices
        { symbol: "1HZ10V", name: "Volatility 10 (1s) Index", type: "index", market: "Volatility Indices" },
        { symbol: "1HZ15V", name: "Volatility 15 (1s) Index", type: "index", market: "Volatility Indices" },
        { symbol: "1HZ25V", name: "Volatility 25 (1s) Index", type: "index", market: "Volatility Indices" },
        { symbol: "1HZ30V", name: "Volatility 30 (1s) Index", type: "index", market: "Volatility Indices" },
        { symbol: "1HZ50V", name: "Volatility 50 (1s) Index", type: "index", market: "Volatility Indices" },
        { symbol: "1HZ75V", name: "Volatility 75 (1s) Index", type: "index", market: "Volatility Indices" },
        { symbol: "1HZ90V", name: "Volatility 90 (1s) Index", type: "index", market: "Volatility Indices" },
        { symbol: "1HZ100V", name: "Volatility 100 (1s) Index", type: "index", market: "Volatility Indices" },
        // Boom/Crash Indices
        { symbol: "BOOM1000", name: "Boom 1000 Index", type: "index", market: "Derived" },
        { symbol: "BOOM150N", name: "Boom 150 Index", type: "index", market: "Derived" },
        { symbol: "BOOM300N", name: "Boom 300 Index", type: "index", market: "Derived" },
        { symbol: "BOOM50", name: "Boom 50 Index", type: "index", market: "Derived" },
        { symbol: "BOOM500", name: "Boom 500 Index", type: "index", market: "Derived" },
        { symbol: "BOOM600", name: "Boom 600 Index", type: "index", market: "Derived" },
        { symbol: "BOOM900", name: "Boom 900 Index", type: "index", market: "Derived" },
        { symbol: "CRASH1000", name: "Crash 1000 Index", type: "index", market: "Derived" },
        { symbol: "CRASH150N", name: "Crash 150 Index", type: "index", market: "Derived" },
        { symbol: "CRASH300N", name: "Crash 300 Index", type: "index", market: "Derived" },
        { symbol: "CRASH50", name: "Crash 50 Index", type: "index", market: "Derived" },
        { symbol: "CRASH500", name: "Crash 500 Index", type: "index", market: "Derived" },
        { symbol: "CRASH600", name: "Crash 600 Index", type: "index", market: "Derived" },
        { symbol: "CRASH900", name: "Crash 900 Index", type: "index", market: "Derived" },
        // Jump Indices
        { symbol: "JD10", name: "Jump 10 Index", type: "index", market: "Derived" },
        { symbol: "JD25", name: "Jump 25 Index", type: "index", market: "Derived" },
        { symbol: "JD50", name: "Jump 50 Index", type: "index", market: "Derived" },
        { symbol: "JD75", name: "Jump 75 Index", type: "index", market: "Derived" },
        { symbol: "JD100", name: "Jump 100 Index", type: "index", market: "Derived" },
        // Bear/Bull Indices
        { symbol: "RDBEAR", name: "Bear Market Index", type: "index", market: "Derived" },
        { symbol: "RDBULL", name: "Bull Market Index", type: "index", market: "Derived" },
        // Step Indices
        { symbol: "stpRNG", name: "Step Index 100", type: "index", market: "Derived" },
        { symbol: "stpRNG2", name: "Step Index 200", type: "index", market: "Derived" },
        { symbol: "stpRNG3", name: "Step Index 300", type: "index", market: "Derived" },
        { symbol: "stpRNG4", name: "Step Index 400", type: "index", market: "Derived" },
        { symbol: "stpRNG5", name: "Step Index 500", type: "index", market: "Derived" },
        // Range Indices
        { symbol: "RB100", name: "Range Break 100 Index", type: "index", market: "Derived" },
        { symbol: "RB200", name: "Range Break 200 Index", type: "index", market: "Derived" },
        // Forex Baskets
        { symbol: "WLDAUD", name: "AUD Basket", type: "index", market: "Forex Baskets" },
        { symbol: "WLDEUR", name: "EUR Basket", type: "index", market: "Forex Baskets" },
        { symbol: "WLDGBP", name: "GBP Basket", type: "index", market: "Forex Baskets" },
        { symbol: "WLDUSD", name: "USD Basket", type: "index", market: "Forex Baskets" },
        { symbol: "WLDXAU", name: "Gold Basket", type: "index", market: "Forex Baskets" },
        // Cryptocurrencies
        { symbol: "cryBTCUSD", name: "BTC/USD", type: "index", market: "Cryptocurrencies" },
        { symbol: "cryETHUSD", name: "ETH/USD", type: "index", market: "Cryptocurrencies" },
        // Major Forex Pairs
        { symbol: "frxEURUSD", name: "EUR/USD", type: "forex", market: "Forex" },
        { symbol: "frxGBPUSD", name: "GBP/USD", type: "forex", market: "Forex" },
        { symbol: "frxUSDJPY", name: "USD/JPY", type: "forex", market: "Forex" },
        { symbol: "frxAUDUSD", name: "AUD/USD", type: "forex", market: "Forex" },
        { symbol: "frxUSDCAD", name: "USD/CAD", type: "forex", market: "Forex" },
        { symbol: "frxUSDCHF", name: "USD/CHF", type: "forex", market: "Forex" },
        // Cross Currency Pairs
        { symbol: "frxEURGBP", name: "EUR/GBP", type: "forex", market: "Forex" },
        { symbol: "frxEURJPY", name: "EUR/JPY", type: "forex", market: "Forex" },
        { symbol: "frxEURCHF", name: "EUR/CHF", type: "forex", market: "Forex" },
        { symbol: "frxGBPJPY", name: "GBP/JPY", type: "forex", market: "Forex" },
        { symbol: "frxAUDJPY", name: "AUD/JPY", type: "forex", market: "Forex" },
        { symbol: "frxEURAUD", name: "EUR/AUD", type: "forex", market: "Forex" },
        { symbol: "frxEURCAD", name: "EUR/CAD", type: "forex", market: "Forex" },
        { symbol: "frxGBPAUD", name: "GBP/AUD", type: "forex", market: "Forex" },
        { symbol: "frxGBPCAD", name: "GBP/CAD", type: "forex", market: "Forex" },
        { symbol: "frxNZDUSD", name: "NZD/USD", type: "forex", market: "Forex" },
        { symbol: "frxUSDCAD", name: "USD/CAD", type: "forex", market: "Forex" },
        // Commodities
        { symbol: "frxXAUUSD", name: "Gold/USD", type: "commodity", market: "Commodities" },
        { symbol: "frxXAGUSD", name: "Silver/USD", type: "commodity", market: "Commodities" },
        // OTC Indices
        { symbol: "OTC_DJI", name: "Wall Street 30", type: "index", market: "Indices" },
        { symbol: "OTC_NDX", name: "US Tech 100", type: "index", market: "Indices" },
        { symbol: "OTC_SPC", name: "US 500", type: "index", market: "Indices" },
        { symbol: "OTC_FTSE", name: "UK 100", type: "index", market: "Indices" },
        { symbol: "OTC_GDAXI", name: "Germany 40", type: "index", market: "Indices" },
        { symbol: "OTC_N225", name: "Japan 225", type: "index", market: "Indices" },
    ];

    const RESOLUTIONS = ["1", "5", "15", "30", "60", "240", "1D"];
    const GRANULARITY = { "1": 60, "5": 300, "15": 900, "30": 1800, "60": 3600, "240": 14400, "1D": 86400, D: 86400 };

    /* ---- one shared socket, multiplexed across history requests + live bar streams ---- */
    class DerivSocket {
        constructor(appId) {
            this.appId = appId;
            this.ws = null;
            this.reqId = 1;
            this.pending = {};          // req_id -> {resolve, reject}          (one-shot requests)
            this.pendingStreams = {};   // req_id -> {guid, onTick}             (subscribing requests, before we know the sub id)
            this.streamsByGuid = {};    // listenerGuid -> {subId, onTick}      (once the sub id is known)
            this.queue = [];
            this._connect();
        }

        _connect() {
            this.ws = new WebSocket(`wss://ws.derivws.com/websockets/v3?app_id=${this.appId}`);
            this.ws.onopen = () => { this.queue.forEach((req) => this.ws.send(JSON.stringify(req))); this.queue = []; };
            this.ws.onmessage = (evt) => this._route(JSON.parse(evt.data));
            this.ws.onclose = () => setTimeout(() => this._connect(), 3000);
            this.ws.onerror = () => this.ws.close();
        }

        _send(req) {
            req.req_id = this.reqId++;
            if (this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(req));
            else this.queue.push(req);
            return req.req_id;
        }

        /** One-shot request/response, e.g. a plain (non-subscribing) history fetch. */
        request(req) {
            return new Promise((resolve, reject) => {
                const id = this._send(req);
                this.pending[id] = { resolve, reject };
            });
        }

        /** Subscribing ticks_history request. onTick fires for every streamed
         *  "ohlc" update after the initial snapshot. */
        subscribeOhlc(req, guid, onTick) {
            const id = this._send(req);
            this.pendingStreams[id] = { guid, onTick };
        }

        unsubscribeOhlc(guid) {
            const stream = this.streamsByGuid[guid];
            if (stream && stream.subId) this._send({ forget: stream.subId });
            delete this.streamsByGuid[guid];
        }

        _route(data) {
            const reqId = data.req_id;

            // First response to a subscribing request: learn the real
            // subscription id and promote it into streamsByGuid.
            if (reqId && this.pendingStreams[reqId]) {
                const { guid, onTick } = this.pendingStreams[reqId];
                delete this.pendingStreams[reqId];
                if (data.subscription && data.subscription.id) {
                    this.streamsByGuid[guid] = { subId: data.subscription.id, onTick };
                }
            }

            if (data.msg_type === "ohlc" && data.ohlc) {
                const match = Object.values(this.streamsByGuid).find((s) => s.subId === data.ohlc.id);
                if (match) match.onTick(data.ohlc);
            }

            if (reqId && this.pending[reqId]) {
                const { resolve, reject } = this.pending[reqId];
                delete this.pending[reqId];
                if (data.error) reject(data.error); else resolve(data);
            }
        }
    }

    class DerivDatafeed {
        constructor({ appId, onPrice }) {
            this.socket = new DerivSocket(appId);
            this.onPrice = onPrice || function () {};
        }

        onReady(callback) {
            console.log("onReady called");
            // Wrap callback in try-catch to prevent TradingView errors
            try {
                callback({
                    supported_resolutions: RESOLUTIONS,
                    supports_marks: false,
                    supports_timescale_marks: false,
                    supports_time: false,
                    supports_search: true, // Enable symbol search
                    supports_group_request: false,
                });
            } catch (e) {
                console.error("onReady callback error:", e);
            }
        }

        async fetchAllSymbols() {
            try {
                const response = await this.socket.request({ active_symbols: "brief", product_type: "basic" });
                if (response && response.active_symbols) {
                    return response.active_symbols.map(s => ({
                        symbol: s.symbol,
                        name: s.display_name || s.symbol,
                        type: s.market === "forex" ? "forex" : "index",
                        exchange: "Deriv",
                    }));
                }
            } catch (e) {
                console.error("Failed to fetch all symbols:", e);
            }
            return AVAILABLE_SYMBOLS;
        }

        async searchSymbols(userInput, exchange, symbolType, onResult) {
            console.log("searchSymbols called with:", userInput, exchange, symbolType);
            
            // Enhanced search through available symbols with market filtering
            const searchLower = (userInput || "").toLowerCase();
            const results = AVAILABLE_SYMBOLS.filter(s => {
                const matchesSymbol = s.symbol.toLowerCase().includes(searchLower);
                const matchesName = s.name.toLowerCase().includes(searchLower);
                const matchesMarket = s.market && s.market.toLowerCase().includes(searchLower);
                const matchesType = s.type && s.type.toLowerCase().includes(searchLower);
                
                return matchesSymbol || matchesName || matchesMarket || matchesType;
            }).map(s => ({
                symbol: s.symbol,
                full_name: s.symbol,
                description: s.name,
                exchange: "Deriv",
                type: s.type,
                ticker: s.symbol,
                market: s.market,
            }));
            
            // Filter by exchange if specified
            let finalResults = results;
            if (exchange && exchange !== "Deriv") {
                finalResults = finalResults.filter(s => s.exchange === exchange);
            }
            
            // Filter by symbol type if specified
            if (symbolType) {
                finalResults = finalResults.filter(s => 
                    s.type === symbolType || 
                    s.market === symbolType
                );
            }
            
            console.log("Search results:", finalResults.length, finalResults.slice(0, 5));
            onResult(finalResults);
        }

        resolveSymbol(symbolName, onResolve, onError) {
            console.log("resolveSymbol called with:", symbolName);
            
            // Default to R_100 if symbol is invalid - never call onError to avoid TradingView library errors
            const validSymbol = (symbolName && typeof symbolName === 'string' && symbolName.trim()) ? symbolName.trim() : "R_100";
            
            // Find the symbol in our available symbols list to get proper description and market info
            const symbolData = AVAILABLE_SYMBOLS.find(s => s.symbol === validSymbol);
            const description = (symbolData && symbolData.name) ? symbolData.name : validSymbol;
            const market = (symbolData && symbolData.market) ? symbolData.market : "Unknown";
            const symbolType = (symbolData && symbolData.type) ? symbolData.type : "index";
            
            const isForex = validSymbol && validSymbol.startsWith && validSymbol.startsWith("frx");
            const isCommodity = /frxXA[UG]/i.test(validSymbol || "");
            const info = {
                name: validSymbol,
                full_name: validSymbol,
                ticker: validSymbol,
                description: description,
                type: symbolType,
                session: (isForex || isCommodity) ? "24x5" : "24x7",
                timezone: (isForex || isCommodity) ? "America/New_York" : "Etc/UTC",
                exchange: "Deriv",
                listed_exchange: "Deriv",
                minmov: 1,
                pricescale: isForex ? 100000 : 100,
                has_intraday: true,
                has_daily: true,
                has_weekly_and_monthly: false,
                has_no_volume: true,
                volume_precision: 0,
                data_status: "streaming",
                supported_resolutions: RESOLUTIONS,
                supported_timezones: ["Etc/UTC"],
                has_empty_bars: false,
                force_session_rebuild: false,
                currency_code: "USD",
                unit_id: "",
                market: market,
                // Remove fields that might cause TradingView errors
                // supports_time: true,
                // supports_multi_symbol: false,
                // supports_custom_timeframes: false,
            };
            console.log("resolveSymbol returning:", info);
            
            // Wrap onResolve in try-catch to prevent TradingView errors
            try {
                onResolve(info);
            } catch (e) {
                console.error("onResolve callback error:", e);
                // Try calling onError with a string message
                if (onError && typeof onError === 'function') {
                    try {
                        onError("Symbol resolution failed");
                    } catch (e2) {
                        console.error("onError callback error:", e2);
                    }
                }
            }
        }

        getBars(symbolInfo, resolution, rangeStartDate, rangeEndDate, onResult, onError, isFirstCall) {
            console.log("getBars called:", { symbolInfo, resolution, rangeStartDate, rangeEndDate, isFirstCall });
            
            if (!symbolInfo || !symbolInfo.ticker) {
                console.error("Invalid symbolInfo:", symbolInfo);
                // Call onError with string message
                if (onError && typeof onError === 'function') {
                    try {
                        onError("Invalid symbol");
                    } catch (e) {
                        console.error("onError callback error:", e);
                    }
                }
                return;
            }
            
            const formattedSymbol = formatSymbol(symbolInfo.ticker);
            console.log("Formatted symbol:", formattedSymbol);
            
            const granularity = GRANULARITY[resolution] || 60;
            const req = {
                ticks_history: formattedSymbol,
                style: "candles",
                granularity,
                adjust_start_time: 1,
            };
            
            // Always use initial load mode for simplicity - TradingView handles pagination
            // The isFirstCall parameter is unreliable and timestamp conversion is problematic
            req.end = "latest";
            req.count = 500;

            console.log("Sending request:", req);

            this.socket.request(req).then((data) => {
                console.log("Received data:", data);
                if (data.error) {
                    console.error("API Error:", data.error);
                    // Call onError with string message
                    const errorMsg = (data.error.message || data.error || "Unknown error").toString();
                    if (onError && typeof onError === 'function') {
                        try {
                            onError(errorMsg);
                        } catch (e) {
                            console.error("onError callback error:", e);
                        }
                    }
                    return;
                }
                const candles = data.candles || [];
                const bars = candles.map((c) => {
                    const time = c.epoch ? Math.floor(c.epoch * 1000) : Date.now();
                    const open = c.open != null && !isNaN(c.open) ? parseFloat(c.open) : 0;
                    const high = c.high != null && !isNaN(c.high) ? parseFloat(c.high) : 0;
                    const low = c.low != null && !isNaN(c.low) ? parseFloat(c.low) : 0;
                    const close = c.close != null && !isNaN(c.close) ? parseFloat(c.close) : 0;
                    
                    // Bar structure matching TypeScript interface with volume
                    return { 
                        time, 
                        open, 
                        high, 
                        low, 
                        close,
                        volume: 0
                    };
                }).filter(bar => 
                    // Filter out invalid bars
                    bar.time > 0 && 
                    bar.open >= 0 && 
                    bar.high >= 0 && 
                    bar.low >= 0 && 
                    bar.close >= 0 &&
                    bar.high >= bar.low
                ).sort((a, b) => a.time - b.time); // Ensure bars are sorted by time ascending
                console.log("Processed bars:", bars.length, bars.slice(0, 3));
                // Call onResult with bars and metadata as per TypeScript definition
                onResult(bars, { noData: bars.length === 0 });
            }).catch((err) => {
                console.error("getBars error:", err);
                // Call onError with string message
                const errorMsg = (err.message || err || "Unknown error").toString();
                if (onError && typeof onError === 'function') {
                    try {
                        onError(errorMsg);
                    } catch (e) {
                        console.error("onError callback error:", e);
                    }
                }
            });
        }

        subscribeBars(symbolInfo, resolution, onTick, listenerGuid, onResetCacheNeededCallback) {
            if (!symbolInfo || !symbolInfo.ticker) {
                return;
            }
            const granularity = GRANULARITY[resolution] || 60;
            const req = {
                ticks_history: formatSymbol(symbolInfo.ticker),
                style: "candles",
                granularity,
                adjust_start_time: 1,
                count: 1,
                end: "latest",
                subscribe: 1,
            };
            this.socket.subscribeOhlc(req, listenerGuid, (ohlc) => {
                const bar = {
                    time: +ohlc.open_time * 1000, 
                    open: +ohlc.open, 
                    high: +ohlc.high, 
                    low: +ohlc.low, 
                    close: +ohlc.close
                };
                onTick(bar);
                this.onPrice(bar.close, symbolInfo.ticker);
            });
        }

        unsubscribeBars(listenerGuid) {
            this.socket.unsubscribeOhlc(listenerGuid);
        }
    }

    global.DerivDatafeed = DerivDatafeed;
})(window);
