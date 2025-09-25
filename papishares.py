import requests, time
from pprint import pprint
from dotenv import load_dotenv
import os
import sqlite3

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
    "COFFl_EQ": "WT Coffee",
    "CRDO_US_EQ": "Credo",
    "DMYI_US_EQ": "IonQ",
    "GDWNl_EQ": "Goodwin",
    "GIG_US_EQ": "BigBear.ai",
    "GOOGL_US_EQ": "Alphabet",
    "IBM_US_EQ": "IBM",
    "INTC_US_EQ": "Intel",
    "IPOE_US_EQ": "SoFi",
    "LAES_US_EQ": "SEALSQ",
    "LLOYl_EQ": "Lloyds",
    "LPL_US_EQ": "LG Displays",
    "MBX_US_EQ": "MBX Biosciences",
    "MU_US_EQ": "Micron",
    "NET_US_EQ": "Cloudflare",
    "NIO_US_EQ": "NIO",
    "PHNXl_EQ": "Phoenix",
    "QQQ3l_EQ": "NASDAQ-100 3x",
    "QWTMl_EQ": "WT Quantum Computing",
    "RR_US_EQ": "Richtech Robotics",
    "RRl_EQ": "Rolls Royce",
    "SEMIl_EQ": "iShares Semiconductors",
    "SNII_US_EQ": "Rigetti",
    "SPIl_EQ": "Spire Health",
    "SSLNl_EQ": "iShares Silver",
    "STX_US_EQ": "Seagate",
    "VALE_US_EQ": "Vale",
    "WIX_US_EQ": "Wix",
    "WREEl_EQ": "WT Rare Metals",
    "WRENl_EQ": "WT Renewables",
    "XPOA_US_EQ": "D-Wave",
}

NON_STANDARD_STOPS = {
    "DMYI_US_EQ": 8,    # IonQ - volatile
    "QWTMl_EQ": 8,      # WT Quantum Computing - volatile
    "WREEl_EQ": 6,      # WT Rare Metals - volatile
    "WRENl_EQ": 6,      # WT Renewables - volatile
    "XPOA_US_EQ": 8,    # D-Wave - volatile
    "IPOE_US_EQ": 6,    # SoFi - volatile
    "GDWNl_EQ": 6,      # Goodwin - volatile
}

def initialize_database(db):
    print("Initializing database...")
    conn = sqlite3.connect(db)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            ticker TEXT PRIMARY KEY,
            stop_loss REAL,
            last_price REAL
        )
    """)
    conn.commit()
    conn.close()

def get_db(db):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn

def update_stop_loss(ticker, current_price, db, trail_percent):
    conn = get_db(db)
    c = conn.cursor()

    c.execute("SELECT stop_loss FROM positions WHERE ticker=?", (ticker,))
    row = c.fetchone()

    suggested_stop_loss = round(current_price * (1 - trail_percent / 100), 2)

    if row is None:
        stop_loss = suggested_stop_loss
        c.execute("INSERT INTO positions (ticker, stop_loss, last_price) VALUES (?, ?, ?)",
                  (ticker, stop_loss, current_price))
    else:
        stop_loss = max(row["stop_loss"], suggested_stop_loss)
        c.execute("UPDATE positions SET stop_loss=?, last_price=? WHERE ticker=?",
                  (stop_loss, current_price, ticker))

    conn.commit()
    conn.close()
    return stop_loss

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

def get_current_positions(db, default_target_stop_pct = 2):
    all_positions = []
    positions = fetch_positions()
    stop_orders = [o for o in fetch_orders() if o.get("type") in ["STOP", "STOP_LIMIT"]]

    for pos in positions:
        position_dict = {}

        if pos["ticker"] in TICKERS:
            name = TICKERS[pos["ticker"]]
        else:
            name = pos["ticker"]

        if pos["ticker"] in NON_STANDARD_STOPS:
            position_dict["recommended_stop_loss_pct"] = NON_STANDARD_STOPS[pos["ticker"]]
        else:
            position_dict["recommended_stop_loss_pct"] = default_target_stop_pct

        position_dict["ticker"] = pos["ticker"].split("_")[0]
        country = pos["ticker"].split("_")[1]
        if country == "US":
            position_dict["currency"] = "💵"
        else:
            position_dict["currency"] = "💷"
        position_dict["name"] = name
        position_dict["quantity"] = pos["quantity"]
        position_dict["average_price"] = round(pos["averagePrice"], 2)
        position_dict["current_price"] = get_price(pos["ticker"])
        position_dict["profit_pct"] = round(((position_dict["current_price"] - pos["averagePrice"]) / pos["averagePrice"]) * 100, 2)
        position_dict["tolerance"] = 1  # percent

        # Existing stop (if any)
        stop_order = next((o for o in stop_orders if o.get("ticker") == pos["ticker"]), None)
        position_dict["stop_loss_price"] = float(stop_order["stopPrice"]) if stop_order is not None else 0
        position_dict["stop_loss_quantity"] = float(abs(stop_order["quantity"])) if stop_order is not None else 0
        position_dict["recommended_stop_loss"] = update_stop_loss(position_dict["ticker"], position_dict["current_price"], db, position_dict["recommended_stop_loss_pct"])

        # Actual distance from current price
        if position_dict["stop_loss_price"] is not None:
            position_dict["stop_loss_distance_pct"] = round(((position_dict["current_price"] - position_dict["stop_loss_price"]) / position_dict["current_price"]) * 100, 2)
        else:
            position_dict["stop_loss_distance_pct"] = None

        if position_dict["stop_loss_price"] is None \
            or position_dict["quantity"] > position_dict["stop_loss_quantity"] \
            or (position_dict["stop_loss_distance_pct"] - position_dict["recommended_stop_loss_pct"]) >= position_dict["tolerance"] \
            or position_dict["stop_loss_distance_pct"] < 0:
            position_dict["needs_adjusting"] = True
        else:
            position_dict["needs_adjusting"] = False

        time.sleep(1)  # To avoid hitting rate limits
        all_positions.append(position_dict)

    return all_positions


def get_pending_orders():
    orders = []
    pending_orders = [o for o in fetch_orders() if o.get("type") in ["LIMIT", "MARKET"]]
    for order in pending_orders:
        order_dict = {}

        if order["ticker"] in TICKERS:
            name = TICKERS[order["ticker"]]
        else:
            name = order["ticker"]

        order_dict["name"] = name
        order_dict["ticker"] = order["ticker"].split("_")[0]
        country = order["ticker"].split("_")[1]
        if country == "US":
            order_dict["currency"] = "💵"
        else:
            order_dict["currency"] = "💷"
        order_dict["limit_proce"] = round(order["limitPrice"], 2)
        order_dict["quantity"] = order["quantity"]

    time.sleep(1)  # To avoid hitting rate limits
    orders.append(order_dict)
    return orders
