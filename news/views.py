from datetime import datetime, timezone

from django.http import JsonResponse
from django.shortcuts import render

from dashboard.context import base_context

from .services import get_calendar, get_live_video_id, grouped_by_day, relevant_events


def calendar_page(request):
    events, is_live = get_calendar()
    day_groups = grouped_by_day(events)
    now = datetime.now(timezone.utc)
    ctx = base_context(active_nav="news")
    ctx.update({
        "day_groups": day_groups,
        "is_live": is_live,
        "now": now,
    })
    return render(request, "dashboard/news.html", ctx)


def relevant_news_api(request):
    """News events that could be moving a given market's signal, for the
    Analysis page's news panel and the brain panel's Insight tab. ?symbol=
    is the internal market key, ?market_name= the display name (e.g.
    "EUR/USD") used to derive which currencies matter."""
    symbol = request.GET.get("symbol", "")
    market_name = request.GET.get("market_name", "")
    events, currencies, is_live = relevant_events(symbol, market_name)
    now = datetime.now(timezone.utc)
    
    # Determine data source status
    status = "live" if is_live else "cached" if events else "unavailable"
    
    return JsonResponse({
        "status": status,
        "is_live": is_live,
        "symbol": symbol,
        "currencies": currencies,
        "is_synthetic": not bool(currencies),
        "events": [
            {
                "title": ev["title"],
                "country": ev["country"],
                "datetime": ev["datetime"].isoformat(),
                "impact": ev["impact"],
                "impact_class": ev["impact_class"],
                "forecast": ev["forecast"],
                "previous": ev["previous"],
                "actual": ev["actual"],
                "is_upcoming": ev["datetime"] >= now,
            }
            for ev in events[:25]
        ],
    })


def live_channels_api(request):
    """Live news channels for the terminal page - YouTube channels and news streams."""
    channels = [
        {
            "id": "bloomberg",
            "name": "Bloomberg",
            "handle": "@markets",
            "fallback_video_id": "iEpJwprxDdk",
            "region": "North America"
        },
        {
            "id": "cnbc",
            "name": "CNBC",
            "handle": "@CNBC",
            "fallback_video_id": "9NyxcX3rhQs",
            "region": "North America"
        },
        {
            "id": "sky",
            "name": "Sky News",
            "handle": "@SkyNews",
            "fallback_video_id": "uvviIF4725I",
            "region": "Europe"
        },
        {
            "id": "euronews",
            "name": "Euronews",
            "handle": "@euronews",
            "fallback_video_id": "pykpO5kQJ98",
            "region": "Europe"
        },
        {
            "id": "dw",
            "name": "DW",
            "handle": "@DWNews",
            "fallback_video_id": "LuKwFajn37U",
            "region": "Europe"
        },
        {
            "id": "cnn",
            "name": "CNN",
            "handle": "@CNN",
            "fallback_video_id": "w_Ma8oQLmSM",
            "region": "North America"
        },
        {
            "id": "france24",
            "name": "France 24",
            "handle": "@FRANCE24",
            "fallback_video_id": "u9foWyMSETk",
            "region": "Europe"
        },
        {
            "id": "aljazeera",
            "name": "Al Jazeera",
            "handle": "@AlJazeeraEnglish",
            "fallback_video_id": "gCNeDWCI0vo",
            "region": "Middle East"
        },
        {
            "id": "bbc-news",
            "name": "BBC News",
            "handle": "@BBCNews",
            "fallback_video_id": "bjgQzJzCZKs",
            "region": "Europe"
        },
        {
            "id": "reuters",
            "name": "Reuters TV",
            "hls_url": "https://reuters-reutersnow-1-eu.rakuten.wurl.tv/playlist.m3u8",
            "region": "Global"
        },
        {
            "id": "cna",
            "name": "CNA",
            "handle": "@channelnewsasia",
            "fallback_video_id": "XWq5kBlakcQ",
            "region": "Asia"
        },
        {
            "id": "ndtv",
            "name": "NDTV 24x7",
            "handle": "@NDTV",
            "fallback_video_id": "sYZtOFzM78M",
            "region": "Asia"
        }
    ]
    return JsonResponse({"channels": channels})


def live_video_api(request):
    """Checks whether a given YouTube channel handle is currently live —
    mirrors World Monitor's /api/youtube/live. Called by live_news_grid.js
    before falling back to a channel's static fallback_video_id."""
    handle = request.GET.get("channel", "")
    if not handle:
        return JsonResponse({"error": "Missing channel parameter"}, status=400)
    result = get_live_video_id(handle)
    return JsonResponse({
        "videoId": result["video_id"],
        "isLive": result["is_live"],
        "channelName": result["channel_name"],
    })
