"""
Economic calendar data — pulled from Forex Factory's public weekly export
feed (the same JSON endpoint MT4/MT5 "FFC" news indicators use). Cached
hard: FF rate-limits this endpoint to ~2 requests / 5 minutes across every
format (json/xml/csv/ics), so hammering it will just get a "Request
Denied" page back instead of data.
"""
import re
from datetime import datetime, timedelta, timezone

import requests
from django.core.cache import cache

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CACHE_KEY = "ff_calendar_thisweek"
CACHE_SECONDS = 1800  # 30 min — extra buffer under FF's rate limit (2 req / 5 min)
RATE_LIMIT_COOLDOWN_KEY = "ff_calendar_cooldown"
RATE_LIMIT_COOLDOWN_SECONDS = 300  # 5 min cooldown after rate limit

IMPACT_ORDER = {"High": 0, "Medium": 1, "Low": 2, "Holiday": 3, "Non-Economic": 3}


def _impact_class(impact: str) -> str:
    mapping = {
        "High": "impact-high",
        "Medium": "impact-medium",
        "Low": "impact-low",
        "Holiday": "impact-holiday",
        "Non-Economic": "impact-holiday",
    }
    return mapping.get(impact, "impact-low")


def _parse(raw_events):
    events = []
    for e in raw_events:
        try:
            dt = datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        events.append({
            "title": e.get("title", "—"),
            "country": e.get("country", ""),
            "datetime": dt,
            "impact": e.get("impact", "Low"),
            "impact_class": _impact_class(e.get("impact", "Low")),
            "forecast": e.get("forecast") or "",
            "previous": e.get("previous") or "",
            "actual": e.get("actual") or "",
        })
    events.sort(key=lambda ev: ev["datetime"])
    return events


