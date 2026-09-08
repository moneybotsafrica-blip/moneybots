/*
 * Live News Grid for Terminal Page
 * Displays a grid of news channels with videos
 */
(function () {
    const newsGrid = document.getElementById('news-grid');
    const tickerTrack = document.getElementById('news-ticker-track');
    
    if (!newsGrid) return;

    let channels = [];
    let activePlayers = new Map(); // Track active YouTube players

    // Live-video cache, same pattern/TTL as World Monitor's live-news.ts
    const liveVideoCache = new Map();
    const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

    async function fetchLiveVideoInfo(handle) {
        const cached = liveVideoCache.get(handle);
        if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
            return cached;
        }
        try {
            const res = await fetch(`/news/live/?channel=${encodeURIComponent(handle)}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            const info = { videoId: data.videoId || null, isLive: !!data.isLive, timestamp: Date.now() };
            liveVideoCache.set(handle, info);
            return info;
        } catch (e) {
            console.warn(`[Live News Grid] Live check failed for ${handle}:`, e);
            return { videoId: null, isLive: false, timestamp: Date.now() };
        }
    }

    // Load YouTube IFrame API
    let youtubeAPIReady = false;
    let youtubeAPILoading = false;

    function loadYouTubeAPI() {
        if (youtubeAPIReady || youtubeAPILoading) return;
        youtubeAPILoading = true;
        
        const tag = document.createElement('script');
        tag.src = 'https://www.youtube.com/iframe_api';
        const firstScriptTag = document.getElementsByTagName('script')[0];
        firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
    }

    window.onYouTubeIframeAPIReady = function() {
        youtubeAPIReady = true;
        console.log('[Live News Grid] YouTube API ready');
    };

    async function loadChannels() {
        try {
            const res = await fetch('/news/live-channels/');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            channels = data.channels || [];
            console.log('[Live News Grid] Loaded channels:', channels.length, channels);
            renderGrid();
        } catch (e) {
            console.error('[Live News Grid] Failed to load channels:', e);
            newsGrid.innerHTML = `<div class="news-error">Failed to load channels: ${e.message}</div>`;
        }
    }

    function renderGrid() {
        console.log('[Live News Grid] Rendering grid with', channels.length, 'channels');

        if (channels.length === 0) {
            newsGrid.innerHTML = '<div class="news-empty">No channels available</div>';
            return;
        }

        newsGrid.innerHTML = '';
        channels.forEach((channel, index) => {
            const gridItem = createGridItem(channel, index);
            newsGrid.appendChild(gridItem);
        });

        // Load ticker
        loadTicker(channels);
    }

    function createGridItem(channel, index) {
        const item = document.createElement('div');
        item.className = 'news-grid-item';
        item.dataset.channelId = channel.id;

        const hasVideo = channel.fallback_video_id || channel.hls_url;
        
        if (hasVideo) {
            item.innerHTML = `
                <div id="grid-player-${channel.id}"></div>
                <div class="news-grid-overlay">
                    <div class="news-grid-name">${channel.name}</div>
                    <div class="news-grid-region">${channel.region}</div>
                </div>
            `;
            // Load video in grid item
            loadGridVideo(channel, `grid-player-${channel.id}`);
        } else {
            item.innerHTML = `
                <div class="news-channel-icon">${getChannelInitials(channel.name)}</div>
                <div class="news-grid-overlay">
                    <div class="news-grid-name">${channel.name}</div>
                    <div class="news-grid-region">${channel.region}</div>
                </div>
            `;
        }

        return item;
    }

    function getChannelInitials(name) {
        return name.split(/[\s-]+/).map(w => w[0]).join('').slice(0, 2).toUpperCase();
    }

    async function loadGridVideo(channel, containerId) {
        const container = document.getElementById(containerId);
        if (!container) return;

        if (channel.hls_url) {
            container.innerHTML = `
                <video muted loop style="width:100%;height:100%;object-fit:cover;">
                    <source src="${channel.hls_url}" type="application/x-mpegURL">
                </video>
            `;
            return;
        }

        let videoId = channel.fallback_video_id || null;
        if (channel.handle) {
            const info = await fetchLiveVideoInfo(channel.handle);
            if (info.isLive && info.videoId) {
                videoId = info.videoId;
            }
        }

        if (!videoId) return;

        if (!youtubeAPIReady) {
            loadYouTubeAPI();
            // Retry after API loads
            const checkAPI = setInterval(() => {
                if (youtubeAPIReady) {
                    clearInterval(checkAPI);
                    loadGridVideo(channel, containerId);
                }
            }, 500);
            return;
        }

        const player = new YT.Player(containerId, {
            videoId: videoId,
            playerVars: {
                autoplay: 0,
                mute: 1,
                playsinline: 1,
                rel: 0,
                modestbranding: 1,
                controls: 0
            },
            events: {
                onError: (event) => {
                    console.error('[Live News Grid] Grid player error:', event.data);
                }
            }
        });

        activePlayers.set(containerId, player);
    }

    function loadTicker(channels) {
        if (!tickerTrack) return;
        
        tickerTrack.innerHTML = '';
        
        // Create ticker items from channels
        const tickerItems = channels.map(channel => {
            const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            return `
                <div class="news-ticker-item">
                    <span class="news-ticker-time">${time}</span>
                    <span class="news-ticker-headline">${channel.name}</span>
                </div>
            `;
        });

        // Duplicate items for seamless scrolling
        tickerTrack.innerHTML = tickerItems.join('') + tickerItems.join('');
    }

    // Load channels on page load
    loadChannels();
})();
