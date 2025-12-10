from dotenv import load_dotenv
from typing import Dict, Optional, Tuple
from datetime import date, datetime, timedelta
import math
import json
import logging
import os
import pandas as pd
import requests, time
import sqlite3
import yfinance as yf
from tabulate import tabulate

load_dotenv()

T212_API_BASE = os.getenv("T212_API_BASE")
T212_API_KEY = os.getenv("T212_API_KEY")
T212_SECRET_KEY = os.getenv("T212_SECRET_KEY")
TELEGRAM_BOT_TOKEN =os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

RISK_PERCENTAGE = 0.7 # Percentage of account to risk on all positions
TOTAL_RISK_PERCENTAGE = 7.0 # Total percentage of account to risk across all positions

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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS macd_notifications (
            symbol TEXT PRIMARY KEY,
            last_crossover_type TEXT,
            last_crossover_time TIMESTAMP,
            last_notified_time TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS flags (
            flag TEXT PRIMARY KEY,
            status BOOLEAN
        )
    """)
    conn.commit()
    conn.close()

def get_db(db):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn

def get_sma(symbol, days=17):
    """
    Calculate the Simple Moving Average for a given stock symbol.
    Fetches data from Yahoo Finance.

    Parameters:
    symbol (str): Stock ticker symbol (e.g., 'AAPL', 'MSFT', 'TSLA')
    days (int): Number of days for the SMA calculation (default: 17)

    Returns:
    dict: Dictionary containing the SMA value, current price, and date
          Returns None if there's an error or insufficient data
    """
    try:
        # Create ticker object
        ticker = yf.Ticker(symbol)

        # Get enough historical data (fetch 2x the days to account for weekends/holidays)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days * 2)

        # Fetch historical data
        data = ticker.history(start=start_date, end=end_date)

        if len(data) < days:
            logger.info(f"Insufficient data for {symbol}. Need {days} days, got {len(data)}")
            return None

        # Get closing prices
        prices = data['Close'].tolist()

        # Calculate SMA
        last_n = prices[-days:]
        sma_value = sum(last_n) / days

        return round(sma_value, 2)

    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None


def calculate_macd(
    df: pd.DataFrame,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9
) -> pd.DataFrame:
    """
    Calculate MACD indicators from price data.

    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with 'Close' price column
    fast_period : int
        Fast EMA period (default: 12)
    slow_period : int
        Slow EMA period (default: 26)
    signal_period : int
        Signal line period (default: 9)

    Returns:
    --------
    pd.DataFrame
        Original DataFrame with MACD, Signal, and Histogram columns added
    """

    # Calculate EMAs
    df['EMA_fast'] = df['Close'].ewm(span=fast_period, adjust=False).mean()
    df['EMA_slow'] = df['Close'].ewm(span=slow_period, adjust=False).mean()

    # Calculate MACD line
    df['MACD'] = df['EMA_fast'] - df['EMA_slow']

    # Calculate Signal line
    df['Signal'] = df['MACD'].ewm(span=signal_period, adjust=False).mean()

    # Calculate Histogram
    df['Histogram'] = df['MACD'] - df['Signal']

    return df


def get_macd_data(
    symbol: str,
    period: str = "3mo",
    interval: str = "1d"
) -> Optional[pd.DataFrame]:
    """
    Get price data and calculate MACD using yfinance.

    Parameters:
    -----------
    symbol : str
        Ticker symbol (e.g., 'AAPL', 'SGLN.L')
    period : str
        Data period: '1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max'
    interval : str
        Data interval: '1m', '2m', '5m', '15m', '30m', '60m', '90m', '1d', '5d', '1wk', '1mo', '3mo'

    Returns:
    --------
    pd.DataFrame or None
        DataFrame with price and MACD data
    """

    try:
        logger.info(f"Fetching data for {symbol}...")
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)

        if df.empty:
            logger.info(f"❌ No data available for {symbol}")
            return None

        # Calculate MACD
        df = calculate_macd(df)

        return df

    except Exception as e:
        logger.info(f"❌ Error fetching data for {symbol}: {e}")
        return None


def get_latest_macd(symbol: str) -> Optional[Tuple[float, float, float, str]]:
    """
    Get the most recent MACD values for a symbol.

    Returns:
    --------
    tuple or None
        (MACD, Signal, Histogram, Date) or None if request fails
    """

    df = get_macd_data(symbol)

    if df is None or df.empty:
        return None

    # Get the most recent values
    latest = df.iloc[-1]
    latest_date = df.index[-1].strftime('%Y-%m-%d')

    macd = latest['MACD']
    signal = latest['Signal']
    histogram = latest['Histogram']

    return (macd, signal, histogram, latest_date)


def analyze_macd_signal(symbol: str, show_chart: bool = False) -> Optional[str]:
    """
    Analyze MACD and provide trading signal.

    Parameters:
    -----------
    symbol : str
        Ticker symbol
    show_chart : bool
        If True, display recent MACD history

    Returns:
    --------
    str or None
        Trading signal: 'BULLISH', 'BEARISH', or 'NEUTRAL'
    """

    df = get_macd_data(symbol)

    if df is None or df.empty:
        return None

    # Get latest values
    latest = df.iloc[-1]
    macd = latest['MACD']
    signal = latest['Signal']
    histogram = latest['Histogram']
    date = df.index[-1].strftime('%Y-%m-%d %H:%M:%S')

    logger.info(f"{'='*60}")
    logger.info(f"{symbol} - MACD Analysis")
    logger.info(f"{'='*60}")
    logger.info(f"Date: {date}")
    logger.info(f"Current Price: {latest['Close']:.2f}")
    logger.info(f"MACD: {macd:.4f}")
    logger.info(f"Signal: {signal:.4f}")
    logger.info(f"Histogram: {histogram:.4f}")

    # Determine signal
    if macd > signal and histogram > 0:
        signal_type = "BULLISH"
        logger.info(f"📈 Signal: {signal_type} (MACD above signal line)")
    elif macd < signal and histogram < 0:
        signal_type = "BEARISH"
        logger.info(f"📉 Signal: {signal_type} (MACD below signal line)")
    else:
        signal_type = "NEUTRAL"
        logger.info(f"➡️  Signal: {signal_type}")

    # Check for crossovers
    crossover = None
    if len(df) >= 2:
        prev = df.iloc[-2]
        prev_macd = prev['MACD']
        prev_signal = prev['Signal']

        # Bullish crossover
        if prev_macd <= prev_signal and macd > signal:
            crossover = "BULLISH"
            logger.info("🚀 BULLISH CROSSOVER detected! (MACD crossed above Signal)")

        # Bearish crossover
        elif prev_macd >= prev_signal and macd < signal:
            crossover = "BEARISH"
            logger.info("⚠️  BEARISH CROSSOVER detected! (MACD crossed below Signal)")

    # Show recent history if requested
    if show_chart:
        logger.info(f"📊 Recent MACD History (Last 10 periods):")
        logger.info("-" * 60)
        recent = df[['Close', 'MACD', 'Signal', 'Histogram']].tail(10)
        logger.info(recent.to_string())

    return signal_type, crossover


def analyze_multiple_symbols(symbols: list, delay: float = 0) -> Dict[str, Dict]:
    """
    Analyze MACD for multiple symbols.

    Parameters:
    -----------
    symbols : list
        List of ticker symbols
    delay : float
        Delay between requests in seconds (0 = no delay with yfinance)

    Returns:
    --------
    dict
        Dictionary with symbol as key and MACD data as value
    """

    import time

    results = {}

    logger.info(f"{'='*60}")
    logger.info(f"Analyzing {len(symbols)} symbols")
    logger.info(f"{'='*60}")

    for symbol in symbols:
        result = get_latest_macd(symbol)

        if result:
            macd, signal, histogram, date = result
            trend = "BULLISH 📈" if histogram > 0 else "BEARISH 📉"

            results[symbol] = {
                'macd': macd,
                'signal': signal,
                'histogram': histogram,
                'date': date,
                'trend': trend
            }

            logger.info(f"{symbol:15} | MACD: {macd:8.4f} | Signal: {signal:8.4f} | Hist: {histogram:8.4f} | {trend}")
        else:
            logger.info(f"{symbol:15} | ❌ No data available")
            results[symbol] = None

        if delay > 0:
            time.sleep(delay)

    return results

def has_crossover_been_notified(db, symbol, crossover_type):
    """Check if we've already notified about this crossover"""
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT last_crossover_type, last_notified_time
        FROM macd_notifications
        WHERE symbol = ?
    """, (symbol,))

    result = cursor.fetchone()
    conn.close()

    if result is None:
        return False

    last_type, last_time = result
    return last_type == crossover_type

def record_crossover_notification(db, symbol, crossover_type):
    """Record that we've notified about this crossover"""
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO macd_notifications (symbol, last_crossover_type, last_crossover_time, last_notified_time)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            last_crossover_type = excluded.last_crossover_type,
            last_crossover_time = excluded.last_crossover_time,
            last_notified_time = excluded.last_notified_time
    """, (symbol, crossover_type, now, now))

    conn.commit()
    conn.close()

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

def update_flag(flag, db):
    conn = get_db(db)
    c = conn.cursor()

    c.execute("SELECT status FROM flags WHERE flag=?", (flag,))
    row = c.fetchone()

    if row is None:
        c.execute("INSERT INTO flags (flag, status) VALUES (?, ?)",
                  (flag, 'False'))
    else:
        current_status = row[0]
        new_status = not current_status
        c.execute("UPDATE flags SET status=? WHERE flag=?",
                  (new_status, flag))

    conn.commit()
    conn.close()

def get_flag(flag, db, default=False):
    conn = get_db(db)
    c = conn.cursor()
    c.execute("SELECT status FROM flags WHERE flag=?", (flag,))
    row = c.fetchone()
    conn.close()

    if row is None:
        return default

    return row[0]

def update_stop_loss(ticker, stop_loss_price, db):
    conn = get_db(db)
    c = conn.cursor()

    c.execute("SELECT stop_loss FROM positions WHERE ticker=?", (ticker,))
    row = c.fetchone()

    if row is None:
        c.execute("INSERT INTO positions (ticker, stop_loss) VALUES (?, ?)",
                  (ticker, stop_loss_price))
    else:
        c.execute("UPDATE positions SET stop_loss=? WHERE ticker=?",
                  (stop_loss_price, ticker))

    conn.commit()
    conn.close()

def cleanup_stale_notifications(db, active_tickers):
    """Remove notification records for tickers not in current positions"""
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    # Get all tickers currently in the database
    cursor.execute("SELECT DISTINCT ticker FROM positions")
    db_tickers = {row[0] for row in cursor.fetchall()}

    # Find tickers to remove (in DB but not in active positions)
    stale_tickers = db_tickers - set(active_tickers)

    if stale_tickers:
        # Delete stale entries
        placeholders = ','.join('?' * len(stale_tickers))
        cursor.execute(f"DELETE FROM positions WHERE ticker IN ({placeholders})",
                      tuple(stale_tickers))
        deleted_count = cursor.rowcount
        conn.commit()
        logger.info(f"Cleaned up {deleted_count} stale notification records for tickers: {stale_tickers}")
    else:
        logger.info("No stale notification records to clean up")

    conn.close()

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

def get_account_value():
    url = f"{T212_API_BASE}/account/cash"
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

def get_current_positions(db, all_tickers, risk_percentage = RISK_PERCENTAGE):
    result = {} # Full result dict to return, including positions and total risk
    total_risk = 0.0
    all_positions = []

    positions = fetch_positions()
    orders = fetch_orders()
    stop_orders = [o for o in orders if o.get("type") in ["STOP", "STOP_LIMIT"]]

    total_capital = get_account_value()["total"]
    total_risk_per_trade = total_capital * risk_percentage / 100    # 0.07% of account value

    for pos in positions:
        position_dict = {}

        ticker_info = next((item for item in all_tickers if item['ticker'] == pos['ticker']), None)

        # Basic data update from current positions
        position_dict["ticker"] = ticker_info['ticker']
        position_dict["short_name"] = ticker_info['shortName']
        position_dict["name"] = ticker_info['name']
        position_dict["currency"] = ticker_info["currencyCode"]

        if ticker_info["currencyCode"] == "GBX" or ticker_info["currencyCode"] == "GBP" or ticker_info["shortName"] in ["3CFL", "COFF", "COCO"]: # Coffee/Cocoa is in USD but listed in London
            position_dict["short_name"] += ".L"

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

        # Calculate the stop loss and update the DB if needed
        position_value = position_dict["quantity"] * position_dict["average_price"]
        stop_loss_caculating_price = max(position_dict["average_price"], position_dict["max_price"])

        if ticker_info["currencyCode"] == "GBX":
            position_value /= 100
            risk_for_calculation = total_risk_per_trade * 100
        else:
            risk_for_calculation = total_risk_per_trade

        position_dict["stop_loss_price"] = round(stop_loss_caculating_price - (risk_for_calculation / position_dict["quantity"]), 2)
        position_dict["stop_loss_percentage"] = round(((stop_loss_caculating_price - position_dict["stop_loss_price"]) / stop_loss_caculating_price) * 100, 2)
        update_stop_loss(position_dict["ticker"], position_dict["stop_loss_price"], db)

        # Check if a manual stop loss has been set
        stop_order = next((o for o in stop_orders if o.get("ticker") == pos["ticker"]), None)
        # logger.info(f"Checking manual stop loss for {position_dict['ticker']}: {stop_order}")
        position_dict["manual_stop_loss_price"] = float(stop_order["stopPrice"]) if stop_order is not None else None
        position_dict["manual_stop_loss_quantity"] = stop_order["quantity"] if stop_order is not None else 0

        # Calculate total risk
        stop_loss_price = position_dict["manual_stop_loss_price"] if position_dict["manual_stop_loss_price"] is not None else position_dict["stop_loss_price"]
        if position_dict["average_price"] > stop_loss_price:
            risk_percentage = (position_dict["average_price"] - stop_loss_price) / position_dict["average_price"]
            logger.info(f"Risk percentage for {position_dict['ticker']}: {risk_percentage*100:.2f}%")
        else:
            risk_percentage = 0.0
        total_risk += risk_percentage * position_value

        # Check MACD
        signal_type, crossover = analyze_macd_signal(position_dict["short_name"])
        # logger.info(f"Analyzing {position_dict['short_name']} ({position_dict['name']}): {signal_type} / {crossover}")
        position_dict["macd_signal"] = signal_type
        position_dict["macd_crossover"] = crossover
        # logger.info(f"Signal type: {signal_type}")

        if crossover is not None:
            symbol = position_dict["short_name"]
            if not has_crossover_been_notified(db, symbol, crossover):
                send_telegram_message(
                    f"🚨 {position_dict['short_name']} ({position_dict['name']}) MACD {crossover} crossover!"
                )
                record_crossover_notification(db, symbol, crossover)
                logger.info(f"Notification sent and recorded for {symbol} {crossover} crossover")
            else:
                logger.info(f"Already notified about {symbol} {crossover} crossover, skipping")

        # Check SMA (17)
        sma_value = get_sma(position_dict['short_name'], days=17)
        position_dict['sma_17'] = sma_value if (sma_value is not None and not math.isnan(sma_value)) else 0.0
        logger.info(f"SMA(17) for {position_dict['short_name']}: {position_dict['sma_17']}")

        # Check if stop loss has been reached, then if auto_sell is enabled, sell at market and send a message (only weekdays)
        if get_flag("auto_sell", db) and position_dict["stop_loss_price"] >= position_dict["current_price"] and date.today().weekday() < 5:
            # Attempt to sell - It will only sell if there are no stop losses already set
            # and the error code will be 'SellingEquityNotOwned'

            rc = sell(position_dict['ticker'], position_dict['quantity'])

            if "type" in rc and rc["type"] == "/api-errors/selling-equity-not-owned":
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

    # Clean up old symbols from DB
    active_tickers = [position_dict['ticker'] for position_dict in all_positions]
    cleanup_stale_notifications(db, active_tickers)

    # Build json
    result = {
        "positions": sorted(all_positions, key=lambda order: order['profit_pct'], reverse=True),
        "total_risk": total_risk / total_capital * 100,
        "auto_sell": get_flag("auto_sell", db)
    }

    # logger.info(tabulate(result['positions'], headers='keys', tablefmt='simple'))
    # logger.info(f"Total Risk: {result['total_risk']:.2f}% of account value")
    logger.info(json.dumps(result, indent=4))

    return result

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
