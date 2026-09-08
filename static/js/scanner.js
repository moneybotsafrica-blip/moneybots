/* Intraday scanner. It only visualises validated AI signal records. */
(function () {
    const MODES = {
        scalp: { timeframe: '5M', resolution: '5', interval: 30 * 1000, label: 'Scalping · 5-minute chart' },
        day: { timeframe: '1H', resolution: '60', interval: 60 * 1000, label: 'Day trading · 1-hour chart' },
        swing: { timeframe: '1D', resolution: 'D', interval: 5 * 60 * 1000, label: 'Swing trading · daily chart' },
    };
    // Internal symbol names are already in correct Deriv API format
    function formatSymbol(sym) {
        return sym;
    }
    const TRADE_ARROW_COLORS = { Buy: '#1E88E5', Sell: '#E53935' };

    function init() {
        const fab = document.getElementById('scanner-fab');
        const modal = document.getElementById('scanner-modal');
        const close = document.getElementById('scanner-close');
        const scanButton = document.getElementById('scan-chart-btn');
        const autoButton = document.getElementById('auto-scan-btn');
        const status = document.getElementById('scanner-status');
        const summary = document.getElementById('scanner-summary');
        const entries = document.getElementById('scanner-entries');
        const modeLabel = document.getElementById('scanner-mode-label');
        const modeNote = document.getElementById('scanner-note');
        const modeButtons = Array.from(document.querySelectorAll('[data-scanner-mode]'));
        if (!fab || !modal || !scanButton || !autoButton) return;

        let scanning = false;
        let shapes = [];
        let timer = null;
        let autoEnabled = localStorage.getItem('aiScannerAutoScan') === 'true';
        let mode = localStorage.getItem('aiScannerMode') || 'day';
        if (!MODES[mode]) mode = 'day';

        const scannerSymbol = symbol => formatSymbol(symbol);
        const format = value => Number(value).toFixed(Number(value) < 10 ? 5 : 2);
        const escape = value => String(value || '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
        const cleanName = value => String(value || 'AI Signal').replace(/^\s*QATraders:\s*/i, '').trim() || 'AI Signal';

        function setModal(open) {
            modal.classList.toggle('open', open);
            modal.setAttribute('aria-hidden', String(!open));
            if (open) setModeResolution();
        }

        function setModeResolution() {
            if (!window.tradingViewWidget) return;
            window.tradingViewWidget.onChartReady(() => {
                try { window.tradingViewWidget.activeChart().setResolution(MODES[mode].resolution); } catch (_) { /* chart still loading */ }
            });
        }

        function removeShapes(chart) {
            shapes.forEach(id => { try { chart.removeEntity(id); } catch (_) { /* already removed */ } });
            shapes = [];
        }

        function clearPlots() {
            if (!window.tradingViewWidget || !shapes.length) return;
            window.tradingViewWidget.onChartReady(() => removeShapes(window.tradingViewWidget.activeChart()));
        }

        function validPlan(signal) {
            const entry = Number(signal.price), sl = Number(signal.stop_loss), tp = Number(signal.take_profit);
            if (!Number.isFinite(entry) || !Number.isFinite(sl) || !Number.isFinite(tp)) return false;
            return signal.direction === 'Buy' ? sl < entry && tp > entry : signal.direction === 'Sell' && sl > entry && tp < entry;
        }

        function markerPrice(signal) {
            const entry = Number(signal.price), risk = Math.abs(entry - Number(signal.stop_loss));
            const offset = Math.max(risk * 0.6, Math.abs(entry) * 0.00001, 0.000001);
            return signal.direction === 'Buy' ? entry - offset : entry + offset;
        }

        function barSeconds() {
            return mode === 'scalp' ? 300 : mode === 'swing' ? 86400 : 3600;
        }

        function uniqueHistory(history, active) {
            const usedBars = new Set();
            const activeTime = active ? Math.floor(new Date(active.created_at || active.updated_at).getTime() / 1000) : null;
            const activeBar = Number.isFinite(activeTime) ? Math.floor(activeTime / barSeconds()) : null;
            return history.filter(signal => {
                const time = Math.floor(new Date(signal.created_at || signal.updated_at).getTime() / 1000);
                const bar = Math.floor(time / barSeconds());
                if (!Number.isFinite(time) || bar === activeBar || usedBars.has(bar)) return false;
                usedBars.add(bar);
                return true;
            }).slice(0, 6);
        }

        function addShape(chart, point, options) {
            shapes.push(chart.createShape(point, options));
        }

        function addTradeArrow(chart, signal, time) {
            addShape(chart, { time, price: markerPrice(signal) }, {
                shape: signal.direction === 'Buy' ? 'arrow_up' : 'arrow_down',
                lock: true,
                disableSelection: false,
                disableUndo: false,
                showInObjectsTree: true,
                overrides: {
                    color: TRADE_ARROW_COLORS[signal.direction],
                    fontsize: 8,
                    linewidth: 2,
                }
            });
        }

        function plotActive(signal, expectedSymbol) {
            if (!window.tradingViewWidget) return;
            window.tradingViewWidget.onChartReady(() => {
                const chart = window.tradingViewWidget.activeChart();
                if (scannerSymbol(chart.symbol()) !== expectedSymbol) return;
                removeShapes(chart);
                const time = Math.floor(new Date(signal.created_at || signal.updated_at || Date.now()).getTime() / 1000);
                const digits = Number(signal.price) < 10 ? 5 : 2;
                const level = (price, label, color) => addShape(chart, { time, price: Number(price) }, {
                    shape: 'horizontal_line', lock: true, disableSelection: false, disableUndo: false,
                    showInObjectsTree: true, text: `${label} ${Number(price).toFixed(digits)}`,
                    overrides: { linecolor: color, linewidth: 2, textcolor: color }
                });
                level(signal.price, 'Entry', '#1976D2');
                level(signal.take_profit, 'Take Profit', '#00A86B');
                level(signal.stop_loss, 'Stop Loss', '#E53935');
                addTradeArrow(chart, signal, time);
            });
        }

        function plotHistory(history, expectedSymbol) {
            if (!window.tradingViewWidget) return;
            window.tradingViewWidget.onChartReady(() => {
                const chart = window.tradingViewWidget.activeChart();
                if (scannerSymbol(chart.symbol()) !== expectedSymbol) return;
                history.forEach(signal => {
                    const time = Math.floor(new Date(signal.created_at || signal.updated_at).getTime() / 1000);
                    if (!Number.isFinite(time)) return;
                    addTradeArrow(chart, signal, time);
                });
            });
        }

        function render(active, history, symbol) {
            entries.innerHTML = '';
            if (!active && !history.length) {
                summary.innerHTML = `<strong>${escape(symbol)}</strong> — no validated ${mode} setup is available yet.`;
                return;
            }
            if (active) {
                const entry = Number(active.price), sl = Number(active.stop_loss), tp = Number(active.take_profit);
                const rr = Math.abs(tp - entry) / Math.abs(entry - sl);
                summary.innerHTML = `<strong>${escape(symbol)}</strong> · <b class="${active.direction === 'Buy' ? 'scanner-summary-buy' : 'scanner-summary-sell'}">${escape(active.direction)}</b> · ${escape(cleanName(active.pattern || active.entry_type))}<br>Entry <strong>${format(entry)}</strong> · TP <strong>${format(tp)}</strong> · SL <strong>${format(sl)}</strong> · R:R <strong>${rr.toFixed(2)}</strong>`;
                const card = document.createElement('button');
                card.type = 'button'; card.className = 'scanner-entry';
                card.innerHTML = `<div class="scanner-entry-header"><span class="scanner-entry-type ${active.direction.toLowerCase()}">${escape(cleanName(active.pattern || active.entry_type))}</span><span class="scanner-entry-status active">Active setup</span></div><div class="scanner-entry-details">Tap to replot Entry, Take Profit, and Stop Loss.</div>`;
                card.addEventListener('click', () => plotActive(active, symbol));
                entries.appendChild(card);
            }
            history.slice(0, 12).forEach(signal => {
                const card = document.createElement('div');
                card.className = 'scanner-entry scanner-history-entry';
                card.innerHTML = `<div class="scanner-entry-header"><span class="scanner-entry-type ${signal.direction.toLowerCase()}">${escape(cleanName(signal.pattern || signal.entry_type))}</span><span class="scanner-entry-status">Historical</span></div><div class="scanner-entry-details">${escape(signal.direction)} · Entry ${format(signal.price)} · ${escape(String(signal.pnl_hit || 'closed').toUpperCase())}</div>`;
                entries.appendChild(card);
            });
        }

        async function scan() {
            if (scanning) return;
            const rawSymbol = window.currentChartSymbol;
            if (!rawSymbol) { status.textContent = 'Wait for the chart market to finish loading, then scan again.'; return; }
            const symbol = scannerSymbol(rawSymbol);
            scanning = true; scanButton.disabled = true; clearPlots(); setModeResolution();
            status.textContent = `Scanning ${symbol} for a validated ${mode} setup…`;
            try {
                const query = `symbol=${encodeURIComponent(symbol)}&timeframe=${MODES[mode].timeframe}`;
                const [activeResponse, historyResponse] = await Promise.all([
                    fetch(`/api/signals/active/?${query}`), fetch(`/api/signals/history/?${query}&limit=200`)
                ]);
                if (!activeResponse.ok || !historyResponse.ok) throw new Error('Signal service unavailable');
                const activeData = await activeResponse.json();
                const historyData = await historyResponse.json();
                const active = (activeData.signals || []).find(validPlan) || null;
                const rawHistory = (historyData.signals || []).filter(signal => ['Buy', 'Sell'].includes(signal.direction) && validPlan(signal));
                const history = uniqueHistory(rawHistory, active);
                if (active) plotActive(active, symbol);
                plotHistory(history, symbol);
                render(active, history, symbol);
                status.textContent = active ? `${MODES[mode].label} setup plotted on the chart.` : `No validated ${mode} setup right now. No trade is suggested.`;
            } catch (error) {
                console.error('Scanner error:', error);
                status.textContent = `${MODES[mode].label} signal data is unavailable. Try again after the analysis service reconnects.`;
                summary.textContent = 'No signal was plotted.';
                entries.innerHTML = '';
            } finally {
                scanning = false; scanButton.disabled = false;
            }
        }

        function updateAuto() {
            autoButton.classList.toggle('active', autoEnabled);
            autoButton.setAttribute('aria-pressed', String(autoEnabled));
            autoButton.textContent = autoEnabled ? 'Auto Scan: On' : 'Auto Scan: Off';
        }
        function setAuto(enabled) {
            autoEnabled = enabled; localStorage.setItem('aiScannerAutoScan', String(enabled)); updateAuto();
            if (timer) clearInterval(timer); timer = null;
            if (enabled) { scan(); timer = setInterval(scan, MODES[mode].interval); }
        }

        function setMode(nextMode) {
            mode = MODES[nextMode] ? nextMode : 'day';
            localStorage.setItem('aiScannerMode', mode);
            modeButtons.forEach(button => button.classList.toggle('active', button.dataset.scannerMode === mode));
            modeLabel.textContent = `${MODES[mode].label} - validated Entry / TP / SL`;
            modeNote.textContent = `Auto Scan checks the current market every ${mode === 'scalp' ? '30 seconds' : mode === 'day' ? 'minute' : '5 minutes'}. It does not place trades.`;
            clearPlots();
            setModeResolution();
            if (autoEnabled) setAuto(true);
        }

        fab.addEventListener('click', () => setModal(!modal.classList.contains('open')));
        close.addEventListener('click', () => setModal(false));
        modal.querySelector('.scanner-modal-backdrop').addEventListener('click', () => setModal(false));
        scanButton.addEventListener('click', scan);
        autoButton.addEventListener('click', () => setAuto(!autoEnabled));
        modeButtons.forEach(button => button.addEventListener('click', () => setMode(button.dataset.scannerMode)));
        window.addEventListener('chart-symbol-changed', () => { clearPlots(); if (autoEnabled) setTimeout(scan, 350); });
        document.addEventListener('keydown', event => { if (event.key === 'Escape') setModal(false); });
        setMode(mode);
        updateAuto();
        if (autoEnabled) setAuto(true);
        window.aiScannerActions = { scan, setAuto, setMode, clearPlots };
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