def get_calendar():
    """Returns (events, is_live) — events grouped by day, newest fetch cached.
    Returns stale cached data if rate-limited to prevent hammering FF's API."""
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached, True

    # Check if we're in rate limit cooldown
    cooldown = cache.get(RATE_LIMIT_COOLDOWN_KEY)
    if cooldown is not None:
        # Return empty but don't hammer the API
        return [], False

    try:
        resp = requests.get(CALENDAR_URL, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        
        # Check for rate limit responses (FF returns 429 or HTML error page)
        if resp.status_code == 429 or "Request Denied" in resp.text or "rate limit" in resp.text.lower():
            # Set cooldown to prevent repeated requests
            cache.set(RATE_LIMIT_COOLDOWN_KEY, True, RATE_LIMIT_COOLDOWN_SECONDS)
            # If we have any cached data (even stale), return it
            stale_cached = cache.get(CACHE_KEY)
            if stale_cached is not None:
                return stale_cached, False
            return [], False
        
        resp.raise_for_status()
        events = _parse(resp.json())
        if events:
            cache.set(CACHE_KEY, events, CACHE_SECONDS)
            return events, True
    except (requests.RequestException, ValueError):
        pass

    return [], False


def grouped_by_day(events):
    """[(date, [events...]), ...] in chronological order, for day-header rows."""
    groups = {}
    for ev in events:
        day = ev["datetime"].date()
        groups.setdefault(day, []).append(ev)
    return sorted(groups.items())


def is_upcoming(ev) -> bool:
    return ev["datetime"] >= datetime.now(timezone.utc)


# Gold is quoted and driven almost entirely by USD-denominated macro data
# (rates, CPI, NFP), so treat frxXAUUSD like a USD pair for news purposes.
_EXTRA_CURRENCIES = {
    "frxXAUUSD": ["USD"],
}


def currencies_for_symbol(symbol: str, market_name: str = "") -> list:
    """Which FF calendar currency codes are relevant to a given market.
    Forex pairs (market_name like "EUR/USD") map to both legs; gold maps
    to USD; synthetic/volatility/boom/crash/jump indices are algorithmically
    generated and have no real-world news exposure, so they return []."""
    if symbol in _EXTRA_CURRENCIES:
        return _EXTRA_CURRENCIES[symbol]
    if "/" in market_name:
        codes = re.findall(r"[A-Z]{3}", market_name)
        if codes:
            return codes
    if symbol.startswith("frx"):
        codes = re.findall(r"[A-Z]{3}", symbol[3:])
        if len(codes) >= 2:
            return codes[:2]
    return []


# ---------------------------------------------------------------------------
# YouTube live-stream detection for the terminal's Live News grid.
#
# The old live_news_grid.js just hardcoded each channel's fallback_video_id
# and always played that — never actually checking whether the channel was
# live, so it looked "stuck" on an old recording. World Monitor's approach
# (api/youtube/live.js) is: scrape https://www.youtube.com/@handle/live,
# pull the current videoId out of the page's videoDetails/isLive JSON, and
# cache it for a few minutes. World Monitor also proxies through a
# residential-IP relay because Vercel's edge runtime calls from datacenter
# IPs that YouTube throttles hard; we don't have that problem here since
# this Django app calls out directly from a home/VPS IP, so a direct
# scrape (same regex approach) is enough.
# ---------------------------------------------------------------------------
YOUTUBE_LIVE_CACHE_SECONDS = 300  # 5 min, same TTL World Monitor uses
_YT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def get_live_video_id(handle: str) -> dict:
    """Returns {"video_id": str|None, "is_live": bool, "channel_name": str|None}
    for a YouTube channel handle (e.g. "@CNBC"), cached for 5 minutes."""
    if not handle:
        return {"video_id": None, "is_live": False, "channel_name": None}

    cache_key = f"yt_live_{handle}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    handle = handle if handle.startswith("@") else f"@{handle}"
    result = {"video_id": None, "is_live": False, "channel_name": None}

    try:
        resp = requests.get(
            f"https://www.youtube.com/{handle}/live",
            headers=_YT_HEADERS,
            timeout=8,
            allow_redirects=True,
        )
        if resp.ok:
            html = resp.text
            owner_match = re.search(r'"ownerChannelName"\s*:\s*"([^"]+)"', html)
            if owner_match:
                result["channel_name"] = owner_match.group(1)
            else:
                author_match = re.search(r'"author"\s*:\s*"([^"]+)"', html)
                if author_match:
                    result["channel_name"] = author_match.group(1)

            details_idx = html.find('"videoDetails"')
            if details_idx != -1:
                block = html[details_idx:details_idx + 5000]
                vid_match = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', block)
                live_match = re.search(r'"isLive"\s*:\s*true', block)
                if vid_match and live_match:
                    result["video_id"] = vid_match.group(1)
                    result["is_live"] = True
    except requests.RequestException:
        pass

    # Cache negative results too (shorter TTL) so a dead channel doesn't
    # hammer YouTube every request, but a positive "is live" result stays
    # cached for the full window since streams don't flip every few seconds.
    cache.set(cache_key, result, YOUTUBE_LIVE_CACHE_SECONDS if result["is_live"] else 60)
    return result


def relevant_events(symbol: str, market_name: str = "", hours_back: int = 24, hours_forward: int = 72):
    """Events for the given market's currencies within a time window around
    now. Synthetic/volatility markets (no currencies) fall back to the
    highest-impact global events instead, just for general context."""
    events, is_live = get_calendar()
    currencies = currencies_for_symbol(symbol, market_name)
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=hours_back)
    window_end = now + timedelta(hours=hours_forward)

    windowed = [e for e in events if window_start <= e["datetime"] <= window_end]

    if currencies:
        relevant = [e for e in windowed if e["country"] in currencies]
    else:
        relevant = [e for e in windowed if e["impact"] == "High"]

    relevant.sort(key=lambda e: e["datetime"])
    return relevant, currencies, is_live
