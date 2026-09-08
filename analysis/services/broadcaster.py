from channels.layers import get_channel_layer

from ..consumers import ANALYSIS_GROUP


async def broadcast(payload: dict):
    layer = get_channel_layer()
    if layer is None:
        return
    await layer.group_send(ANALYSIS_GROUP, {"type": "analysis.update", "payload": payload})
