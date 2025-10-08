from dotenv import load_dotenv
from typing import Dict, Optional, Tuple, List
import datetime
import json
import logging
import os
import pandas as pd
import requests, time
import sqlite3

load_dotenv()

T212_API_BASE = os.getenv("T212_API_BASE")
T212_API_KEY = os.getenv("T212_API_KEY")
T212_SECRET_KEY = os.getenv("T212_SECRET_KEY")
TELEGRAM_BOT_TOKEN =os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

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
    logger.info("Initializing database...")
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

def get_price_data(
    symbol: str,
    outputsize: str = "compact"
) -> Optional[Dict]:
    """
    Get daily price data using Alpha Vantage FREE API (TIME_SERIES_DAILY).

    Parameters:
    -----------
    symbol : str
        Stock ticker symbol (e.g., 'AAPL', 'IBM')
    outputsize : str
        'compact' (100 data points) or 'full' (20+ years)

    Returns:
    --------
    dict or None
        Dictionary containing price data or None if request fails
    """

    base_url = "https://www.alphavantage.co/query"

    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol,
        "outputsize": outputsize,
        "apikey": ALPHA_VANTAGE_API_KEY
    }

    try:
        logger.info(f"Fetching MACD data for {symbol}...")
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Debug: print raw response
        logger.info(f"API Response keys: {list(data.keys())}")

        # Check for API errors
        if "Error Message" in data:
            logger.info(f"❌ API Error: {data['Error Message']}")
            return None

        if "Note" in data:
            logger.info(f"⚠️  API Rate Limit: {data['Note']}")
            logger.info("   Tip: Free tier allows 5 calls/minute, 500 calls/day")
            return None

        if "Information" in data:
            logger.info(f"ℹ️  API Info: {data['Information']}")
            return None

        return data

    except requests.exceptions.RequestException as e:
        logger.info(f"❌ Request failed: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.info(f"❌ Failed to parse JSON: {e}")
        logger.info(f"   Response text: {response.text[:200]}")
        return None


def calculate_ema(prices: List[float], period: int) -> List[float]:
    """
    Calculate Exponential Moving Average.
    """
    ema = []
    multiplier = 2 / (period + 1)

    # Start with SMA for first value
    sma = sum(prices[:period]) / period
    ema.append(sma)

    # Calculate EMA for remaining values
    for price in prices[period:]:
        ema_value = (price - ema[-1]) * multiplier + ema[-1]
        ema.append(ema_value)

    return ema


def calculate_macd_from_prices(
    prices: List[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9
) -> Tuple[List[float], List[float], List[float]]:
    """
    Calculate MACD, Signal, and Histogram from price data.

    Returns:
    --------
    tuple: (macd_line, signal_line, histogram)
    """

    # Calculate fast and slow EMAs
    fast_ema = calculate_ema(prices, fast_period)
    slow_ema = calculate_ema(prices, slow_period)

    # MACD line = Fast EMA - Slow EMA
    # Align arrays (slow EMA starts later)
    offset = slow_period - fast_period
    macd_line = [fast_ema[i + offset] - slow_ema[i] for i in range(len(slow_ema))]

    # Signal line = EMA of MACD line
    signal_line = calculate_ema(macd_line, signal_period)

    # Histogram = MACD - Signal
    hist_offset = signal_period - 1
    histogram = [macd_line[i + hist_offset] - signal_line[i] for i in range(len(signal_line))]

    return macd_line, signal_line, histogram


def get_latest_macd(
    symbol: str,
) -> Optional[Tuple[float, float, float, str]]:
    """
    Get the most recent MACD values for a symbol (calculated from free price data).

    Returns:
    --------
    tuple or None
        (MACD, Signal, Histogram, Date) or None if request fails
    """

    data = get_price_data(symbol, outputsize="compact")

    if not data:
        logger.info(f"❌ Failed to fetch data for {symbol}")
        return None

    if "Time Series (Daily)" not in data:
        logger.info(f"❌ No price data found for {symbol}")
        logger.info(f"   Available keys: {list(data.keys())}")
        return None

    time_series = data["Time Series (Daily)"]

    # Sort dates and get closing prices
    dates = sorted(time_series.keys(), reverse=True)
    prices = [float(time_series[date]["4. close"]) for date in reversed(dates)]

    # Need at least 35 periods for MACD calculation (26 + 9)
    if len(prices) < 35:
        logger.info(f"❌ Not enough data points for {symbol}")
        return None

    # Calculate MACD
    macd_line, signal_line, histogram = calculate_macd_from_prices(prices)

    # Get most recent values
    latest_date = dates[0]
    macd = macd_line[-1]
    signal = signal_line[-1]
    hist = histogram[-1]

    return (macd, signal, hist, latest_date)


def analyze_macd_signal(symbol):
    """
    Analyze MACD and provide trading signal (using free API).

    Returns:
    --------
    str or None
        Trading signal: 'BULLISH', 'BEARISH', or 'NEUTRAL'
    """

    result = get_latest_macd(symbol)

    if not result:
        return None

    macd, signal, histogram, date = result

    logger.info(f"\n{symbol} - MACD Analysis ({date}):")
    logger.info(f"MACD: {macd:.4f}")
    logger.info(f"Signal: {signal:.4f}")
    logger.info(f"Histogram: {histogram:.4f}")

    # Determine signal
    if macd > signal and histogram > 0:
        signal_type = "BULLISH"
        logger.info(f"Signal: {signal_type} (MACD above signal line)")
    elif macd < signal and histogram < 0:
        signal_type = "BEARISH"
        logger.info(f"Signal: {signal_type} (MACD below signal line)")
    else:
        signal_type = "NEUTRAL"
        logger.info(f"Signal: {signal_type}")

    # Check for crossovers by getting previous value
    data = get_price_data(symbol)
    if data and "Time Series (Daily)" in data:
        time_series = data["Time Series (Daily)"]
        dates = sorted(time_series.keys(), reverse=True)
        prices = [float(time_series[d]["4. close"]) for d in reversed(dates)]

        if len(prices) >= 36:  # Need one extra period for previous values
            macd_line, signal_line, histogram = calculate_macd_from_prices(prices)
            crossover = None

            prev_macd = macd_line[-2]
            prev_signal = signal_line[-2]

            # Bullish crossover
            if prev_macd <= prev_signal and macd > signal:
                logger.info("⚠️  BULLISH CROSSOVER detected!")
                crossover = "BULLISH"

            # Bearish crossover
            elif prev_macd >= prev_signal and macd < signal:
                logger.info("⚠️  BEARISH CROSSOVER detected!")
                crossover = "BEARISH"

    return signal_type, crossover

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
    url = f"{T212_API_BASE}/metadata/instruments"
    resp = requests.get(url, headers=HEADERS, auth=(T212_API_KEY,T212_SECRET_KEY))
    resp.raise_for_status()
    return resp.json()

def fetch_positions():
    """Fetch all current equity positions"""
    url = f"{T212_API_BASE}/portfolio"
    while True:
        try:
            resp = requests.get(url, headers=HEADERS, auth=(T212_API_KEY,T212_SECRET_KEY))
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 429:  # Too Many Requests
                logger.info("Rate limit hit. Retrying after a short delay...")
                time.sleep(1)  # Wait before retrying
            else:
                raise e

def fetch_orders():
    """Fetch the latest market price for a given ticker"""
    url = f"{T212_API_BASE}/orders"
    resp = requests.get(url, headers=HEADERS, auth=(T212_API_KEY,T212_SECRET_KEY))
    resp.raise_for_status()
    return resp.json()

def get_price(ticker: str):
    """Fetch the latest market price for a given ticker"""
    url = f"{T212_API_BASE}/portfolio/{ticker}"
    resp = requests.get(url, headers=HEADERS, auth=(T212_API_KEY,T212_SECRET_KEY))
    resp.raise_for_status()
    return resp.json()["currentPrice"]

def sell(ticker, quantity):
    url = f"{T212_API_BASE}/orders/market"
    payload = {
        "quantity": -quantity,
        "ticker": ticker
    }
    logger.info(f"Selling {quantity} x {ticker}")
    resp = requests.post(url, json=payload, headers=HEADERS, auth=(T212_API_KEY,T212_SECRET_KEY))
    data = resp.json()
    logger.info(data)
    return data

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }

    response = requests.post(url, data=payload)

    if response.status_code == 200:
        logger.info("Message sent successfully!")
    else:
        logger.info("Failed to send message:", response.text)

def get_current_positions(db, all_tickers, default_target_stop_pct = 2):
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

        # TODO: Check MACD - 25 requests per day, not good
        # full_ticker = position_dict["short_name"] if position_dict["currency"] == "USD" else position_dict["short_name"] + ".L"
        # signal_type, crossover = analyze_macd_signal(full_ticker)
        # logger.info(f"Signal type: {signal_type}")
        # if crossover is None:
        #     logger.info(f"No recent crossover.")
        # else:
        #     logger.info(f"Crossover type: {crossover}")

        # Check if stop loss has been reached, then sell at market and send a message (only weekdays)
        if position_dict["stop_loss_price"] >= position_dict["current_price"] and datetime.date.today().weekday() < 5:
            # Attempt to sell - It will only sell if there are no stop losses already set
            # and the error code will be 'SellingEquityNotOwned'
            rc = sell(position_dict['ticker'], position_dict['quantity'])

            if "code" in rc and rc["code"] == "SellingEquityNotOwned":
                logger.info(f"Could not sell {position_dict['ticker']}, probably because there is a stop loss in place")
            else:
                message =  f"Stop loss activated for {position_dict['short_name']} - {position_dict['name']}.\n"
                message += f"Purchased price: {position_dict['average_price']}\n"
                message += f"Current price: {position_dict['current_price']}\n"
                message += f"Max price: {position_dict['max_price']}\n"
                message += f"Stop loss price: {position_dict['stop_loss_price']}\n"
                message += f"P/L: {position_dict['profit_pct']}%\n"
                send_telegram_message(message)

        all_positions.append(position_dict)
        time.sleep(1)  # To avoid hitting rate limits

    return all_positions

def get_pending_orders(all_tickers):
    orders = []
    pending_orders = [o for o in fetch_orders() if o.get("type") in ["LIMIT", "MARKET"]]
    for order in pending_orders:
        order_dict = {}
        ticker_info = next((item for item in all_tickers if item['ticker'] == order['ticker']), None)

        order_dict["name"] = ticker_info["name"]
        order_dict["ticker"] = ticker_info["shortName"]

        if ticker_info["currencyCode"] == "USD":
            order_dict["currency"] = "💵"
        else:
            order_dict["currency"] = "💷"

        if order["type"] == "MARKET":
            order_dict["limit_price"] = order["type"]
        else:
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
