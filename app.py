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
    <h1>🚀 Webhook Receiver with PnL & Cumulative PnL</h1>
    <p>Send TradingView webhook to <strong>/webhook</strong> endpoint.</p>
    <p>View stored signals table at <a href='/signals' target='_blank'>/signals</a>.</p>
    </body>
    </html>
    '''

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        symbol = data.get("symbol")
        event = data.get("event").lower()
        price = float(data.get("price"))
        utc_time_str = data.get("time")

        utc_time = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%SZ")
        utc_time = pytz.utc.localize(utc_time)
        ist_time = utc_time.astimezone(pytz.timezone("Asia/Kolkata"))
        time_str = ist_time.strftime("%d-%m-%Y %H:%M:%S")

        pnl_value = None
        cumulative_pnl_value = None

        # Get last cumulative PnL
        last_signal = Signal.query.order_by(Signal.id.desc()).first()
        last_cumulative = last_signal.cumulative_pnl if last_signal and last_signal.cumulative_pnl is not None else 0

        if event == "sell":
            unmatched_buy = Signal.query.filter_by(symbol=symbol, event='buy', pnl=None).order_by(Signal.id.asc()).first()
            if unmatched_buy:
                pnl_value = price - unmatched_buy.price
                unmatched_buy.pnl = pnl_value
                db.session.commit()
                cumulative_pnl_value = last_cumulative + pnl_value
            else:
                cumulative_pnl_value = last_cumulative
        else:  # 'buy' event
            cumulative_pnl_value = last_cumulative

        new_signal = Signal(
            symbol=symbol,
            event=event,
            price=price,
            time=time_str,
            pnl=pnl_value,
            cumulative_pnl=cumulative_pnl_value
        )
        db.session.add(new_signal)
        db.session.commit()

        print(f"🔔 {event.upper()} signal received for {symbol} at {price} | PnL: {pnl_value} | Cumulative PnL: {cumulative_pnl_value}")

        return jsonify({
            "status": "success",
            "symbol": symbol,
            "event": event,
            "price": price,
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
            print("⚠️ All records deleted from signals table.")
        except Exception as e:
            print(f"❌ Error while deleting records: {e}")
        return redirect(url_for('view_signals'))

    signals = Signal.query.all()

    table_html = '''
        <html>
        <head>
            <title>Stored Signals with PnL</title>
            <style>
                body { font-family: Arial; background-color: #f9f9f9; padding: 20px; text-align: center; }
                table { border-collapse: collapse; width: 90%; margin: auto; }
                th, td { border: 1px solid #ccc; padding: 8px; text-align: center; }
                th { background-color: #f0f0f0; }
                h1 { text-align: center; }
                .delete-button {
                    background-color: red;
                    color: white;
                    padding: 10px 20px;
                    border: none;
                    border-radius: 5px;
                    cursor: pointer;
                    margin: 20px;
                }
                .pnl-profit {
                    color: green;
                    font-weight: bold;
                }
                .pnl-loss {
                    color: red;
                    font-weight: bold;
                }
            </style>
        </head>
        <body>
            <h1>📊 Stored TradingView Signals with PnL</h1>
            <form method="post" onsubmit="return confirm('Are you sure you want to delete all records?');">
                <button type="submit" class="delete-button">🚨 Delete All Records</button>
            </form>
            <table>
                <tr>
                    <th>ID</th>
                    <th>Symbol</th>
                    <th>Event</th>
                    <th>Price</th>
                    <th>Time (IST)</th>
                    <th>PnL</th>
                    <th>Cumulative PnL</th>
                </tr>
                {% for s in signals %}
                <tr>
                    <td>{{ s.id }}</td>
                    <td>{{ s.symbol }}</td>
                    <td>{{ s.event }}</td>
                    <td>{{ s.price }}</td>
                    <td>{{ s.time }}</td>
                    <td>
                        {% if s.event == 'sell' and s.pnl is not none %}
                            {% if s.pnl > 0 %}
                                <span class="pnl-profit">{{ "%.2f"|format(s.pnl) }}</span>
                            {% elif s.pnl < 0 %}
                                <span class="pnl-loss">{{ "%.2f"|format(s.pnl) }}</span>
                            {% else %}
                                {{ "%.2f"|format(s.pnl) }}
                            {% endif %}
                        {% else %}
                            <!-- Empty for 'buy' rows -->
                        {% endif %}
                    </td>
                    <td>
                        {% if s.event == 'sell' and s.cumulative_pnl is not none %}
                            {% if s.cumulative_pnl > 0 %}
                                <span class="pnl-profit">{{ "%.2f"|format(s.cumulative_pnl) }}</span>
                            {% elif s.cumulative_pnl < 0 %}
                                <span class="pnl-loss">{{ "%.2f"|format(s.cumulative_pnl) }}</span>
                            {% else %}
                                {{ "%.2f"|format(s.cumulative_pnl) }}
                            {% endif %}
                        {% else %}
                            <!-- Empty for 'buy' rows -->
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
