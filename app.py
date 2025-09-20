from flask import Flask, render_template, jsonify
import papishares

app = Flask(__name__)

@app.route('/data')
def get_data():
    orders = papishares.get_stop_losses()
    return sorted(orders, key=lambda order: order['profit_pct'], reverse=True)

@app.route('/')
def index():
    return render_template('orders.html')

@app.route("/healthz")
def healthz():
    return jsonify(status="ok"), 200

@app.route("/readyz")
def readyz():
    return jsonify(status="ready"), 200

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)
