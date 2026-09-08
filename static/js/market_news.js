/*
 * Market News functionality for AI Strategy page.
 * Fetches and displays market news with impact analysis.
 */
(function () {
    const form = document.getElementById('mn-filter-form');
    const grid = document.getElementById('mn-grid');
    const storiesCount = document.getElementById('mn-stories-count');
    const highImpactCount = document.getElementById('mn-high-impact-count');

    if (!form || !grid) return;

    function esc(s) {
        return String(s || '').replace(/[&<>"']/g, function (c) {
            return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
        });
    }

    function formatTime(dateStr) {
        const date = new Date(dateStr);
        const now = new Date();
        const diff = Math.floor((now - date) / 1000);
        
        if (diff < 60) return `${diff}s ago`;
        if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
        return date.toLocaleDateString();
    }

    function row(item) {
        const markets = (item.markets || []).map(function (m) {
            return '<span class="mn-badge mn-badge--market">' + esc(m) + '</span>';
        }).join('');
        
        return '' +
            '<article class="mn-row' + (item.high_impact ? ' is-high-impact' : '') + '">' +
                '<div class="mn-col--time">' + esc(item.published || formatTime(item.publishedAt)) + '</div>' +
                '<div class="mn-col--impact">' +
                    '<span class="mn-impact mn-impact--' + esc(item.impact_level || 'low') + '">' + esc(String(item.impact_level || 'low').toUpperCase()) + '</span>' +
                    '<span class="mn-time-window">' + esc(item.impact_time_window || '') + '</span>' +
                '</div>' +
                '<div class="mn-col--headline">' +
                    '<div class="mn-main">' +
                        '<h2 class="mn-card-title"><a href="' + esc(item.url || item.link || '#') + '" target="_blank" rel="noopener noreferrer">' + esc(item.title) + '</a></h2>' +
                        '<p class="mn-meta">' + esc(item.source || 'News') + (item.impact_category ? ' · ' + esc(item.impact_category) : '') + '</p>' +
                        '<p class="mn-line"><strong>Effect:</strong> ' + esc(item.effect || item.market_analysis || '') + '</p>' +
                        '<p class="mn-line"><strong>Why:</strong> ' + esc(item.why || '') + '</p>' +
                    '</div>' +
                '</div>' +
                '<div class="mn-col--market">' + markets + '</div>' +
            '</article>';
    }

    function render(items) {
        if (!items || !items.length) {
            grid.innerHTML = '<div class="mn-empty">No market news found for this filter.</div>';
            if (storiesCount) storiesCount.textContent = '0';
            if (highImpactCount) highImpactCount.textContent = '0';
            return;
        }
        
        grid.innerHTML = items.map(row).join('');
        
        if (storiesCount) storiesCount.textContent = items.length;
        if (highImpactCount) {
            const highImpact = items.filter(function (item) { return item.high_impact; }).length;
            highImpactCount.textContent = highImpact;
        }
    }

    function fetchAndRender(pushState) {
        const params = new URLSearchParams(new FormData(form));
        params.set('limit', '30');
        const url = '/api/ai/news/?' + params.toString();
        
        console.log('Fetching market news from:', url);
        
        fetch(url, {headers: {'Accept': 'application/json'}})
            .then(function (r) { 
                console.log('Response status:', r.status);
                return r.json(); 
            })
            .then(function (data) {
                console.log('Received data:', data);
                const items = data.news || [];
                console.log('News items:', items);
                
                // Transform items to match expected format
                const transformedItems = items.map(function (item) {
                    return {
                        title: item.title,
                        url: item.url,
                        image: item.image,
                        published: item.publishedAt,
                        source: 'News',
                        impact_level: item.sentiment > 0.3 ? 'high' : item.sentiment < -0.3 ? 'high' : 'low',
                        impact_time_window: '',
                        impact_category: item.category,
                        high_impact: Math.abs(item.sentiment) > 0.3,
                        effect: item.market_analysis,
                        why: item.description || item.content,
                        markets: [item.category || 'general']
                    };
                });
                console.log('Transformed items:', transformedItems);
                render(transformedItems);
                if (pushState && window.history) {
                    window.history.replaceState({}, '', window.location.pathname + '?' + params.toString());
                }
            })
            .catch(function (err) {
                console.error('Failed to fetch market news:', err);
                grid.innerHTML = '<div class="mn-empty">Failed to load market news.</div>';
            });
    }

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        fetchAndRender(true);
    });

    // Initial load
    fetchAndRender(false);

    // Auto-refresh every 60 seconds
    setInterval(function () { fetchAndRender(false); }, 60000);
})();
