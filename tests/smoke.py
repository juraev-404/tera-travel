from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = 'altai'
MODE = 'request'
ITEM = None
PRICE = None


def request(url, data=None):
    headers = {'Content-Type': 'application/json'} if data is not None else {}
    body = json.dumps(data).encode('utf-8') if data is not None else None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers), timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    with tempfile.TemporaryDirectory() as data_dir:
        env = dict(os.environ, PORTFOLIO_DATA_DIR=data_dir)
        if MODE == 'static':
            command = [sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1', '--directory', str(ROOT / 'public')]
        else:
            command = [sys.executable, str(ROOT / 'server.py'), '--port', str(port)]
        proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, cwd=ROOT)
        try:
            for _ in range(50):
                try:
                    status, html = request(base + '/')
                    if status == 200:
                        break
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(.1)
            else:
                raise AssertionError('Server did not start')
            assert b'<html' in html.lower(), 'Homepage did not render'
            if MODE == 'static':
                assert request(base + '/pulse.js')[0] == 200
                assert b'data-pane' in html
            else:
                assert request(base + '/assets/common.css')[0] == 200
                assert request(base + '/assets/common.js')[0] == 200
                assert json.loads(request(base + '/api/health')[1])['ok']
                assert request(base + '/server.py')[0] == 404
                if MODE == 'order':
                    status, body = request(base + '/api/submit', {'site': SITE, 'kind': 'order', 'delivery': 'Самовывоз', 'items': [{'id': ITEM, 'quantity': 2, 'price': 1}]})
                    result = json.loads(body)
                    assert status == 200 and result['total'] == 2 * PRICE and result['reference']
                    status, _ = request(base + '/api/submit', {'site': SITE, 'kind': 'order', 'delivery': 'Самовывоз', 'items': [{'id': ITEM, 'quantity': 0}]})
                    assert status == 400
                else:
                    status, body = request(base + '/api/submit', {'site': SITE, 'kind': 'request', 'name': 'Тест', 'service': 'Демо'})
                    assert status == 200 and json.loads(body)['reference']
                status, _ = request(base + '/api/submit', {'site': ['invalid'], 'kind': 'request'})
                assert status == 400
            print(f'PASS: {SITE} standalone homepage and {MODE} scenario')
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


if __name__ == '__main__':
    main()
