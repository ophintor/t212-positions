from flask import Flask, render_template
import papishares

app = Flask(__name__)

@app.route('/')
def index():
    orders = papishares.get_stop_losses()
    sorted_orders = sorted(orders, key=lambda order: order['profit_pct'], reverse=True)
    return render_template('orders.html', orders=sorted_orders)

if __name__ == '__main__':
    app.run(debug=True)
