#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Лабораторная работа №12 — «Ментальный покер» (Техасский холдем) с веб-интерфейсом.

Запуск:  python3 server.py            (порт 8012, либо переменная окружения PORT)
         python3 server.py --port 9000
Открыть: http://127.0.0.1:8012

Только стандартная библиотека Python — ничего устанавливать не нужно.
"""
import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from game import Game

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
GAME = Game()

MIME = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
        '.js': 'application/javascript; charset=utf-8', '.svg': 'image/svg+xml',
        '.ico': 'image/x-icon', '.png': 'image/png'}


class Handler(BaseHTTPRequestHandler):
    server_version = 'MentalPoker/1.0'

    # ---------- helpers ----------
    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path):
        ext = os.path.splitext(path)[1].lower()
        try:
            with open(path, 'rb') as f:
                body = f.read()
        except OSError:
            self._send_json({'error': 'not found'}, 404)
            return
        self.send_response(200)
        self.send_header('Content-Type', MIME.get(ext, 'application/octet-stream'))
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length else b'{}'
        try:
            return json.loads(raw.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError('Некорректный JSON в теле запроса')

    def log_message(self, fmt, *args):  # тише в консоли
        pass

    # ---------- routing ----------
    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path == '/':
            self._send_file(os.path.join(STATIC_DIR, 'index.html'))
            return
        if path == '/api/state':
            self._send_json(GAME.state_dict(include_secrets=False))
            return
        if path == '/api/secrets':
            self._send_json(GAME.state_dict(include_secrets=True).get('protocol', {}))
            return
        m = re.match(r'^/static/([A-Za-z0-9_.-]+)$', path)
        if m:
            self._send_file(os.path.join(STATIC_DIR, m.group(1)))
            return
        self._send_json({'error': 'not found'}, 404)

    def do_POST(self):
        path = self.path.split('?', 1)[0]
        try:
            data = self._read_json()
            if path == '/api/new_game':
                players = data.get('players') or []
                deck_size = int(data.get('deck_size', 52))
                p_bits = int(data.get('p_bits', 512))
                if p_bits not in (256, 384, 512, 768, 1024):
                    raise ValueError('p_bits: 256/384/512/768/1024')
                self._send_json(GAME.new_game(players, deck_size=deck_size, p_bits=p_bits))
                return
            if path == '/api/deal':
                self._send_json(GAME.deal())
                return
            if path == '/api/community':
                self._send_json(GAME.community_stage(str(data.get('stage', ''))))
                return
            if path == '/api/showdown':
                self._send_json(GAME.showdown())
                return
            if path == '/api/reset':
                GAME.reset()
                self._send_json({'ok': True})
                return
            self._send_json({'error': 'not found'}, 404)
        except ValueError as e:
            self._send_json({'error': str(e)}, 400)
        except Exception as e:  # noqa: BLE001 — учебный стенд: показываем ошибку пользователю
            self._send_json({'error': f'{type(e).__name__}: {e}'}, 500)


def main():
    port = 8012
    args = sys.argv[1:]
    if '--port' in args:
        port = int(args[args.index('--port') + 1])
    elif os.environ.get('PORT'):
        port = int(os.environ['PORT'])
    httpd = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    print(f'ЛР №12 «Ментальный покер» — http://127.0.0.1:{port}  (Ctrl+C для выхода)')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
