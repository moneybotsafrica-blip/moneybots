"""
Test script to verify server-side connection with same configuration as Django
"""
import asyncio
import websockets
import json
import os
import sys

# Change to the project directory and set up Django
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'deriv_platform.settings')

async def test_binaryws_endpoint():
    """Test the binaryws endpoint directly"""
    ws_url = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
    symbol = "R_100"
    
    print(f"Testing binaryws endpoint:")
    print(f"  WS URL: {ws_url}")
    print(f"  Symbol: {symbol}")
    print()
    
    try:
        async with websockets.connect(ws_url) as ws:
            print("Connected to WebSocket")
            
            # Test candle request
            request = {
                'ticks_history': symbol,
                'style': 'candles',
                'granularity': 60,
                'count': 5,
                'end': 'latest'
            }
            
            print(f"Sending request: {request}")
            await ws.send(json.dumps(request))
            response = await ws.recv()
            data = json.loads(response)
            
            print(f"Response: {json.dumps(data, indent=2)}")
            
            if 'error' in data:
                print(f"[FAIL] {symbol}: {data['error'].get('message', 'Unknown error')}")
            elif 'candles' in data:
                print(f"[OK] {symbol}: {len(data['candles'])} candles received")
                for candle in data['candles']:
                    print(f"  {candle['epoch']}: O={candle['open']} H={candle['high']} L={candle['low']} C={candle['close']}")
            else:
                print(f"[FAIL] {symbol}: Unexpected response")
                    
    except Exception as e:
        print(f"Connection failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_binaryws_endpoint())
