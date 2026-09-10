from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

def google_login_redirect(request):
    """Redirect to the correct allauth Google login URL."""
    process = request.GET.get('process', 'login')
    return redirect(f'/accounts/social/google/login/?process={process}')

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
