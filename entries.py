from io import StringIO
import yfinance as yf
import pandas as pd
import requests

urls = {
    "FTSE100": "https://en.wikipedia.org/wiki/FTSE_100_Index",
    "FTSE250": "https://en.wikipedia.org/wiki/FTSE_250_Index",
    "SP500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
}

def get_ftse_tickers():
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
    tickers = {}

    for index_name, url in urls.items():
        try:
            resp = requests.get(url, headers=headers)
            resp.raise_for_status()

            tables = pd.read_html(StringIO(resp.text), flavor="bs4")
            table = None
            ticker_col = None

            # auto-detect ticker column
            for t in tables:
                for col in ["Symbol", "EPIC", "Ticker"]:
                    if col in t.columns:
                        ticker_col, table = col, t
                        break
                if table is not None:
                    break

            if table is None:
                print(f"Could not find ticker column for {index_name}")
                tickers[index_name] = []
                continue

            symbols = table[ticker_col].dropna().astype(str).str.strip()

            # Append .L for FTSE stocks
            if index_name in ["FTSE100", "FTSE250"]:
                symbols = [sym + ".L" if not sym.endswith(".L") else sym for sym in symbols]

            tickers[index_name] = sorted(set(symbols))

        except Exception as e:
            print(f"Error retrieving {index_name}: {e}")
            tickers[index_name] = []

    return tickers


def tickers_recent_highs(tickers, windows=[20, 55], lookback_days=2):
    """
    Returns a dictionary with tickers that reached their rolling maximum
    within the last `lookback_days` for each window in `windows`.
    """
    results = {w: [] for w in windows}

    for ticker in tickers:
        try:
            # fetch enough history
            data = yf.download(ticker, period="3mo", interval="1d", auto_adjust=False, progress=False)  # ~60 trading days
            if data.empty:
                continue

            close = data["High"]

            for w in windows:
                rolling_max = close.rolling(window=w).max()

                # last N days
                last_n = close.tail(lookback_days)
                max_n = rolling_max.tail(lookback_days)

                # check if any of the last N closes hit the rolling max
                if any(last_n.values >= max_n.values):
                    results[w].append(ticker)
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")

    return results

def main():
    tickers = get_ftse_tickers()

    print("Collecting FTSE 100 tickers...")
    highs_ftse100 = tickers_recent_highs(tickers["FTSE100"], windows=[20, 55], lookback_days=2)
    print("Collecting FTSE 250 tickers...")
    highs_ftse250 = tickers_recent_highs(tickers["FTSE250"], windows=[20, 55], lookback_days=2)
    print("Collecting S&P 500 tickers...")
    highs_sp500 = tickers_recent_highs(tickers["SP500"], windows=[20, 55], lookback_days=2)

    print("FTSE 100 tickers")
    for w, tickers_at_high in highs_ftse100.items():
        print(f"{w}-day highs in the last 2 days:", tickers_at_high)

    print("FTSE 250 tickers")
    for w, tickers_at_high in highs_ftse250.items():
        print(f"{w}-day highs in the last 2 days:", tickers_at_high)

    print("S&P 500 tickers")
    for w, tickers_at_high in highs_sp500.items():
        print(f"{w}-day highs in the last 2 days:", tickers_at_high)
