from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
import pytz
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///signals.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Signal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(50))
    event = db.Column(db.String(20))
    price = db.Column(db.Float)
    lots = db.Column(db.Float)
    lot_size = db.Column(db.Float)
    quantity = db.Column(db.Float)
    trade_value = db.Column(db.Float)
    total_purchase = db.Column(db.Float)
    position = db.Column(db.Float)
    avg_buy_price = db.Column(db.Float)
    time = db.Column(db.String(50))
    pnl = db.Column(db.Float, nullable=True)
    cumulative_pnl = db.Column(db.Float, nullable=True)

with app.app_context():
    db.create_all()

@app.route('/')
def home():
    return '''
    <html>
    <head><title>Webhook Receiver</title></head>
    <body style="font-family: Arial; background-color: #f0f8ff; text-align: center; padding-top: 80px;">
    <h1>🚀 Webhook Receiver with Extended Trade Table</h1>
    <p>Send TradingView webhook to <strong>/webhook</strong> endpoint.</p>
    <p>View stored signals table at <a href='/signals' target='_blank'>/signals</a>.</p>
    </body>
    </html>
    '''

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        import json
        data = json.loads(request.data.decode('utf-8'))
        symbol = data.get("symbol")
        event = data.get("event").lower()
        price = float(data.get("price"))
        lots = float(data.get("lots"))
        lot_size = float(data.get("lot_size"))
        quantity = float(data.get("quantity"))
        trade_value = float(data.get("trade_value"))
        utc_time_raw = data.get("time")

        if isinstance(utc_time_raw, int):
            utc_time = datetime.utcfromtimestamp(utc_time_raw / 1000)
            utc_time = pytz.utc.localize(utc_time)
        elif isinstance(utc_time_raw, str):
            utc_time = datetime.strptime(utc_time_raw, "%Y-%m-%dT%H:%M:%SZ")
            utc_time = pytz.utc.localize(utc_time)
        else:
            raise ValueError(f"Unsupported time format received: {utc_time_raw}")

        ist_time = utc_time.astimezone(pytz.timezone("Asia/Kolkata"))
        time_str = ist_time.strftime("%d-%m-%Y %H:%M:%S")

        signals_df = pd.read_sql(Signal.query.statement, db.session.bind)
        total_purchase = signals_df['trade_value'][signals_df['event'] == 'buy'].sum() + (trade_value if event == 'buy' else 0)
        position = signals_df['quantity'][signals_df['event'] == 'buy'].sum() - signals_df['quantity'][signals_df['event'] == 'sell'].sum()
        position = position + (quantity if event == 'buy' else -quantity)

        # Calculate weighted average buy price on buys only
        buy_signals = signals_df[signals_df['event'] == 'buy']
        total_qty = buy_signals['quantity'].sum() + (quantity if event == 'buy' else 0)
        total_cost = (buy_signals['price'] * buy_signals['quantity']).sum() + (price * quantity if event == 'buy' else 0)
        avg_buy_price = (total_cost / total_qty) if total_qty != 0 else 0

        pnl_value = None
        last_signal = Signal.query.order_by(Signal.id.desc()).first()
        last_cumulative = last_signal.cumulative_pnl if last_signal and last_signal.cumulative_pnl is not None else 0

        if event == "sell":
            pnl_value = (price - avg_buy_price) * quantity
            cumulative_pnl_value = last_cumulative + pnl_value
        else:
            cumulative_pnl_value = last_cumulative

        new_signal = Signal(
            symbol=symbol,
            event=event,
            price=price,
            lots=lots,
            lot_size=lot_size,
            quantity=quantity,
            trade_value=trade_value,
            total_purchase=total_purchase,
            position=position,
            avg_buy_price=avg_buy_price,
            time=time_str,
            pnl=pnl_value,
            cumulative_pnl=cumulative_pnl_value
        )
        db.session.add(new_signal)
        db.session.commit()

        print(f"✅ {event.upper()} | {symbol} @ {price} | Qty: {quantity} | PnL: {pnl_value} | Cum PnL: {cumulative_pnl_value}")

        return jsonify({
            "status": "success",
            "symbol": symbol,
            "event": event,
            "price": price,
            "lots": lots,
            "lot_size": lot_size,
            "quantity": quantity,
            "trade_value": trade_value,
            "total_purchase": total_purchase,
            "position": position,
            "avg_buy_price": avg_buy_price,
            "time": time_str,
            "pnl": pnl_value,
            "cumulative_pnl": cumulative_pnl_value
        }), 200

    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/signals', methods=['GET', 'POST'])
