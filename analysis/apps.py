import asyncio
import threading
import os
import sys
from django.apps import AppConfig


class AnalysisConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "analysis"

    def ready(self):
        """Start the analysis loop when Django app is ready."""
        print("[Analysis] ready() method called")
        
        # Prevent multiple startups (this method can be called multiple times)
        if os.environ.get("ANALYSIS_LOOP_RUNNING"):
            print("[Analysis] Loop already running, skipping startup")
            return
        
        # Only run in the main process, not during migrations/management commands
        skip_commands = ['migrate', 'makemigrations', 'collectstatic', 'createsuperuser', 'shell', 'test']
        if any(cmd in sys.argv for cmd in skip_commands):
            print(f"[Analysis] Skipping startup for command: {' '.join(sys.argv)}")
            return
            
        # Set environment variable to prevent duplicate startups
        os.environ["ANALYSIS_LOOP_RUNNING"] = "1"
        
        print("[Analysis] Initializing analysis startup...")
        
        # Start the analysis loop in a background thread
        try:
            print("[Analysis] Attempting to import analysis modules...")
            from analysis.management.commands.run_analysis import analysis_loop, feed
            from django.conf import settings
            
            print("[Analysis] Imported analysis modules successfully")
            
            def run_analysis_async():
                try:
                    print("[Analysis] Starting event loop...")
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    print("[Analysis] Starting Deriv feed connection...")
                    # Start feed and analysis loop
                    feed_task = loop.create_task(feed.run_forever())
                    loop.run_until_complete(asyncio.sleep(10))  # Give feed time to initialize
                    
                    interval = settings.ANALYSIS_INTERVAL_SECONDS
                    print(f"[Analysis] Starting analysis loop with {interval}s interval...")
                    loop_task = loop.create_task(analysis_loop(interval))
                    loop.run_until_complete(asyncio.gather(feed_task, loop_task))
                except Exception as e:
                    print(f"[Analysis] Error in analysis loop: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Start in daemon thread so it doesn't block server shutdown
            print("[Analysis] Creating background thread...")
            analysis_thread = threading.Thread(target=run_analysis_async, daemon=True, name="AnalysisLoop")
            analysis_thread.start()
            print("[OK] Analysis loop started in background thread")
        except Exception as e:
            print(f"[Analysis] Failed to start analysis loop: {e}")
            import traceback
            traceback.print_exc()
