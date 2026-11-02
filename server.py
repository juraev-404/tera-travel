#!/usr/bin/env python3
"""Small, dependency-free server for the portfolio demos.

Only files in public/ are served. Demo submissions contain no payment or contact
details and are kept separately from all other applications on the machine.
"""
from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import json
import mimetypes
import os
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / 'public'
DATA = Path(os.environ.get('PORTFOLIO_DATA_DIR', ROOT / 'data')).resolve()
DB = DATA / 'demo.sqlite3'
LIMITS = defaultdict(deque)
LOCK = threading.Lock()
SITES = {'altai'}


def setup():
    DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
    with sqlite3.connect(DB) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS submissions (id TEXT PRIMARY KEY, site TEXT NOT NULL, kind TEXT NOT NULL, created TEXT NOT NULL, payload TEXT NOT NULL)')
    purge_old_submissions()
    threading.Thread(target=housekeeping, daemon=True).start()


def purge_old_submissions():
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).isoformat()
    with sqlite3.connect(DB, timeout=5) as db:
        db.execute('DELETE FROM submissions WHERE created < ?', (cutoff,))


def housekeeping():
    while True:
        time.sleep(6 * 60 * 60)
        try:
            purge_old_submissions()
        except sqlite3.Error:
            pass


def clean(value, size=100):
    if not isinstance(value, str):
        raise ValueError('Некорректное поле формы')
    value = ' '.join(value.split())
    if len(value) > size:
        raise ValueError('Одно из полей слишком длинное')
    return value


def products():
    with (PUBLIC / 'assets' / 'products.json').open(encoding='utf-8') as f:
        return json.load(f)


def submit(data):
    if not isinstance(data, dict) or not isinstance(data.get('site'), str) or data.get('site') not in SITES:
        raise ValueError('Неизвестный проект')
    site, kind = data['site'], data.get('kind')
    if kind == 'order':
        if site not in {'forma', 'takt'}:
            raise ValueError('Заказ недоступен')
        catalog = {p['id']: p for p in products()[site]}
        items = data.get('items')
        if not isinstance(items, list) or not 1 <= len(items) <= 20:
            raise ValueError('Корзина пуста')
        checked, total, seen = [], 0, set()
        for item in items:
            if not isinstance(item, dict):
                raise ValueError('Некорректный товар')
            ident, qty = item.get('id'), item.get('quantity')
            if not isinstance(ident, str) or ident not in catalog or ident in seen or type(qty) is not int or not 1 <= qty <= 20:
                raise ValueError('Проверьте состав корзины')
            seen.add(ident)
            p = catalog[ident]
            total += p['price'] * qty
            checked.append({'id': ident, 'name': p['name'], 'price': p['price'], 'quantity': qty})
        payload = {'items': checked, 'total': total, 'delivery': clean(data.get('delivery', ''), 40)}
        if payload['delivery'] not in {'Самовывоз', 'Доставка'}:
            raise ValueError('Выберите способ получения')
    elif kind == 'request':
        if site not in {'arkhe', 'sol', 'luma', 'altai', 'flow'}:
            raise ValueError('Форма недоступна')
        payload = {k: clean(data.get(k, ''), 120) for k in ('name', 'service', 'date', 'time', 'guests')}
        if not payload['name'] or not payload['service']:
            raise ValueError('Заполните обязательные поля')
        if payload['date']:
            try:
                date = dt.date.fromisoformat(payload['date'])
            except ValueError:
                raise ValueError('Проверьте дату') from None
            if not dt.date.today() <= date <= dt.date.today() + dt.timedelta(days=730):
                raise ValueError('Выберите будущую дату')
    else:
        raise ValueError('Неизвестный тип формы')
    now = dt.datetime.now(dt.timezone.utc)
    ident = secrets.token_hex(5).upper()
    with sqlite3.connect(DB, timeout=5) as db:
        db.execute('DELETE FROM submissions WHERE created < ?', ((now - dt.timedelta(days=7)).isoformat(),))
        db.execute('INSERT INTO submissions VALUES (?, ?, ?, ?, ?)', (ident, site, kind, now.isoformat(), json.dumps(payload, ensure_ascii=False)))
    return {'ok': True, 'reference': ident, **({'total': total} if kind == 'order' else {})}


class Handler(SimpleHTTPRequestHandler):
    server_version = 'PortfolioDemo'
    sys_version = ''

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC), **kwargs)

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        super().end_headers()

    def list_directory(self, path):
        self.send_error(HTTPStatus.NOT_FOUND)
        return None

    def json(self, status, value):
        body = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlparse(self.path).path == '/api/health':
            self.json(200, {'ok': True, 'service': 'portfolio-demos'})
        else:
            super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != '/api/submit':
            self.json(404, {'ok': False, 'error': 'Адрес не найден'})
            return
        origin = self.headers.get('Origin')
        if origin and urlparse(origin).netloc.lower() != self.headers.get('Host', '').lower():
            self.json(403, {'ok': False, 'error': 'Недопустимый источник запроса'})
            return
        peer = self.client_address[0]
        forwarded = self.headers.get('X-Real-IP', '')
        try:
            # Nginx overwrites this header. Only trust it from the loopback proxy.
            if ipaddress.ip_address(peer).is_loopback and forwarded:
                peer = str(ipaddress.ip_address(forwarded))
        except ValueError:
            peer = self.client_address[0]
        with LOCK:
            now = time.monotonic()
            if len(LIMITS) > 4096:
                for key in list(LIMITS):
                    if not LIMITS[key] or LIMITS[key][-1] < now - 60:
                        del LIMITS[key]
            if len(LIMITS) > 4096 and peer not in LIMITS:
                self.json(429, {'ok': False, 'error': 'Слишком много запросов. Попробуйте позже.'})
                return
            q = LIMITS[peer]
            while q and q[0] < now - 60:
                q.popleft()
            if len(q) >= 30:
                self.json(429, {'ok': False, 'error': 'Слишком много запросов. Попробуйте позже.'})
                return
            q.append(now)
        try:
            size = int(self.headers.get('Content-Length', '-1'))
            if size < 2 or size > 8192:
                raise ValueError('Некорректный размер запроса')
            if self.headers.get_content_type() != 'application/json':
                raise ValueError('Некорректный формат запроса')
            data = json.loads(self.rfile.read(size))
            self.json(200, submit(data))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.json(400, {'ok': False, 'error': str(exc) or 'Проверьте данные'})
        except sqlite3.Error:
            self.json(503, {'ok': False, 'error': 'Сервис временно недоступен'})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=19271)
    args = parser.parse_args()
    setup()
    mimetypes.add_type('image/svg+xml', '.svg')
    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f'Portfolio demos running on http://{args.bind}:{args.port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
