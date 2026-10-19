import os
import ssl
from datetime import datetime
from zoneinfo import ZoneInfo
import pymysql
from flask import Flask, jsonify, request

app = Flask(__name__)

def get_connection():
    ca = os.environ['MYSQL_CA_PEM'].replace('\\n', '\n')
    tls = ssl.create_default_context(cadata=ca)
    return pymysql.connect(
        host=os.environ['MYSQL_HOST'],
        port=int(os.environ['MYSQL_PORT']),
        user=os.environ['MYSQL_USER'],
        password=os.environ['MYSQL_PASSWORD'],
        database=os.environ['MYSQL_DATABASE'],
        charset='utf8mb4', ssl=tls,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=15, read_timeout=20,
        write_timeout=20, autocommit=True)

@app.after_request
def headers(response):
    origin = os.environ.get('FRONTEND_ORIGIN', '').rstrip('/')
    if origin and request.headers.get('Origin') == origin:
        response.headers['Access-Control-Allow-Origin'] = origin
    response.headers['Vary'] = 'Origin'
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.get('/')
def home():
    return jsonify(message='銷售分析 API 已啟動',
                   data_endpoint='/api/dashboard')

@app.get('/api/dashboard')
def dashboard():
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute('SELECT * FROM sales ORDER BY sale_date,sale_id')
            rows = cursor.fetchall()
        daily, products, categories = {}, {}, {}
        quantity, returns, revenue = 0, 0, 0
        for row in rows:
            day = row['sale_date'].isoformat()
            name, category = row['product_name'], row['category']
            q, r = int(row['quantity']), int(row['returned_quantity'])
            value = row['unit_price'] * (q-r)
            quantity += q
            returns += r
            revenue += value
            daily[day] = daily.get(day, 0) + value
            products[name] = products.get(name, 0) + value
            categories[category] = categories.get(category, 0) + value
        return jsonify(
            generated_at=datetime.now(ZoneInfo('Asia/Taipei')).isoformat(),
            summary=dict(record_count=len(rows), total_quantity=quantity,
                         total_returns=returns, net_revenue=float(revenue)),
            daily=[dict(date=k,net_revenue=float(v))
                   for k,v in sorted(daily.items())],
            products=[dict(name=k,net_revenue=float(v))
                      for k,v in sorted(products.items(),
                                        key=lambda x:x[1],reverse=True)],
            categories=[dict(name=k,net_revenue=float(v))
                        for k,v in sorted(categories.items())])
    except Exception:
        app.logger.exception('資料庫查詢失敗')
        return jsonify(error='暫時無法取得資料，請稍後重試。'),503
    finally:
        if conn is not None:
            conn.close()
