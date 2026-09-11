/*
 * Floating AI chart panel: Insight, Analysis, Chat.
 * Sends the open chart's symbol, live price, and candles to /api/ai/.
 * 
 * Features:
 * - Multi-tab interface (Insight, Analysis, Gap Analysis, Chat)
 * - Voice recording for questions and news analysis
 * - Real-time chart data integration
 * - AI-powered market analysis and recommendations
 */
(function () {
    // DOM Elements
    const fab = document.getElementById("brain-fab");
    if (!fab) return;

    if (!window.AI_ENABLED) {
        fab.addEventListener("click", () => {
            alert("To enable the AI chart panel, set GROQ_API_KEY or ANTHROPIC_API_KEY in .env and restart the server.");
        });
        return;
    }

    const panel = document.getElementById("brain-panel");
    if (!panel) return;

    const closeBtn = document.getElementById("brain-close");
    const messages = document.getElementById("brain-messages");
    const form = document.getElementById("brain-form");
    const input = document.getElementById("brain-input");
    const voiceBtn = document.getElementById("brain-voice");
    const voiceStatus = document.getElementById("brain-voice-status");
    const voiceMode = document.getElementById("brain-voice-mode");
    const voiceModeMic = document.getElementById("brain-voice-mode-mic");
    const voiceModeClose = document.getElementById("brain-voice-mode-close");
    const voiceModeStatus = document.getElementById("brain-voice-mode-status");
    const symbolLabel = document.getElementById("brain-current-symbol");

    const tabs = panel.querySelectorAll(".brain-tab");
    const tabPanels = {
        insight: document.getElementById("brain-panel-insight"),
        analysis: document.getElementById("brain-panel-analysis"),
        chat: document.getElementById("brain-panel-chat"),
    };

    // State management
    const history = [];
    let open = false;
    let recorder = null;
    let recordingChunks = [];
    let recordingStartTime = null;
    let recordingTimer = null;
    let voiceModeActive = false;
    
    // Technical indicator mapping for TradingView
    const STUDY_MAP = {
        RSI: "Relative Strength Index",
        MACD: "MACD",
        MA: "Moving Average",
        MASIMPLE: "Moving Average",
        BB: "Bollinger Bands",
        ATR: "Average True Range",
        STOCHASTIC: "Stochastic",
    };

    // Chart data functions
    function currentSymbol() {
        return window.currentChartSymbol || "";
    }

    function livePrice(symbol) {
        if (window.currentChartPrice != null && (!symbol || symbol === window.currentChartSymbol)) {
            return Number(window.currentChartPrice);
        }
        if (window.marketDataService && symbol) {
            const quoted = window.marketDataService.getPrice(symbol);
            if (quoted != null) return Number(quoted);
        }
        return null;
    }

    function chartCandles(symbol) {
        if (window.marketDataService && symbol) {
            const bars = window.marketDataService.getCandles(symbol);
            if (bars && bars.length) return bars.slice(-240);
        }
        if (window.currentCandleData && symbol === window.currentChartSymbol) {
            return [window.currentCandleData];
        }
        return [];
    }

    function chartPayload() {
        const symbol = currentSymbol();
        return {
            symbol: symbol,
            price: livePrice(symbol),
            candles: chartCandles(symbol),
            timeframe: "60",
        };
    }

    function validateChartPayload(payload) {
        if (!payload.symbol) {
            return { valid: false, error: "No symbol selected" };
        }
        if (!payload.candles || payload.candles.length === 0) {
            return { valid: false, error: "No candle data available" };
        }
        return { valid: true };
    }

    // TradingView chart interaction functions
    function withChart(fn) {
        const widget = window.tradingViewWidget;
        if (!widget || typeof widget.activeChart !== "function") {
            return { error: "Chart not ready" };
        }
        const run = function () {
            try {
                fn(widget.activeChart());
            } catch (err) {
                console.warn("AI chart action failed", err);
            }
        };
        if (typeof widget.onChartReady === "function") {
            widget.onChartReady(run);
        } else {
            run();
        }
        return { success: true };
    }

    // AI chart actions for TradingView integration
    window.aiChartActions = {
        addIndicator: function (name) {
            const mapped = STUDY_MAP[String(name || "").toUpperCase()] || name;
            return withChart(function (chart) {
                chart.createStudy(mapped, false, false);
            });
        },
        addHorizontalLine: function (price, color, text) {
            return withChart(function (chart) {
                chart.createShape(
                    { price: Number(price) },
                    {
                        shape: "horizontal_line",
                        lock: false,
                        disableSelection: false,
                        overrides: {
                            linecolor: color || "#26a69a",
                            linewidth: 2,
                            showLabel: Boolean(text),
                            text: text || "",
                        },
                    }
                );
            });
        },
        clearShapes: function () {
            return withChart(function (chart) {
                chart.removeAllShapes();
            });
        },
        applyActions: function (actions) {
            if (!Array.isArray(actions)) return;
            actions.forEach(function (action) {
                const type = (action && action.type) || "";
                if (type === "clear") window.aiChartActions.clearShapes();
                else if (type === "indicator") window.aiChartActions.addIndicator(action.name);
                else if (type === "hline") {
                    window.aiChartActions.addHorizontalLine(action.price, action.color, action.text);
                }
            });
        },
    };

    // UI state management functions
    function setOpen(next) {
        open = next;
        panel.classList.toggle("open", open);
        panel.setAttribute("aria-hidden", open ? "false" : "true");
        fab.classList.toggle("active", open);
        if (open) {
            updateSymbolLabel();
            refreshInsight();
            renderMarketsWithNews();
        }
    }

    function setTab(name) {
        tabs.forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
        Object.entries(tabPanels).forEach(([key, el]) => {
            if (el) {
                if (key === name) {
                    el.hidden = false;
                    el.style.display = 'flex';
                    // Force reflow to ensure proper rendering
                    void el.offsetHeight;
                    // Ensure chat messages are visible when switching to chat tab
                    if (key === "chat" && messages) {
                        messages.scrollTop = messages.scrollHeight;
                    }
                } else {
                    el.hidden = true;
                    el.style.display = 'none';
                }
            }
        });
        if (name === "chat" && input) input.focus();
    }

    function updateSymbolLabel() {
        const symbol = currentSymbol();
        let label = symbol || "—";
        if (window.AVAILABLE_MARKETS && symbol) {
            const market = window.AVAILABLE_MARKETS.find((m) => m.symbol === symbol);
            if (market) label = market.name;
        }
        if (symbolLabel) symbolLabel.textContent = label;
    }

    // Event listeners for UI interactions
    fab.addEventListener("click", () => setOpen(!open));
    closeBtn.addEventListener("click", () => setOpen(false));
    tabs.forEach((tab) => tab.addEventListener("click", () => setTab(tab.dataset.tab)));

    // Insight panel elements and functions
    const dirBadge = document.getElementById("ai-dir-badge");
    const marketName = document.getElementById("ai-market-name");
    const updatedEl = document.getElementById("ai-updated");
    const emptyEl = document.getElementById("ai-insight-empty");
    const fields = {
        price: document.getElementById("m-price"),
        strength: document.getElementById("m-strength"),
        opportunity: document.getElementById("m-opportunity"),
        rsi: document.getElementById("m-rsi"),
        atr: document.getElementById("m-atr"),
        risk: document.getElementById("m-risk"),
        sl: document.getElementById("m-sl"),
        tp: document.getElementById("m-tp"),
        rr: document.getElementById("m-rr"),
        conf: document.getElementById("m-conf"),
    };

    // Utility functions for formatting
    function fmt(n, digits) {
        const value = Number(n);
        if (!Number.isFinite(value)) return "—";
        return value.toFixed(digits == null ? 2 : digits);
    }

    function dirClass(dir) {
        return dir === "Buy" ? "buy" : dir === "Sell" ? "sell" : "neutral";
    }

    function paintPrice() {
        const symbol = currentSymbol();
        const price = livePrice(symbol);
        if (fields.price && price != null) {
            fields.price.textContent = fmt(price, price < 10 ? 5 : 2);
        }
    }

    const newsList = document.getElementById("ai-news-list");
    const newsDot = document.getElementById("ai-news-dot");
    const newsMarkets = document.getElementById("ai-news-markets");
    const analyzeNewsBtn = document.getElementById("analyze-news-btn");
    const newsBackBtn = document.getElementById("ai-news-back-btn");
    const voiceNewsBtn = document.getElementById("brain-voice-news");
    const newsForm = document.getElementById("news-form");
    const newsInput = document.getElementById("news-input");
    const attachBtn = document.querySelector(".brain-attach");
    let selectedNewsMarket = null;
    let newsRecorder = null;
    let newsRecordingChunks = [];

    async function fetchMarketsWithNews() {
        try {
            const res = await fetch("/api/ai/news/");
            const data = await res.json();
            
            if (data.error) {
                console.error("News API error:", data.error);
                if (newsMarkets) {
                    newsMarkets.innerHTML = `<div class="ai-news-empty">News error: ${data.error}</div>`;
                }
                return {};
            }
            
            const news = data.news || [];
            
            // Group news by markets
            const marketNewsMap = {};
            news.forEach(article => {
                const markets = article.markets || [article.category || 'general'];
                markets.forEach(market => {
                    if (!marketNewsMap[market]) {
                        marketNewsMap[market] = [];
                    }
                    marketNewsMap[market].push(article);
                });
            });

            return marketNewsMap;
        } catch (e) {
            console.error("Failed to fetch markets with news:", e);
            if (newsMarkets) {
                newsMarkets.innerHTML = `<div class="ai-news-empty">Failed to load news. Please try again later.</div>`;
            }
            return {};
        }
    }

    async function renderMarketsWithNews() {
        if (!newsMarkets) return;
        
        const marketNewsMap = await fetchMarketsWithNews();
        const markets = Object.keys(marketNewsMap);
        
        if (markets.length === 0) {
            newsMarkets.innerHTML = '<div class="ai-news-empty">No markets with recent news.</div>';
            return;
        }

        const marketButtons = markets.map(market => {
            const count = marketNewsMap[market].length;
            return `<button class="ai-news-market-btn" data-market="${market}">${market} (${count})</button>`;
        }).join('');

        newsMarkets.innerHTML = `<div class="ai-news-markets-grid">${marketButtons}</div>`;

        // Add click handlers
        document.querySelectorAll('.ai-news-market-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const market = this.dataset.market;
                selectMarketForNews(market, marketNewsMap[market]);
            });
        });
    }

    function selectMarketForNews(market, newsArticles) {
        selectedNewsMarket = market;
        
        // Update UI to show selected market news
        newsMarkets.style.display = 'none';
        newsList.style.display = 'block';
        analyzeNewsBtn.style.display = 'block';
        if (newsForm) {
            newsForm.style.display = 'flex';
            // Clear any previous input
            if (newsInput) newsInput.value = '';
        }

        // Render news articles
        const newsHtml = newsArticles.map(article => {
            const title = (article.title || '').replace(/[&<>"']/g, function(c) {
                return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
            });
            const sentiment = article.sentiment ? article.sentiment.toFixed(2) : 'N/A';
            return `
            <div class="ai-news-item">
                <div class="ai-news-body">
                    <div class="ai-news-title-row">
                        <span class="ai-news-headline">${title}</span>
                    </div>
                    <div class="ai-news-sentiment">Sentiment: ${sentiment}</div>
                </div>
            </div>`;
        }).join('');

        newsList.innerHTML = newsHtml || '<div class="ai-news-empty">No news articles for this market.</div>';
    }

    function backToMarkets() {
        selectedNewsMarket = null;
        newsMarkets.style.display = 'block';
        newsList.style.display = 'none';
        analyzeNewsBtn.style.display = 'none';
        if (newsForm) newsForm.style.display = 'none';
    }

    // Add click handler for back button
    if (newsBackBtn) {
        newsBackBtn.addEventListener("click", backToMarkets);
    }

    async function analyzeMarketNews() {
        if (!selectedNewsMarket) {
            alert("Please select a market first.");
            return;
        }
        
        analyzeNewsBtn.textContent = "Analyzing...";
        analyzeNewsBtn.disabled = true;

        try {
            const res = await fetch("/api/ai/news/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ 
                    market: selectedNewsMarket,
                    action: "analyze"
                }),
            });
            
            if (!res.ok) {
                throw new Error(`HTTP error! status: ${res.status}`);
            }
            
            const data = await res.json();
            
            if (data.error) {
                // Provide user-friendly error message
                let errorMsg = data.error;
                if (errorMsg.includes("API key") || errorMsg.includes("Invalid")) {
                    errorMsg = "AI API key issue. Please check your .env file has GROQ_API_KEY or ANTHROPIC_API_KEY set.";
                }
                alert("Analysis failed: " + errorMsg);
            } else {
                // Show analysis results in the chat tab
                setTab("chat");
                addMessage("ai", data.response || "Analysis completed for " + selectedNewsMarket);
            }
        } catch (e) {
            console.error("News analysis error:", e);
            alert("Could not reach the analysis API. Please check your internet connection and try again.");
        } finally {
            analyzeNewsBtn.textContent = "Analyze Market News";
            analyzeNewsBtn.disabled = false;
        }
    }

    // Add click handler for analyze news button
    if (analyzeNewsBtn) {
        analyzeNewsBtn.addEventListener("click", analyzeMarketNews);
    }

    // Voice recording for news analysis
    let newsRecordingStartTime = null;
    let newsRecordingTimer = null;

    async function startNewsRecording() {
        if (!navigator.mediaDevices || !window.MediaRecorder) {
            alert("Voice recording is not supported by this browser.");
            return;
        }
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            newsRecordingChunks = [];
            newsRecordingStartTime = Date.now();
            newsRecorder = new MediaRecorder(stream);
            
            // Start recording timer
            newsRecordingTimer = setInterval(() => {
                const elapsed = Math.floor((Date.now() - newsRecordingStartTime) / 1000);
                const minutes = Math.floor(elapsed / 60);
                const seconds = elapsed % 60;
                voiceNewsBtn.title = `Recording… ${minutes}:${seconds.toString().padStart(2, '0')} — Click to stop`;
            }, 1000);
            
            newsRecorder.ondataavailable = (event) => {
                if (event.data.size) newsRecordingChunks.push(event.data);
            };
            
            newsRecorder.onstop = async () => {
                clearInterval(newsRecordingTimer);
                stream.getTracks().forEach((track) => track.stop());
                voiceNewsBtn.classList.remove("is-recording");
                voiceNewsBtn.disabled = true;
                voiceNewsBtn.title = "Record voice for news analysis";
                
                try {
                    const blob = new Blob(newsRecordingChunks, { type: newsRecorder.mimeType || "audio/webm" });
                    const formData = new FormData();
                    formData.append("audio", blob, "voice-news.webm");
                    const response = await fetch("/api/ai/transcribe/", { method: "POST", body: formData });
                    const data = await response.json();
                    
                    if (!response.ok || data.error) throw new Error(data.error || "Transcription failed.");
                    
                    // Put the transcribed text in the input field
                    newsInput.value = data.text;
                    newsInput.focus();
                } catch (error) {
                    alert(error.message || "Could not transcribe the recording.");
                } finally {
                    voiceNewsBtn.disabled = false;
                }
            };
            
            newsRecorder.start();
            voiceNewsBtn.classList.add("is-recording");
            voiceNewsBtn.title = "Recording… 0:00 — Click to stop";
        } catch (error) {
            alert("Microphone access was denied or unavailable.");
        }
    }

    if (voiceNewsBtn) {
        voiceNewsBtn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (newsRecorder && newsRecorder.state === "recording") {
                newsRecorder.stop();
            } else {
                startNewsRecording();
            }
        });
    }

    // Prevent attach button from submitting form
    if (attachBtn) {
        attachBtn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            // File attachment functionality can be added here
            alert("File attachment feature coming soon!");
        });
    }

    // News form submission handler
    if (newsForm) {
        newsForm.addEventListener("submit", (e) => {
            e.preventDefault();
            const value = newsInput.value.trim();
            if (!value || !selectedNewsMarket) return;
            
            // Switch to chat tab and send the news-related question
            setTab("chat");
            addMessage("user", `Analyze the news for ${selectedNewsMarket}: ${value}`);
            
            // Add thinking indicator
            const thinking = addMessage("ai", "thinking");
            
            // Trigger the news analysis with the text input
            fetch("/api/ai/news/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ 
                    market: selectedNewsMarket,
                    action: "analyze",
                    question: value
                }),
            })
            .then(res => res.json())
            .then(analysisData => {
                thinking.remove();
                
                if (analysisData.error) {
                    addMessage("ai", "Analysis failed: " + analysisData.error);
                } else {
                    addMessage("ai", analysisData.response || "Analysis completed for " + selectedNewsMarket);
                }
            })
            .catch(e => {
                thinking.remove();
                addMessage("ai", "Could not reach the analysis API. Please check your internet connection.");
            });
            
            // Clear the input
            newsInput.value = "";
        });
    }

    async function refreshInsight() {
        const symbol = currentSymbol();
        if (!symbol || !dirBadge) return;

        let marketLabel = symbol;
        if (window.AVAILABLE_MARKETS) {
            const market = window.AVAILABLE_MARKETS.find((m) => m.symbol === symbol);
            if (market) marketLabel = market.name;
        }

        if (window.SignalNews && newsList) {
            window.SignalNews.refresh(symbol, marketLabel, newsList, { compact: true }).then(() => {
                if (newsDot) newsDot.classList.add("live");
            });
        }

        try {
            const res = await fetch("/api/signals/active/?symbol=" + encodeURIComponent(symbol));
            const data = await res.json();
            const signal = (data.signals || [])[0];
            marketName.textContent = (signal && signal.market_name) || marketLabel;
            paintPrice();

            if (!signal) {
                emptyEl.style.display = "block";
                emptyEl.textContent = "No stored signal yet. Open Analysis to run AI on this chart's candles.";
                dirBadge.textContent = "—";
                dirBadge.className = "dir-badge neutral";
                updatedEl.textContent = "live";
                ["strength", "opportunity", "rsi", "atr", "risk", "sl", "tp", "rr", "conf"].forEach((key) => {
                    if (fields[key]) fields[key].textContent = "—";
                });
                return;
            }

            emptyEl.style.display = "none";
            dirBadge.textContent = signal.direction;
            dirBadge.className = "dir-badge " + dirClass(signal.direction);
            updatedEl.textContent = new Date(signal.updated_at || Date.now()).toLocaleTimeString();
            const price = livePrice(symbol);
            const shown = price != null ? price : signal.current_price != null ? signal.current_price : signal.price;
            fields.price.textContent = fmt(shown, shown < 10 ? 5 : 2);
            fields.strength.textContent = fmt(signal.signal_strength, 2);
            fields.opportunity.textContent = fmt(signal.opportunity_score, 1);
            fields.rsi.textContent = signal.rsi !== null && signal.rsi !== undefined ? fmt(signal.rsi, 1) : "—";
            fields.atr.textContent = signal.atr !== null && signal.atr !== undefined ? fmt(signal.atr, 4) : "—";
            fields.risk.textContent = signal.risk_level || "—";
            fields.sl.textContent = signal.stop_loss != null ? fmt(signal.stop_loss, 4) : "—";
            fields.tp.textContent = signal.take_profit != null ? fmt(signal.take_profit, 4) : "—";
            fields.rr.textContent = signal.risk_reward ? "1:" + fmt(signal.risk_reward, 1) : "—";
            fields.conf.textContent = signal.model_confidence != null ? fmt(signal.model_confidence * 100, 0) + "%" : "—";
        } catch (e) {
            console.warn("AI insight refresh failed", e);
        }
    }

    window.addEventListener("chart-symbol-changed", (event) => {
        window.currentChartSymbol = event.detail.symbol;
        updateSymbolLabel();
        if (open) refreshInsight();
    });

    window.addEventListener("tick-update", (event) => {
        if (!open) return;
        const symbol = event.detail && event.detail.symbol;
        if (symbol && symbol === currentSymbol()) paintPrice();
    });

    setInterval(() => {
        if (open) {
            updateSymbolLabel();
            paintPrice();
        }
    }, 1000);
    
    setInterval(() => {
        if (open) refreshInsight();
    }, 10000);

    const askBtn = document.getElementById("ask-ai-btn");
    if (askBtn) {
        askBtn.addEventListener("click", () => {
            setTab("chat");
            let name = currentSymbol() || "this market";
            if (window.AVAILABLE_MARKETS && currentSymbol()) {
                const market = window.AVAILABLE_MARKETS.find((m) => m.symbol === currentSymbol());
                if (market) name = market.name;
            }
            input.value = "What's your read on " + name + " right now?";
            input.focus();
        });
    }

    const runBtn = document.getElementById("run-ai-analysis");
    const analysisStatus = document.getElementById("ai-analysis-status");
    const analysisCard = document.getElementById("ai-analysis-card");

    function paintAnalysis(data) {
        const analysis = data.analysis || {};
        const snapshot = data.snapshot || {};
        analysisCard.hidden = false;
        const bias = document.getElementById("ai-analysis-bias");
        const conf = document.getElementById("ai-analysis-conf");
        bias.textContent = analysis.bias || "Neutral";
        bias.className = "dir-badge " + dirClass(analysis.bias);
        conf.textContent = analysis.confidence != null ? analysis.confidence + "% confidence" : "";
        document.getElementById("ai-analysis-summary").textContent = analysis.summary || "";
        document.getElementById("ai-analysis-setup").textContent = analysis.setup ? "Setup: " + analysis.setup : "";
        document.getElementById("ai-analysis-risks").textContent = analysis.risks ? "Risk: " + analysis.risks : "";
        const digits = (snapshot.price || 0) < 10 ? 5 : 2;
        document.getElementById("ai-an-support").textContent = fmt(analysis.support, digits);
        document.getElementById("ai-an-resist").textContent = fmt(analysis.resistance, digits);
        document.getElementById("ai-an-stop").textContent = fmt(analysis.stop, digits);
        document.getElementById("ai-an-target").textContent = fmt(analysis.target, digits);
        if (analysis.rsi == null && snapshot.rsi != null && fields.rsi) {
            fields.rsi.textContent = fmt(snapshot.rsi, 1);
        }
        window.aiChartActions.applyActions(analysis.actions || []);
    }

    async function runChartAnalysis() {
        const payload = chartPayload();
        const validation = validateChartPayload(payload);
        
        if (!validation.valid) {
            analysisStatus.textContent = validation.error;
            analysisStatus.style.color = "var(--warn)";
            return;
        }
        
        analysisStatus.textContent = "Analyzing " + payload.symbol + "…";
        analysisStatus.style.color = "var(--text-dim)";
        runBtn.disabled = true;
        try {
            if ((!payload.candles || payload.candles.length < 20) && window.marketDataService) {
                try {
                    const raw = await window.marketDataService.loadHistoricalData(payload.symbol, {
                        granularity: 60,
                        count: 240,
                        end: "latest",
                    });
                    payload.candles = (raw || []).map(function (c) {
                        return {
                            time: c.epoch ? c.epoch * 1000 : c.time,
                            open: c.open,
                            high: c.high,
                            low: c.low,
                            close: c.close,
                            epoch: c.epoch,
                        };
                    });
                } catch (loadErr) {
                    console.warn("Could not prefetch candles for AI analysis", loadErr);
                }
            }
            const res = await fetch("/api/ai/chart-analysis/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (data.error) {
                analysisStatus.textContent = "Error: " + data.error;
                analysisStatus.style.color = "var(--sell)";
                if (data.snapshot) {
                    paintAnalysis(data);
                }
                return;
            }
            analysisStatus.textContent = data.name || payload.symbol;
            analysisStatus.style.color = "var(--buy)";
            paintAnalysis(data);
        } catch (err) {
            console.error("Chart analysis error:", err);
            analysisStatus.textContent = "Could not reach the analysis API. Please check your connection.";
            analysisStatus.style.color = "var(--sell)";
        } finally {
            runBtn.disabled = false;
        }
    }

    if (runBtn) runBtn.addEventListener("click", runChartAnalysis);

    // Stock analysis functions removed - gap analysis tab removed from deriv chart panel
    // Stock analysis should be implemented separately for stock charts

    function addMessage(role, text) {
        const div = document.createElement("div");
        div.className = "brain-msg brain-msg-" + (role === "user" ? "user" : "ai");
        
        if (role === "ai" && text === "thinking") {
            div.classList.add("brain-msg-thinking");
            div.innerHTML = '<span class="thinking-indicator"><span></span><span></span><span></span></span>';
        } else {
            div.textContent = text;
        }
        
        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight;
        return div;
    }

    // Prevent voice button from triggering form submission
    if (voiceBtn) {
        voiceBtn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
        });
    }

    function speakReply(text) {
        if (!text || !window.speechSynthesis || !window.SpeechSynthesisUtterance) {
            return Promise.resolve();
        }
        window.speechSynthesis.cancel();
        return new Promise((resolve) => {
            const utterance = new SpeechSynthesisUtterance(text.replace(/```[\s\S]*?```/g, ""));
            utterance.rate = 1.02;
            utterance.pitch = 1;
            utterance.onend = resolve;
            utterance.onerror = resolve;
            window.speechSynthesis.speak(utterance);
        });
    }

    async function send(message, voiceReply = false) {
        if (!message || message.trim() === "") {
            return;
        }
        
        const payload = chartPayload();
        const validation = validateChartPayload(payload);
        
        if (!validation.valid) {
            addMessage("ai", "⚠ " + validation.error + " Please select a market on the chart first.");
            return;
        }
        
        addMessage("user", message);
        history.push({ role: "user", content: message });
        const thinking = addMessage("ai", "thinking");
        payload.message = message;
        payload.history = history.slice(0, -1);

        try {
            const res = await fetch("/api/ai/chat/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            
            if (!res.ok) {
                throw new Error(`HTTP error! status: ${res.status}`);
            }
            
            const data = await res.json();
            thinking.remove();
            if (data.error) {
                addMessage("ai", "⚠ " + data.error);
            } else {
                addMessage("ai", data.reply);
                history.push({ role: "assistant", content: data.reply });
                window.aiChartActions.applyActions(data.actions || []);
                if (voiceReply) {
                    setVoiceModeStatus("Speaking...");
                    await speakReply(data.reply);
                    exitVoiceMode();
                }
            }
        } catch (e) {
            console.error("Chat error:", e);
            thinking.remove();
            addMessage("ai", "⚠ Couldn't reach the AI backend — check the server is running and your internet connection.");
            if (voiceReply) exitVoiceMode();
        }
    }

    form.addEventListener("submit", (e) => {
        e.preventDefault();
        const value = input.value.trim();
        if (!value) return;
        input.value = "";
        send(value);
    });

    function setVoiceStatus(message) {
        if (!voiceStatus) return;
        voiceStatus.hidden = !message;
        voiceStatus.textContent = message;
    }

    function setVoiceModeStatus(message) {
        if (voiceModeStatus) voiceModeStatus.textContent = message;
        setVoiceStatus(message);
    }

    function enterVoiceMode() {
        voiceModeActive = true;
        panel.classList.add("voice-mode-open");
        voiceMode.hidden = false;
        setVoiceModeStatus("Tap the microphone to speak");
    }

    function exitVoiceMode() {
        voiceModeActive = false;
        panel.classList.remove("voice-mode-open");
        voiceMode.hidden = true;
        if (recorder && recorder.state === "recording") recorder.stop();
        setVoiceStatus("");
    }

    async function startRecording() {
        if (!navigator.mediaDevices || !window.MediaRecorder) {
            setVoiceModeStatus("Voice recording is not supported by this browser.");
            return;
        }
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            recordingChunks = [];
            recordingStartTime = Date.now();
            recorder = new MediaRecorder(stream);
            
            // Start recording timer
            recordingTimer = setInterval(() => {
                const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
                const minutes = Math.floor(elapsed / 60);
                const seconds = elapsed % 60;
                setVoiceModeStatus(`Listening… ${minutes}:${seconds.toString().padStart(2, '0')}`);
            }, 1000);
            
            recorder.ondataavailable = (event) => {
                if (event.data.size) recordingChunks.push(event.data);
            };
            recorder.onstop = async () => {
                clearInterval(recordingTimer);
                stream.getTracks().forEach((track) => track.stop());
                voiceBtn.classList.remove("is-recording");
                if (voiceModeMic) voiceModeMic.classList.remove("is-recording");
                voiceBtn.disabled = true;
                setVoiceModeStatus("Thinking…");
                try {
                    const blob = new Blob(recordingChunks, { type: recorder.mimeType || "audio/webm" });
                    const formData = new FormData();
                    formData.append("audio", blob, "voice-question.webm");
                    const response = await fetch("/api/ai/transcribe/", { method: "POST", body: formData });
                    const data = await response.json();
                    if (!response.ok || data.error) throw new Error(data.error || "Transcription failed.");
                    setVoiceModeStatus("Thinking…");
                    await send(data.text, true);
                } catch (error) {
                    setVoiceModeStatus(error.message || "Could not transcribe the recording.");
                } finally {
                    voiceBtn.disabled = false;
                }
            };
            recorder.start();
            voiceBtn.classList.add("is-recording");
            if (voiceModeMic) voiceModeMic.classList.add("is-recording");
            setVoiceModeStatus("Listening… 0:00");
        } catch (error) {
            setVoiceModeStatus("Microphone access was denied or unavailable.");
        }
    }

    if (voiceBtn) voiceBtn.addEventListener("click", () => {
        enterVoiceMode();
        if (!recorder || recorder.state !== "recording") startRecording();
    });
    if (voiceModeMic) voiceModeMic.addEventListener("click", () => {
        if (recorder && recorder.state === "recording") recorder.stop();
        else startRecording();
    });
    if (voiceModeClose) voiceModeClose.addEventListener("click", exitVoiceMode);

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && open) setOpen(false);
    });
})();
