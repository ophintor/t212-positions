import sqlite3
from flask import Flask, render_template, jsonify
import papishares

app = Flask(__name__)
db = 'positions.db'
papishares.initialize_database(db)

@app.route('/positions')
def get_positions():
    positions = papishares.get_current_positions(db)
    return sorted(positions, key=lambda order: order['profit_pct'], reverse=True)

@app.route('/orders')
def get_orders():
    orders = papishares.get_pending_orders()
    return orders

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
