/*
 * Shared price feed service for real-time price updates across the application
 * Connects to Deriv WebSocket and broadcasts price updates to all listeners
 * Optimized to avoid rate limiting
 */
(function () {
    class PriceFeed {
        constructor() {
            this.ws = null;
            this.listeners = new Map(); // symbol -> Set of callbacks
            this.currentPrices = new Map(); // symbol -> current price
            this.subscribedSymbols = new Set(); // symbols we're currently subscribed to
            this.appId = window.DERIV_APP_ID || 1089;
            this.apiToken = window.DERIV_API_TOKEN || null;
            this.reqId = 1;
            this.pending = {};
            this.connected = false;
            this.authorized = false;
            this.maxConcurrentSubscriptions = 5; // Limit concurrent subscriptions to avoid rate limiting
            this.subscriptionQueue = [];
            this.isProcessingQueue = false;
        }

        connect() {
            if (this.connected && this.ws && this.ws.readyState === WebSocket.OPEN) {
                return;
            }

            this.ws = new WebSocket(`wss://ws.binaryws.com/websockets/v3?app_id=${this.appId}`);

            this.ws.onopen = () => {
                console.log('Price feed connected');
                this.connected = true;
                
                // Authorize if token provided
                if (this.apiToken && this.apiToken.trim() !== "") {
                    this.send({ authorize: this.apiToken });
                }
                
                // Process subscription queue
                this.processSubscriptionQueue();
            };

            this.ws.onmessage = (evt) => {
                const data = JSON.parse(evt.data);
                this.handleMessage(data);
            };

            this.ws.onclose = () => {
                console.log('Price feed disconnected, reconnecting...');
                this.connected = false;
                this.subscribedSymbols.clear();
                setTimeout(() => this.connect(), 3000);
            };

            this.ws.onerror = (error) => {
                console.error('Price feed error:', error);
            };
        }

        send(req) {
            req.req_id = this.reqId++;
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify(req));
            }
            return req.req_id;
        }

        handleMessage(data) {
            // Handle authorization response
            if (data.msg_type === "authorize") {
                if (data.error) {
                    console.error('Price feed authorization error:', data.error);
                    this.authorized = false;
                } else {
                    console.log('Price feed authorization successful');
                    this.authorized = true;
                }
                return;
            }

            // Handle pending requests
            if (data.req_id && this.pending[data.req_id]) {
                this.pending[data.req_id](data);
                delete this.pending[data.req_id];
            }

            // Handle tick updates
            if (data.msg_type === "tick" && data.tick) {
                const apiSymbol = data.tick.symbol;
                const price = parseFloat(data.tick.quote);
                // Convert API symbol back to internal symbol for listeners
                const internalSymbol = this.convertToInternalSymbol(apiSymbol);
                this.updatePrice(internalSymbol, price);
            }

            // Handle OHLC updates
            if (data.msg_type === "ohlc" && data.ohlc) {
                const apiSymbol = data.ohlc.symbol;
                const price = parseFloat(data.ohlc.close);
                // Convert API symbol back to internal symbol for listeners
                const internalSymbol = this.convertToInternalSymbol(apiSymbol);
                this.updatePrice(internalSymbol, price);
            }
        }

        convertToInternalSymbol(apiSymbol) {
            // Convert API symbol back to internal symbol format
            // Internal symbol names are already in correct Deriv API format
            // No conversion needed
            return apiSymbol;
        }

        updatePrice(symbol, price) {
            const oldPrice = this.currentPrices.get(symbol);
            this.currentPrices.set(symbol, price);
            
            // Notify all listeners for this symbol
            const callbacks = this.listeners.get(symbol);
            if (callbacks) {
                callbacks.forEach(callback => {
                    try {
                        callback(symbol, price, oldPrice);
                    } catch (error) {
                        console.error('Error in price callback:', error);
                    }
                });
            }
        }

        processSubscriptionQueue() {
            if (this.isProcessingQueue || this.subscriptionQueue.length === 0) {
                return;
            }

            this.isProcessingQueue = true;

            // Process as many subscriptions as we can without exceeding the limit
            while (this.subscriptionQueue.length > 0 && 
                   this.subscribedSymbols.size < this.maxConcurrentSubscriptions) {
                const symbol = this.subscriptionQueue.shift();
                this.subscribeToSymbol(symbol);
            }

            this.isProcessingQueue = false;
        }

        subscribeToSymbol(symbol) {
            if (!this.connected || !this.ws || this.subscribedSymbols.has(symbol)) {
                return;
            }

            // Format symbol for Deriv API
            const formattedSymbol = this.formatSymbol(symbol);

            // Only subscribe to ticks (not OHLC) to reduce API calls
            const tickReq = {
                ticks: formattedSymbol,
                subscribe: 1,
            };
            this.send(tickReq);

            this.subscribedSymbols.add(symbol);
            console.log(`Subscribed to ${symbol}`);
        }

        unsubscribeFromSymbol(symbol) {
            if (!this.connected || !this.ws || !this.subscribedSymbols.has(symbol)) {
                return;
            }

            const formattedSymbol = this.formatSymbol(symbol);
            
            // Unsubscribe from ticks
            const forgetReq = {
                forget: formattedSymbol,
            };
            this.send(forgetReq);

            this.subscribedSymbols.delete(symbol);
            console.log(`Unsubscribed from ${symbol}`);

            // Process queue after unsubscribing
            this.processSubscriptionQueue();
        }

        formatSymbol(symbol) {
            // Convert internal symbol format to Deriv API format
            // Internal symbol names are already in correct Deriv API format
            // No conversion needed
            return symbol;
        }

        subscribe(symbol, callback) {
            if (!this.listeners.has(symbol)) {
                this.listeners.set(symbol, new Set());
            }
            this.listeners.get(symbol).add(callback);

            // Add to subscription queue if not already subscribed
            if (!this.subscribedSymbols.has(symbol)) {
                this.subscriptionQueue.push(symbol);
                this.processSubscriptionQueue();
            }

            // Connect if not already connected
            if (!this.connected) {
                this.connect();
            }

            // Return current price if available
            const currentPrice = this.currentPrices.get(symbol);
            if (currentPrice) {
                callback(symbol, currentPrice, null);
            }

            // Return unsubscribe function
            return () => {
                const callbacks = this.listeners.get(symbol);
                if (callbacks) {
                    callbacks.delete(callback);
                    if (callbacks.size === 0) {
                        this.listeners.delete(symbol);
                        // Unsubscribe from API if no more listeners
                        this.unsubscribeFromSymbol(symbol);
                    }
                }
            };
        }

        getPrice(symbol) {
            return this.currentPrices.get(symbol);
        }

        getCurrentPrices() {
            return Object.fromEntries(this.currentPrices);
        }
    }

    // Create singleton instance
    window.priceFeed = new PriceFeed();
})();