from dotenv import load_dotenv
import os
import requests

load_dotenv()

TELEGRAM_BOT_TOKEN =os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }

    response = requests.post(url, data=payload, verify=False)

    if response.status_code == 200:
        print("Message sent successfully!")
    else:
        print("Failed to send message:", response.text)

send_telegram_message("Hello from the bot!")
