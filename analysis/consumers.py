import json
import logging
from datetime import datetime

from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import async_to_sync
from django.core.cache import cache

ANALYSIS_GROUP = "analysis_updates"
CHART_DATA_GROUP = "chart_data"
logger = logging.getLogger(__name__)


class AnalysisConsumer(AsyncWebsocketConsumer):
    """Browser connects here (ws/analysis/) to receive live updates for the
    analysis window: every market's latest signal + open paper positions.
    The run_analysis / run_position_manager management commands push
    messages into ANALYSIS_GROUP; this consumer just relays them.
    
    Also receives chart data from browser to make it available to analysis system."""

    async def connect(self):
        await self.channel_layer.group_add(ANALYSIS_GROUP, self.channel_name)
        await self.channel_layer.group_add(CHART_DATA_GROUP, self.channel_name)
        await self.accept()
        print(f"WebSocket connected: {self.channel_name}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(ANALYSIS_GROUP, self.channel_name)
        await self.channel_layer.group_discard(CHART_DATA_GROUP, self.channel_name)
        print(f"WebSocket disconnected: {self.channel_name}")

    async def analysis_update(self, event):
        await self.send(text_data=json.dumps(event["payload"]))
        print(f"Broadcasting to {self.channel_name}: {event['payload'].get('type', 'unknown')}")

    async def receive(self, text_data):
        """Handle incoming WebSocket messages from browser, including chart data."""
        try:
            data = json.loads(text_data)
            print(f"Received message from {self.channel_name}: {data}")
            
            # Handle chart data updates
            if data.get('type') == 'chart_data':
                await self.handle_chart_data(data)
            # Handle symbol changes
            elif data.get('type') == 'symbol_change':
                await self.handle_symbol_change(data)
            # Handle other message types
            else:
                logger.info(f"Received unknown message type: {data.get('type')}")
                
        except json.JSONDecodeError:
            print(f"Received invalid JSON from {self.channel_name}")
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")

    async def handle_chart_data(self, data):
        """Handle chart data from browser and make it available to analysis system."""
        try:
            symbol = data.get('symbol')
            chart_data = data.get('data', {})
            
            if not symbol:
                logger.warning("Chart data received without symbol")
                return
            
            # Store chart data in cache for analysis system to use
            cache_key = f"chart_data_{symbol}"
            cache.set(cache_key, {
                'symbol': symbol,
                'price': chart_data.get('price'),
                'candle': chart_data.get('candle'),
                'timestamp': datetime.now().isoformat(),
                'historical': chart_data.get('historical', [])
            }, timeout=60)  # Cache for 60 seconds
            
            logger.info(f"Updated chart data cache for {symbol}: price={chart_data.get('price')}")
            
            # Broadcast to other consumers if needed
            await self.channel_layer.group_send(
                CHART_DATA_GROUP,
                {
                    'type': 'chart_data_update',
                    'symbol': symbol,
                    'data': chart_data
                }
            )
            
        except Exception as e:
            logger.error(f"Error handling chart data: {e}")

    async def handle_symbol_change(self, data):
        """Handle symbol change from chart."""
        try:
            symbol = data.get('symbol')
            if symbol:
                # Update current symbol in cache
                cache.set('current_chart_symbol', symbol, timeout=300)
                logger.info(f"Current chart symbol updated to: {symbol}")
                
                # Notify analysis system about symbol change
                await self.channel_layer.group_send(
                    ANALYSIS_GROUP,
                    {
                        'type': 'symbol_change',
                        'symbol': symbol
                    }
                )
        except Exception as e:
            logger.error(f"Error handling symbol change: {e}")

    async def chart_data_update(self, event):
        """Handle chart data update broadcasts within the group."""
        # This method is called when the group receives a chart_data_update message
        logger.debug(f"Chart data update broadcast: {event.get('symbol')}")

    async def symbol_change(self, event):
        """Handle symbol change broadcasts within the group."""
        logger.debug(f"Symbol change broadcast: {event.get('symbol')}")
