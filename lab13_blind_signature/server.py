#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Лабораторная работа №13 — «Слепая подпись» на базе анонимного голосования.

Запуск:  python3 server.py            (порт 8013, либо переменная окружения PORT)
         python3 server.py --port 9000
Открыть: http://127.0.0.1:8013

Только стандартная библиотека Python — ничего устанавливать не нужно.
"""
import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from election import ElectionServer, VoterClient, CHOICES

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
MIME = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
        '.js': 'application/javascript; charset=utf-8', '.svg': 'image/svg+xml'}

LOCK = threading.Lock()
SERVER = ElectionServer()
CLIENTS = {}   # имя избирателя -> VoterClient


def fresh_election(with_defaults: bool = True):
    SERVER.reset()
    CLIENTS.clear()
    if with_defaults:
        for v in ('Алиса', 'Боб', 'Чарли'):
            SERVER.add_voter(v)
            CLIENTS[v] = VoterClient(v)
        SERVER.generate_keys(1024)


def client_for(voter: str) -> VoterClient:
    if voter not in CLIENTS:
        if voter not in SERVER.voters:
            raise ValueError(f'Избиратель «{voter}» не зарегистрирован')
        CLIENTS[voter] = VoterClient(voter)
    return CLIENTS[voter]


def full_state(include_server_secrets: bool = False) -> dict:
    d = SERVER.state(include_secrets=include_server_secrets)
    d['clients'] = {name: cl._view(include_secrets=True) for name, cl in CLIENTS.items()}
    return d


class Handler(BaseHTTPRequestHandler):
    server_version = 'BlindVotingLab/1.0'

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

    def log_message(self, fmt, *args):
        pass

    # ---------------- GET ----------------
    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path == '/':
            self._send_file(os.path.join(STATIC_DIR, 'index.html'))
            return
        if path == '/api/state':
            with LOCK:
                self._send_json(full_state(False))
            return
        if path == '/api/secrets':
            with LOCK:
                self._send_json(SERVER.state(include_secrets=True))
            return
        m = re.match(r'^/static/([A-Za-z0-9_.-]+)$', path)
        if m:
            self._send_file(os.path.join(STATIC_DIR, m.group(1)))
            return
        self._send_json({'error': 'not found'}, 404)

    # ---------------- POST ----------------
    def do_POST(self):
        path = self.path.split('?', 1)[0]
        try:
            with LOCK:
                data = self._read_json()

                if path == '/api/keys':
                    bits = int(data.get('bits', 1024))
                    if bits not in (512, 768, 1024, 2048):
                        raise ValueError('bits: 512/768/1024/2048')
                    SERVER.generate_keys(bits)
                    CLIENTS.clear()
                    for v in SERVER.voters:
                        CLIENTS[v] = VoterClient(v)
                    self._send_json(full_state(False))
                    return

                if path == '/api/voters':
                    name = SERVER.add_voter(str(data.get('name', '')))
                    CLIENTS[name] = VoterClient(name)
                    self._send_json(full_state(False))
                    return

                if path == '/api/client/ballot':
                    voter = str(data.get('voter', ''))
                    choice = str(data.get('choice', ''))
                    cl = client_for(voter)
                    cl.create_ballot(choice)
                    self._send_json(full_state(False))
                    return

                if path == '/api/client/blind':
                    voter = str(data.get('voter', ''))
                    n, e = SERVER.public_key()
                    if n is None:
                        raise ValueError('Сначала сгенерируйте ключи сервера')
                    cl = client_for(voter)
                    cl.do_blind(n, e)
                    self._send_json(full_state(False))
                    return

                if path == '/api/client/sign':
                    voter = str(data.get('voter', ''))
                    cl = client_for(voter)
                    resp = SERVER.blind_sign(voter, cl.blinded)   # сервер видит только m′!
                    cl.on_signed(resp['blinded_sig'])
                    self._send_json(full_state(False))
                    return

                if path == '/api/client/unblind':
                    voter = str(data.get('voter', ''))
                    n, e = SERVER.public_key()
                    cl = client_for(voter)
                    cl.do_unblind(n, e)
                    self._send_json(full_state(False))
                    return

                if path == '/api/client/cast':
                    voter = str(data.get('voter', ''))
                    cl = client_for(voter)
                    if cl.stage != 'unblinded':
                        raise ValueError('Сначала снимите ослепление и проверьте подпись (шаг 4)')
                    SERVER.cast_ballot(cl.message, cl.ballot['choice'], cl.ballot['id'], cl.signature)
                    cl.stage = 'cast'
                    self._send_json(full_state(False))
                    return

                if path == '/api/verify_all':
                    report = SERVER.verify_all()
                    self._send_json({'report': report, 'state': full_state(False)})
                    return

                if path == '/api/reset':
                    fresh_election(with_defaults=True)
                    self._send_json(full_state(False))
                    return

                self._send_json({'error': 'not found'}, 404)
        except ValueError as e:
            self._send_json({'error': str(e)}, 400)
        except Exception as e:  # noqa: BLE001
            self._send_json({'error': f'{type(e).__name__}: {e}'}, 500)


def main():
    port = 8013
    args = sys.argv[1:]
    if '--port' in args:
        port = int(args[args.index('--port') + 1])
    elif os.environ.get('PORT'):
        port = int(os.environ['PORT'])
    print('Генерация RSA-1024 ключей избирательной комиссии…')
    fresh_election(with_defaults=True)
    httpd = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    print(f'ЛР №13 «Слепая подпись» — http://127.0.0.1:{port}  (Ctrl+C для выхода)')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