def view_signals():
    if request.method == 'POST':
        try:
            Signal.query.delete()
            db.session.commit()
            print("⚠️ All records deleted.")
        except Exception as e:
            print(f"❌ Error while deleting: {e}")
        return redirect(url_for('view_signals'))

    signals = Signal.query.all()

    table_html = '''
        <html>
        <head>
            <title>Trade Table with PnL</title>
            <style>
                body { font-family: Arial; background-color: #f9f9f9; padding: 20px; text-align: center; }
                table { border-collapse: collapse; width: 95%; margin: auto; }
                th, td { border: 1px solid #ccc; padding: 8px; text-align: center; font-size: 14px; }
                th { background-color: #f0f0f0; }
                h1 { text-align: center; }
                .delete-button { background-color: red; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; margin: 20px; }
                .pnl-profit { color: green; font-weight: bold; }
                .pnl-loss { color: red; font-weight: bold; }
            </style>
        </head>
        <body>
            <h1>📊 Trading Table with Live PnL</h1>
            <form method="post" onsubmit="return confirm('Delete all records?');">
                <button type="submit" class="delete-button">🚨 Delete All</button>
            </form>
            <table>
                <tr>
                    <th>ID</th><th>SYMBOL</th><th>EVENT</th><th>PRICE</th><th>LOTS</th><th>LOT SIZE</th>
                    <th>QUANTITY</th><th>TRANSACTION</th><th>TOTAL PURCHASE</th><th>POSITION</th>
                    <th>AVG BUY PRICE</th><th>TIME</th><th>PnL</th><th>CUMULATIVE PnL</th>
                </tr>
                {% for s in signals %}
                <tr>
                    <td>{{ s.id }}</td><td>{{ s.symbol }}</td><td>{{ s.event }}</td><td>{{ s.price }}</td>
                    <td>{{ s.lots }}</td><td>{{ s.lot_size }}</td><td>{{ s.quantity }}</td>
                    <td>{{ s.trade_value }}</td><td>{{ s.total_purchase }}</td><td>{{ s.position }}</td>
                    <td>{{ "%.2f"|format(s.avg_buy_price) }}</td><td>{{ s.time }}</td>
                    <td>
                        {% if s.pnl is not none %}
                            {% if s.pnl > 0 %}
                                <span class="pnl-profit">{{ "%.2f"|format(s.pnl) }}</span>
                            {% elif s.pnl < 0 %}
                                <span class="pnl-loss">{{ "%.2f"|format(s.pnl) }}</span>
                            {% else %}
                                {{ "%.2f"|format(s.pnl) }}
                            {% endif %}
                        {% endif %}
                    </td>
                    <td>
                        {% if s.cumulative_pnl is not none %}
                            {% if s.cumulative_pnl > 0 %}
                                <span class="pnl-profit">{{ "%.2f"|format(s.cumulative_pnl) }}</span>
                            {% elif s.cumulative_pnl < 0 %}
                                <span class="pnl-loss">{{ "%.2f"|format(s.cumulative_pnl) }}</span>
                            {% else %}
                                {{ "%.2f"|format(s.cumulative_pnl) }}
                            {% endif %}
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </table>
        </body>
        </html>
    '''

    return render_template_string(table_html, signals=signals)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
