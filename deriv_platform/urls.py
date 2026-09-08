from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

def google_login_redirect(request):
    """Redirect to the correct allauth Google login URL."""
    process = request.GET.get('process', 'login')
    return redirect(f'/accounts/social/google/login/?process={process}')

# Import stocks views directly as fallback
try:
    from stocks import views as stocks_views
    STOCKS_AVAILABLE = True
except ImportError:
    STOCKS_AVAILABLE = False

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("accounts/google/login/", google_login_redirect, name="google_login"),
    path("", include("dashboard.urls")),
    path("news/", include("news.urls")),
    path("api/", include("analysis.urls")),
    path("analysis/", include("analysis.urls")),
    path("api/", include("positions.urls")),
    path("api/ai/", include("assistant.urls")),
    path("signals/", include("analysis.urls")),  # Add direct /signals/ route for live signals page
    path("stocks/", include("stocks.urls")),  # Add stocks page with TradingView integration
    # WebSocket routes are handled in ASGI, not here
]

# Fallback: add stocks routes directly if include fails
if STOCKS_AVAILABLE:
    urlpatterns.append(path("stocks/", stocks_views.stocks_page, name="stocks_page"))
    urlpatterns.append(path("stocks/api/analyze-gaps/", stocks_views.analyze_gaps, name="analyze_gaps"))
    urlpatterns.append(path("stocks/api/ticker/", stocks_views.get_stock_ticker, name="get_stock_ticker"))
