import requests, time
from dotenv import load_dotenv
import os

load_dotenv()

API_BASE = os.getenv("API_BASE")
API_KEY = os.getenv("API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")
BOT_TOKEN =os.getenv("BOT_TOKEN")

HEADERS = {
    "Content-Type": "application/json"
}


def buy(ticker, quantity):
    url = f"{API_BASE}/orders/market"
    payload = {
        "quantity": quantity,
        "ticker": ticker
    }

    print(f"Buying {quantity} x {ticker}")
    resp = requests.post(url, json=payload, headers=HEADERS, auth=(API_KEY,SECRET_KEY))
    data = resp.json()
    print(data)


def sell(ticker, quantity):
    url = f"{API_BASE}/orders/market"
    payload = {
        "quantity": -quantity,
        "ticker": ticker
    }

    print(f"Selling {quantity} x {ticker}")
    resp = requests.post(url, json=payload, headers=HEADERS, auth=(API_KEY,SECRET_KEY))
    data = resp.json()
    print(data)

sell("METC_US_EQ", 1)
