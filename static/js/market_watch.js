/*
 * Market Watch panel: shows all markets with live prices updating per tick.
 * Displays "Waiting for signal" status for each market until a signal is generated.
 */
(function () {
    const container = document.getElementById("market-watch-body");
    if (!container) return;

    // Import market catalog from Python context (passed via data attribute or global)
    const markets = window.AVAILABLE_MARKETS || {};

    function formatSymbol(sym) {
        // Internal symbol names are already in correct Deriv API format
        // No conversion needed
        return sym;
    }

    const lastPrices = {};
    const marketStatus = {}; // Track signal status per market

    function fmt(n, digits = 2) {
        return n === null || n === undefined ? "—" : Number(n).toFixed(digits);
    }

    function renderMarketRow(symbol, name, price = null, status = "waiting") {
        const digits = price && price < 10 ? 5 : 2;
        const priceDisplay = price !== null ? fmt(price, digits) : "Loading...";
        const statusClass = status === "signal" ? "signal-active" : "waiting";
        const statusText = status === "signal" ? "Analysis" : "Waiting for signal";
        const priceClass = price !== null ? (lastPrices[symbol] !== undefined && price >= lastPrices[symbol] ? "price-up" : "price-down") : "";
        
        return `
            <tr data-symbol="${symbol}" class="market-row">
                <td class="market-name">${name}</td>
                <td class="market-price ${priceClass}">${priceDisplay}</td>
                <td class="market-status ${statusClass}">${statusText}</td>
            </tr>
        `;
    }

    function updateMarketPrice(symbol, price) {
        const row = container.querySelector(`tr[data-symbol="${symbol}"]`);
        if (!row) return;

        const priceEl = row.querySelector(".market-price");
        const prev = lastPrices[symbol];
        const digits = price < 10 ? 5 : 2;
        
        priceEl.textContent = fmt(price, digits);
        row.classList.remove("up", "down");
        
        if (prev !== undefined) {
            row.classList.add(price >= prev ? "up" : "down");
        }
        
        lastPrices[symbol] = price;
    }

    function updateMarketStatus(symbol, status, direction = null) {
        const row = container.querySelector(`tr[data-symbol="${symbol}"]`);
        if (!row) return;

        const statusEl = row.querySelector(".market-status");
        statusEl.classList.remove("waiting", "signal-active");
        
        if (status === "signal") {
            statusEl.classList.add("signal-active");
            if (direction) {
                statusEl.textContent = `${direction} Signal`;
            } else {
                statusEl.textContent = "Analyzing";
            }
        } else {
            statusEl.classList.add("waiting");
            statusEl.textContent = "Scanning";
        }
        
        marketStatus[symbol] = status;
    }

    function initializeMarketWatch() {
        const rows = Object.entries(markets).map(([symbol, name]) => 
            renderMarketRow(symbol, name)
        ).join("");
        container.innerHTML = rows;
    }

    let ws = null;
    let reqId = 1;

    function connectWebSocket() {
        ws = new WebSocket(`wss://ws.binaryws.com/websockets/v3?app_id=${window.DERIV_APP_ID}`);
        
        ws.onopen = () => {
            // Only authorize if we have a valid non-empty token
            if (window.DERIV_API_TOKEN && window.DERIV_API_TOKEN.trim() !== "") {
                ws.send(JSON.stringify({ authorize: window.DERIV_API_TOKEN }));
            }
            
            // Subscribe to all markets
            Object.keys(markets).forEach((symbol) => {
                ws.send(JSON.stringify({ ticks: formatSymbol(symbol), subscribe: 1, req_id: reqId++ }));
            });
        };

        ws.onmessage = (evt) => {
            const data = JSON.parse(evt.data);
            
            // Handle authorization response
            if (data.msg_type === "authorize") {
                if (data.error) {
                    console.error('Market watch authorization error:', data.error);
                } else {
                    console.log('Market watch authorization successful');
                }
                return;
            }
            
            if (data.error || !data.tick) return;
            
            const symbol = data.tick.symbol;
            // Map back to our internal symbol
            const internalSymbol = Object.keys(SYMBOL_MAP).find(key => SYMBOL_MAP[key] === symbol) || symbol;
            
            if (markets[internalSymbol]) {
                updateMarketPrice(internalSymbol, data.tick.quote);
            }
        };

        ws.onclose = () => setTimeout(connectWebSocket, 4000);
        ws.onerror = () => ws.close();
    }

    // Listen for signal updates from analysis WebSocket
    function connectAnalysisWebSocket() {
        const proto = window.location.protocol === "https:" ? "wss" : "ws";
        const ws = new WebSocket(`${proto}://${window.location.host}/ws/analysis/`);
        
        ws.onmessage = (evt) => {
            let data;
            try {
                data = JSON.parse(evt.data);
            } catch (e) {
                return;
            }
            
            if (data.type === "signal" && data.signal) {
                // Update status to signal active for this market with direction
                updateMarketStatus(data.signal.symbol, "signal", data.signal.direction);
                
                // Reset to waiting after 30 seconds
                setTimeout(() => {
                    updateMarketStatus(data.signal.symbol, "waiting");
                }, 30000);
            }
        };
        
        ws.onclose = () => setTimeout(connectAnalysisWebSocket, 3000);
        ws.onerror = () => ws.close();
    }

    initializeMarketWatch();
    connectWebSocket();
    connectAnalysisWebSocket();
})();
