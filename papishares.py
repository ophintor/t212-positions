import requests, time
from dotenv import load_dotenv
import os
import sqlite3
import json
import logging

load_dotenv()

API_BASE = os.getenv("API_BASE")
API_KEY = os.getenv("API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")
BOT_TOKEN =os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TELEGRAM_URL = os.getenv("TELEGRAM_URL")

HEADERS = {
    "Content-Type": "application/json"
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

current_prices = {}

def initialize_database(db):
    print("Initializing database...")
    conn = sqlite3.connect(db)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            ticker TEXT PRIMARY KEY,
            max_price REAL,
            stop_loss REAL
        )
    """)
    conn.commit()
    conn.close()

def get_db(db):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn

def update_max_price(ticker, price, db):
    conn = get_db(db)
    c = conn.cursor()

    c.execute("SELECT stop_loss FROM positions WHERE ticker=?", (ticker,))
    row = c.fetchone()

    if row is None:
        c.execute("INSERT INTO positions (ticker, max_price) VALUES (?, ?)",
                  (ticker, price))
    else:
        c.execute("UPDATE positions SET max_price=? WHERE ticker=?",
                  (price, ticker))

    conn.commit()
    conn.close()

def update_stop_loss(ticker, price, db, trail_percent):
    conn = get_db(db)
    c = conn.cursor()

    c.execute("SELECT stop_loss FROM positions WHERE ticker=?", (ticker,))
    row = c.fetchone()

    suggested_stop_loss = round(price * (1 - trail_percent / 100), 2)

    if row is None:
        c.execute("INSERT INTO positions (ticker, stop_loss) VALUES (?, ?)",
                  (ticker, suggested_stop_loss))
    else:
        c.execute("UPDATE positions SET stop_loss=? WHERE ticker=?",
                  (suggested_stop_loss, ticker))

    conn.commit()
    conn.close()

    return suggested_stop_loss

def get_stop_loss(ticker, db):
    conn = get_db(db)
    c = conn.cursor()

    c.execute("SELECT stop_loss FROM positions WHERE ticker=?", (ticker,))
    row = c.fetchone()

    conn.close()

    if row is None:
        return None
    else:
        return row[0]

def get_max_price(ticker, db):
    conn = get_db(db)
    c = conn.cursor()

    c.execute("SELECT max_price FROM positions WHERE ticker=?", (ticker,))
    row = c.fetchone()

    conn.close()

    if row is None:
        return None
    else:
        return row[0]

def fetch_all_tickers_info():
    url = f"{API_BASE}/metadata/instruments"
    resp = requests.get(url, headers=HEADERS, auth=(API_KEY,SECRET_KEY))
    resp.raise_for_status()
    return resp.json()

def fetch_positions():
    """Fetch all current equity positions"""
    url = f"{API_BASE}/portfolio"
    while True:
        try:
            resp = requests.get(url, headers=HEADERS, auth=(API_KEY,SECRET_KEY))
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
    resp = requests.get(url, headers=HEADERS, auth=(API_KEY,SECRET_KEY))
    resp.raise_for_status()
    return resp.json()

def get_price(ticker: str):
    """Fetch the latest market price for a given ticker"""
    url = f"{API_BASE}/portfolio/{ticker}"
    resp = requests.get(url, headers=HEADERS, auth=(API_KEY,SECRET_KEY))
    resp.raise_for_status()
    return resp.json()["currentPrice"]

def sell(ticker, quantity):
    url = f"{API_BASE}/orders/market"
    payload = {
        "quantity": -quantity,
        "ticker": ticker
    }
    logger.info(f"Selling {quantity} x {ticker}")
    resp = requests.post(url, json=payload, headers=HEADERS, auth=(API_KEY,SECRET_KEY))
    data = resp.json()
    logger.info(data)

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

def get_current_positions(db, all_tickers, default_target_stop_pct = 4):
    all_positions = []
    positions = fetch_positions()

    for pos in positions:
        position_dict = {}

        ticker_info = next((item for item in all_tickers if item['ticker'] == pos['ticker']), None)

        # Basic data update from current positions
        position_dict["ticker"] = ticker_info['ticker']
        position_dict["short_name"] = ticker_info['shortName']
        position_dict["name"] = ticker_info['name']

        if ticker_info["currencyCode"] == "USD":
            position_dict["currency"] = "💵"
        else:
            position_dict["currency"] = "💷"

        position_dict["quantity"] = pos["quantity"]
        position_dict["average_price"] = round(pos["averagePrice"], 2)
        position_dict["current_price"] = get_price(ticker_info["ticker"])
        position_dict["profit_pct"] = round(((position_dict["current_price"] - pos["averagePrice"]) / pos["averagePrice"]) * 100, 2)

        # Get the max price and update the DB if needed
        max_price = get_max_price(position_dict["ticker"], db)

        if max_price is None or max_price < position_dict["current_price"]:
            update_max_price(position_dict["ticker"], position_dict["current_price"], db)
            position_dict["max_price"] = position_dict["current_price"]
        else:
            position_dict["max_price"] = max_price


        # Get the stop loss and update the DB if needed
        position_dict["stop_loss_price"] = update_stop_loss(
            position_dict["ticker"],
            max(position_dict["average_price"],position_dict["current_price"]),
            db,
            default_target_stop_pct
        )

        # Check if stop loss has been reached, then sell at market and send a message
        if position_dict["stop_loss_price"] >= position_dict["current_price"]:
            message =  f"Stop loss activated for {position_dict['short_name']} - {position_dict['name']}.\n"
            message += f"Purchased price: {position_dict['average_price']}\n"
            message += f"Current price: {position_dict['current_price']}\n"
            message += f"Max price: {position_dict['max_price']}\n"
            message += f"Stop loss price: {position_dict['stop_loss_price']}\n"
            message += f"P/L: {position_dict['profit_pct']}%\n"
            send_telegram_message(message)
            # sell(position_dict['ticker'], position_dict['quantity'])
        all_positions.append(position_dict)

        time.sleep(1)  # To avoid hitting rate limits

    return all_positions

def get_pending_orders(all_tickers):
    orders = []
    pending_orders = [o for o in fetch_orders() if o.get("type") in ["LIMIT", "MARKET"]]
    for order in pending_orders:
        order_dict = {}

        if order["ticker"] in all_tickers:
            name = all_tickers[order["ticker"]]
        else:
            name = order["ticker"]

        order_dict["name"] = name
        order_dict["ticker"] = order["ticker"].split("_")[0]
        country = order["ticker"].split("_")[1]
        if country == "US":
            order_dict["currency"] = "💵"
        else:
            order_dict["currency"] = "💷"
        order_dict["limit_price"] = round(order["limitPrice"], 2)
        order_dict["quantity"] = order["quantity"]
        orders.append(order_dict)

        time.sleep(1)  # To avoid hitting rate limits

    return orders

def get_last_entries():
    json_url = 'http://stuff.dabeed.net/suggested_entries.json'

    try:
        response = requests.get(json_url, timeout=10)
        response.raise_for_status()

        # Parse JSON
        data = response.json()
        return data
    except requests.exceptions.RequestException as e:
        return f"Error fetching data from URL: {str(e)}"
    except json.JSONDecodeError as e:
        return f"Error parsing JSON: {str(e)}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"
