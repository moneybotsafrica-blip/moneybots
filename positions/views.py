from django.http import JsonResponse

from analysis.models import MarketSignal

from .models import PaperPosition


def positions_list(request):
    open_positions = PaperPosition.objects.filter(status="open")
    closed_positions = PaperPosition.objects.exclude(status="open")[:50]

    results = []
    for position in open_positions:
        latest = MarketSignal.objects.filter(symbol=position.symbol).order_by("-created_at").first()
        current_price = latest.price if latest else position.entry_price
        results.append(position.as_dict(current_price=current_price))

    for position in closed_positions:
        results.append(position.as_dict())

    return JsonResponse({"positions": results})
