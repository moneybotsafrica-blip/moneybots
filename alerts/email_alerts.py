"""
Email alerts — ported from the uploaded email_alerts.py.

Only change from the original: EMAIL_CONFIG and the cooldown window now
come from Django settings (which load from .env) instead of being
hardcoded in this file. The Gmail app password Jj had in the original
should be rotated since it was committed in plaintext — put the new one
in .env, never in source.
"""
import json
import logging
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from django.conf import settings

VAR_DIR = settings.BASE_DIR / "var"
VAR_DIR.mkdir(exist_ok=True)
SIGNAL_CACHE_FILE = VAR_DIR / "last_signal.json"


def load_last_signal():
    try:
        if SIGNAL_CACHE_FILE.exists():
            with open(SIGNAL_CACHE_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Error loading last signal: {e}")
    return None


def save_last_signal(signal_data):
    try:
        signal_data["timestamp"] = datetime.now().timestamp()
        with open(SIGNAL_CACHE_FILE, "w") as f:
            json.dump(signal_data, f)
    except Exception as e:
        logging.error(f"Error saving signal: {e}")


def should_send_alert(signal, price_data):
    last_signal = load_last_signal()
    if not last_signal:
        return True

    current_time = datetime.now().timestamp()
    time_diff_minutes = (current_time - last_signal.get("timestamp", 0)) / 60

    if signal["direction"] != last_signal.get("signal", {}).get("direction"):
        logging.info("Signal direction changed - sending alert")
        return True

    if time_diff_minutes < settings.ALERT_COOLDOWN_MINUTES:
        last_entry = last_signal.get("price_data", {}).get("entry", 0)
        price_change_percent = abs((price_data["entry"] - last_entry) / last_entry) * 100 if last_entry else 0

        if price_change_percent > 2:
            logging.info(f"Significant price change ({price_change_percent:.1f}%) - sending alert")
            return True

        if signal.get("pattern") != last_signal.get("signal", {}).get("pattern"):
            logging.info("Pattern changed - sending alert")
            return True

        logging.info(
            f"Skipping alert - cooldown period ({time_diff_minutes:.0f} min < {settings.ALERT_COOLDOWN_MINUTES} min)"
        )
        return False

    logging.info("Cooldown period expired - sending new alert")
    return True


def format_trade_alert(signal, price_data, advice):
    market_name = price_data.get("market_name", "Unknown Market")
    color = "#28a745" if signal["direction"] == "Buy" else "#dc3545"
    rr = signal.get("risk_reward")
    rr_line = f"1:{rr:.1f}" if rr else "n/a"

    return f"""
    <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: {color}; padding: 20px; border-radius: 5px;">
                <h2 style="color: white; margin: 0; text-align: center;">
                    {signal['direction']} Signal Alert (paper trade only)
                </h2>
            </div>

            <div style="margin: 20px 0; background-color: #f8f9fa; padding: 15px; border-radius: 5px;">
                <h3 style="color: #333; margin-top: 0;">Market Information:</h3>
                <ul style="list-style-type: none; padding: 0;">
                    <li><strong>Market:</strong> {market_name}</li>
                    <li><strong>Date/Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC</li>
                </ul>
            </div>

            <div style="margin: 20px 0; background-color: #f8f9fa; padding: 15px; border-radius: 5px;">
                <h3 style="color: #333; margin-top: 0;">Signal Analysis:</h3>
                <ul style="list-style-type: none; padding: 0;">
                    <li><strong>Entry Type:</strong> {signal.get('entry_type', 'n/a')}</li>
                    <li><strong>Signal Strength:</strong> {signal.get('signal_strength', 0):.2f}</li>
                    <li><strong>Setup Quality:</strong> {signal.get('setup_quality', 0):.1f}%</li>
                </ul>
            </div>

            <div style="margin: 20px 0; background-color: #f8f9fa; padding: 15px; border-radius: 5px;">
                <h3 style="color: #333; margin-top: 0;">Trade Levels:</h3>
                <ul style="list-style-type: none; padding: 0;">
                    <li><strong>Entry Price:</strong> {price_data['entry']:.5f}</li>
                    <li><strong>Stop Loss:</strong> {price_data['stop_loss']:.5f}</li>
                    <li><strong>Take Profit:</strong> {price_data['take_profit']:.5f}</li>
                    <li><strong>Risk/Reward Ratio:</strong> {rr_line}</li>
                </ul>
            </div>

            <div style="margin: 20px 0; background-color: #f8f9fa; padding: 15px; border-radius: 5px;">
                <h3 style="color: #333; margin-top: 0;">Trading Advisory:</h3>
                <p style="margin: 0;">{advice}</p>
            </div>

            <div style="margin-top: 30px; padding: 15px; border-top: 1px solid #ddd;">
                <p style="color: #666; font-size: 12px; margin: 0;">
                    ⚠️ Automated analysis only — no order was placed.<br>
                    🔍 Always conduct your own analysis and risk management.<br>
                    ⏰ Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC
                </p>
            </div>
        </body>
    </html>
    """


def send_trade_alert(signal, price_data, advice):
    cfg = settings.EMAIL_CONFIG
    if not cfg["HOST_USER"] or not cfg["HOST_PASSWORD"] or not cfg["CONTACT_EMAIL"]:
        logging.info("Email alert skipped: EMAIL_HOST_USER/PASSWORD/ALERT_CONTACT_EMAIL not set in .env")
        return False

    try:
        if not should_send_alert(signal, price_data):
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[Paper Signal] {signal['direction']} — {price_data.get('market_name', signal['symbol'])}"
        msg["From"] = cfg["HOST_USER"]
        msg["To"] = cfg["CONTACT_EMAIL"]
        msg.attach(MIMEText(format_trade_alert(signal, price_data, advice), "html"))

        server = smtplib.SMTP(cfg["HOST"], cfg["PORT"])
        server.starttls()
        server.login(cfg["HOST_USER"], cfg["HOST_PASSWORD"])
        server.send_message(msg)
        server.quit()

        save_last_signal({"signal": signal, "price_data": price_data, "timestamp": datetime.now().timestamp()})
        logging.info(f"Trade alert email sent for {signal['direction']} {signal['symbol']}")
        return True

    except Exception as e:
        logging.error(f"Failed to send trade alert email: {e}")
        return False
