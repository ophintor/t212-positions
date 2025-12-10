import time
import papishares

def manage_stop_losses():
    positions = papishares.fetch_positions()
    orders = papishares.fetch_orders()
    stop_orders = [o for o in orders if o.get("type") in ["STOP", "STOP_LIMIT"]]
    adjustments = False
    message = ""
    exceptions = [] #["MU_US_EQ", "WIX_US_EQ", "SCWO_US_EQ", "DMYI_US_EQ", "SNII_US_EQ"] # Micron, Wix, 374Water, IonQ, Rigetti
    default_target_stop_pct = 4

    for pos in positions:
        if pos["ticker"] in papishares.TICKERS:
            ticker = papishares.TICKERS[pos["ticker"]]
        else:
            ticker = pos["ticker"]

        qty = float(pos["quantity"])
        avg_price = float(pos["averagePrice"])
        current_price = float(papishares.get_price(pos["ticker"]))

        # Profit %
        profit_pct = ((current_price - avg_price) / avg_price) * 100

        # Decide stop distance
        stop_distance_pct = default_target_stop_pct + int(profit_pct / 10)

        # Target stop price
        target_stop = round(current_price * (1 - stop_distance_pct / 100), default_target_stop_pct)

        # Existing stop (if any)
        stop_order = next((o for o in stop_orders if o.get("ticker") == pos["ticker"]), None)
        stop_loss_price = float(stop_order["stopPrice"]) if stop_order is not None else None

        # Actual distance from current price
        if stop_loss_price is not None:
            actual_distance_pct = ((current_price - stop_loss_price) / current_price) * 100
            distance_str = f"{actual_distance_pct:.2f}%"
        else:
            actual_distance_pct = None
            distance_str = "N/A"

        # Only flag when existing stop is a loser (i.e. actual_distance > desired) by tolerance
        tolerance = 1  # percent
        needs_adjust = False

        if stop_loss_price is None:
            needs_adjust = True
        else:
            if (actual_distance_pct - stop_distance_pct) >= tolerance:
                needs_adjust = True

        if needs_adjust and pos["ticker"] not in exceptions:
            adjustments = True
            # padding = " " * 4
            if stop_loss_price is None:
                distance_display = f"[Not set]\n⚠️ Adjust to {target_stop} [-{stop_distance_pct}%]"
            else:
                distance_display = f"[{distance_str}]\n⚠️ Adjust to {target_stop} [-{stop_distance_pct}%]"
        else:
            distance_display = f"[{distance_str}]"

        stop_loss_display = f"{stop_loss_price}" if stop_loss_price is not None else "N/A"
        # padding_ticker = " " * (12 - len(pos['ticker']))
        # padding_ticker = " " * (15 - len(ticker))
        minus_padding = "" if profit_pct < 0 else " "
        padding_profit = " " * (6 - len(f"{abs(profit_pct):.2f}"))
        padding_stop = " " * (7 - len(stop_loss_display))
        message += f"{pos['ticker']}: {ticker}\n"
        message += f"P/L: {minus_padding}{profit_pct:.2f}%{padding_profit}SL: {stop_loss_display}{padding_stop}{distance_display}\n"
        message += "- " * 18 + "\n"

        time.sleep(1)  # To avoid hitting rate limits

        # Optionally auto-adjust:
        # if needs_adjust:
        #     result = update_stop_order(ticker, qty, target_stop)
        #     print("✅ Stop updated:", result)

    print(message)
    if adjustments:
        papishares.send_telegram_message(f"<code>{message}</code>")

if __name__ == "__main__":
    # while True:
        manage_stop_losses()
        # papishares.report_price_moves()
