import requests, time
from pprint import pprint
from dotenv import load_dotenv
import os

load_dotenv()

API_BASE = os.getenv("API_BASE")
API_KEY = os.getenv("API_KEY")
BOT_TOKEN =os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TELEGRAM_URL = os.getenv("TELEGRAM_URL")

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": API_KEY
}

current_prices = {}

TICKERS = {
    "AMD_US_EQ": "AMD",
    "APP_US_EQ": "AppLovin",
    "AVl_EQ": "Aviva",
    "CAPA_US_EQ": "Quantum-Si",
    "CRDO_US_EQ": "Credo",
    "DMYI_US_EQ": "IonQ",
    "GOOGL_US_EQ": "Alphabet",
    "INTC_US_EQ": "Intel",
    "LLOYl_EQ": "Lloyds",
    "MU_US_EQ": "Micron",
    "NET_US_EQ": "Cloudflare",
    "PHNXl_EQ": "Phoenix",
    "QQQ3l_EQ": "NASDAQ-100 3x",
    "QWTMl_EQ": "WT Quantum Computing",
    "RRl_EQ": "Rolls Royce",
    "SEMIl_EQ": "iShares Semiconductors",
    "SNII_US_EQ": "Rigetti",
    "SPIl_EQ": "Spire Health",
    "STX_US_EQ": "Seagate",
    "VALE_US_EQ": "Vale",
    "WIX_US_EQ": "Wix",
    "WREEl_EQ": "WT Rare Metals",
    "XPOA_US_EQ": "D-Wave",
    "XXII_US_EQ": "22nd Century",
}

def fetch_positions():
    """Fetch all current equity positions"""
    url = f"{API_BASE}/portfolio"
    while True:
        try:
            resp = requests.get(url, headers=HEADERS)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 429:  # Too Many Requests
                print("Rate limit hit. Retrying after a short delay...")
                time.sleep(1)  # Wait before retrying
            else:
                raise e

def fetch_orders():
    """Fetch the latest market price for a given ticker"""
    url = f"{API_BASE}/orders"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()

def get_price(ticker: str):
    """Fetch the latest market price for a given ticker"""
    url = f"{API_BASE}/portfolio/{ticker}"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()["currentPrice"]

def update_stop_order(ticker: str, quantity: float, stop_price: float):
    """Place a stop order at the given stop price"""
    url = f"{API_BASE}/orders/stop"
    payload = {
        "ticker": ticker,
        "quantity": quantity,
        "stopPrice": stop_price,
        "timeValidity": "DAY"
    }
    print(url, payload, HEADERS)
    resp = requests.post(url, headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }

    response = requests.post(url, data=payload)

    if response.status_code == 200:
        print("Message sent successfully!")
    else:
        print("Failed to send message:", response.text)

def report_price_moves():
    positions = fetch_positions()
    for pos in positions:
        if pos["ticker"] in TICKERS:
            ticker = TICKERS[pos["ticker"]]
        else:
            ticker = pos["ticker"]

        if pos["ticker"] in current_prices:
            old_price = current_prices[pos["ticker"]]
        else:
            old_price = None
        current_prices[pos["ticker"]] = get_price(pos["ticker"])
        if old_price is not None and current_prices[pos["ticker"]] != old_price:
            percentage_change = ((current_prices[pos["ticker"]] - old_price) / old_price) * 100
            if abs(percentage_change) >= 0.5:
                padding = " " * (15 - len(ticker))
                message = f"Price change for {ticker}: {padding} {old_price} -> {current_prices[pos['ticker']]}\t ({percentage_change:.2f}%)"
                print(message)
                send_telegram_message(f"<code>{message}</code>")

        time.sleep(1)  # To avoid hitting rate limits

def get_stop_losses(exceptions=[], default_target_stop_pct = 3):
    all_stop_losses = []
    positions = fetch_positions()
    stop_orders = [o for o in fetch_orders() if o.get("type") in ["STOP", "STOP_LIMIT"]]

    for pos in positions:
        ticker_position = {}

        if pos["ticker"] in TICKERS:
            name = TICKERS[pos["ticker"]]
        else:
            name = pos["ticker"]

        ticker_position["ticker"] = pos["ticker"].split("_")[0]
        country = pos["ticker"].split("_")[1]
        if country == "US":
            ticker_position["currency"] = "💵"
        else:
            ticker_position["currency"] = "💷"
        ticker_position["name"] = name
        ticker_position["quantity"] = pos["quantity"]
        ticker_position["average_price"] = pos["averagePrice"]
        ticker_position["current_price"] = get_price(pos["ticker"])
        ticker_position["profit_pct"] = round(((ticker_position["current_price"] - pos["averagePrice"]) / pos["averagePrice"]) * 100, 2)
        ticker_position["tolerance"] = 1  # percent
        # ticker_position["stop_distance_pct"] = default_target_stop_pct + int(ticker_position["profit_pct"] / 10)
        ticker_position["recommended_stop_loss"] = round(ticker_position["current_price"] * (1 - default_target_stop_pct / 100), 2)


        # Existing stop (if any)
        # TODO check qty matches position
        stop_order = next((o for o in stop_orders if o.get("ticker") == pos["ticker"]), None)
        ticker_position["stop_loss_price"] = float(stop_order["stopPrice"]) if stop_order is not None else None
        ticker_position["stop_quantity"] = float(stop_order["quantity"]) if stop_order is not None else None

        # Actual distance from current price
        if ticker_position["stop_loss_price"] is not None:
            ticker_position["stop_loss_distance_pct"] = round(((ticker_position["current_price"] - ticker_position["stop_loss_price"]) / ticker_position["current_price"]) * 100, 2)
        else:
            ticker_position["stop_loss_distance_pct"] = None

        if ticker_position["stop_loss_price"] is None or (ticker_position["stop_loss_distance_pct"] - default_target_stop_pct) >= ticker_position["tolerance"]:
            ticker_position["needs_adjusting"] = True
        else:
            ticker_position["needs_adjusting"] = False

        time.sleep(1)  # To avoid hitting rate limits
        all_stop_losses.append(ticker_position)

    return all_stop_losses
