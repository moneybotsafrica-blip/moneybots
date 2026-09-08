/*
 * "News affecting this signal" — shared between the Analysis page's news
 * panel (full list, one column) and the brain panel's Insight tab (compact
 * card, top few events). Both just call fetchRelevant() and hand the
 * events to a render function; only markup density differs.
 *
 * Backend: GET /news/relevant/?symbol=<key>&market_name=<display name>
 * -> { is_live, currencies, is_synthetic, events: [...] }
 * Forex/gold markets get events for their currency legs; synthetic and
 * volatility indices (no real underlying) fall back to global high-impact
 * events, flagged via is_synthetic so the UI can explain why.
 */
(function () {
    async function fetchRelevant(symbol, marketName) {
        const params = new URLSearchParams({ symbol: symbol || "", market_name: marketName || "" });
        const res = await fetch(`/news/relevant/?${params.toString()}`);
        if (!res.ok) throw new Error(`news fetch failed: ${res.status}`);
        return res.json();
    }

    function relTime(iso, isUpcoming) {
        const diffMs = new Date(iso) - Date.now();
        const abs = Math.abs(diffMs);
        const mins = Math.round(abs / 60000);
        let label;
        if (mins < 60) label = `${mins}m`;
        else if (mins < 60 * 24) label = `${Math.round(mins / 60)}h`;
        else label = `${Math.round(mins / (60 * 24))}d`;
        return isUpcoming ? `in ${label}` : `${label} ago`;
    }

    function eventRow(ev, compact) {
        const dir = ev.is_upcoming ? "upcoming" : "released";
        const actual = ev.actual ? `<span class="ai-news-figure">A: ${ev.actual}</span>` : "";
        const forecast = ev.forecast ? `<span class="ai-news-figure">F: ${ev.forecast}</span>` : "";
        const figures = !compact && (actual || forecast)
            ? `<div class="ai-news-figures">${actual}${forecast}</div>`
            : "";
        return `
            <div class="ai-news-item ai-news-${dir}">
                <i class="impact-dot ${ev.impact_class}" title="${ev.impact} impact"></i>
                <div class="ai-news-body">
                    <div class="ai-news-title-row">
                        <span class="ai-news-currency">${ev.country}</span>
                        <span class="ai-news-headline">${ev.title}</span>
                    </div>
                    ${figures}
                </div>
                <span class="ai-news-when ${dir}">${relTime(ev.datetime, ev.is_upcoming)}</span>
            </div>`;
    }

    function render(container, data, { compact = false, countEl = null } = {}) {
        if (!container) return;
        const events = compact ? (data.events || []).slice(0, 5) : (data.events || []);

        if (countEl) {
            countEl.textContent = data.events && data.events.length
                ? `${data.events.length} event${data.events.length === 1 ? "" : "s"}`
                : "—";
        }

        if (!data.is_live) {
            container.innerHTML = `<div class="ai-news-empty">News feed unavailable right now — try again shortly.</div>`;
            return;
        }
        if (!events.length) {
            container.innerHTML = data.is_synthetic
                ? `<div class="ai-news-empty">Synthetic/volatility index — algorithmically generated, not driven by economic news. Showing nothing high-impact in range.</div>`
                : `<div class="ai-news-empty">No ${data.currencies.join("/")} events in the surrounding window.</div>`;
            return;
        }

        const header = data.is_synthetic
            ? `<div class="ai-news-context">Synthetic index — no direct currency exposure. Showing global high-impact events for context.</div>`
            : `<div class="ai-news-context">Tracking ${data.currencies.join(", ")} events.</div>`;

        container.innerHTML = (compact ? "" : header) + events.map((ev) => eventRow(ev, compact)).join("");
    }

    async function refresh(symbol, marketName, container, opts) {
        if (!container) return;
        try {
            const data = await fetchRelevant(symbol, marketName);
            render(container, data, opts);
        } catch (e) {
            container.innerHTML = `<div class="ai-news-empty">Couldn't load news — check the server is running.</div>`;
        }
    }

    // ---- Analysis page: hook to the market filter select ----
    function attachToFilter(selectId, listId, countId) {
        const select = document.getElementById(selectId);
        const list = document.getElementById(listId);
        const countEl = countId ? document.getElementById(countId) : null;
        if (!select || !list) return;

        function currentMarketName() {
            const opt = select.selectedOptions[0];
            return opt ? opt.textContent : "";
        }

        function load() {
            refresh(select.value, currentMarketName(), list, { compact: false, countEl });
        }

        select.addEventListener("change", load);
        load();
        setInterval(load, 60000);
    }

    window.SignalNews = { fetchRelevant, render, refresh, attachToFilter };

    // Self-init for the Analysis page — runs wherever this script is loaded
    // from (base.html), no matter its position relative to the page's own
    // content block, since DOMContentLoaded only fires once parsing (incl.
    // all synchronous scripts) is done.
    document.addEventListener("DOMContentLoaded", () => {
        if (document.getElementById("analysis-symbol-filter") && document.getElementById("analysis-news-list")) {
            attachToFilter("analysis-symbol-filter", "analysis-news-list", "analysis-news-count");
        }
    });
})();
