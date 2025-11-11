from flask import Flask, render_template, render_template_string, jsonify
import os
import papishares

app = Flask(__name__)
db = os.getenv('DB_PATH', './papishares.db')
papishares.initialize_database(db)
all_tickers = papishares.fetch_all_tickers_info()

@app.route('/positions')
def get_positions():
    positions = papishares.get_current_positions(db, all_tickers)
    return positions

@app.route('/orders')
def get_orders():
    orders = papishares.get_pending_orders(all_tickers)
    return orders

@app.route('/entries')
def get_entries():
    entries = papishares.get_last_entries()
    return render_template('entries.html', data=entries, risk=70)

@app.route('/autosell', methods=['POST'])
def autosell():
    new_status = papishares.update_flag('auto_sell', db)
    return jsonify({'auto_sell': new_status})

@app.route('/')
def index():
    return render_template('positions.html')

@app.route("/healthz")
def healthz():
    return jsonify(status="ok"), 200

@app.route("/readyz")
def readyz():
    return jsonify(status="ready"), 200

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)
