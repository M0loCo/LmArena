# -*- coding: utf-8 -*-
"""
ЛР №13 — Слепая подпись на базе системы анонимного голосования.

Разделение сторон (логическое, как требует задание):
  ElectionServer («избирательная комиссия»):
      генерирует RSA-ключи, регистрирует избирателей, выдаёт кредит подписи
      (ровно один на избирателя, чтобы исключить повторное голосование),
      подписывает ОСЛЕПЛЁННЫЕ бюллетени, принимает бюллетени в «урну»
      через анонимный канал, проверяет подписи и считает голоса.
  VoterClient («избиратель»):
      формирует бюллетень ({Да, Нет, Воздержался}), ослепляет его своим
      одноразовым r, передаёт ослеплённое значение серверу, снимает
      ослепление с полученной подписи, отправляет бюллетень в урну.

Сервер НИКОГДА не видит выбор избирателя до урны, а в урне бюллетень уже
не связан с тем, кто и когда получил подпись.
"""
import json
import secrets
import uuid
from collections import Counter

from blind_rsa import (generate_keypair, hash_message, random_blinding_factor,
                       blind, sign_blinded, unblind, verify)

BALLOT_TAG = 'BLIND-BALLOT-v1'        # домен-сепарация: сервер подписывает только бюллетени этой формы
CHOICES = ['Да', 'Нет', 'Воздержался']


def ballot_message(ballot) -> str:
    """Каноническая строка, которая хешируется и подписывается."""
    return f'{BALLOT_TAG}|id={ballot["id"]}|choice={ballot["choice"]}'


def new_ballot(choice: str) -> dict:
    if choice not in CHOICES:
        raise ValueError(f'Недопустимый выбор: {choice!r}. Допустимо: {CHOICES}')
    # 12 hex = 48 бит энтропии для id — достаточно для учебной урны и наглядно
    return {'id': secrets.token_hex(6), 'choice': choice, 'tag': BALLOT_TAG}


# =================================================================
#                        СЕРВЕРНАЯ ЧАСТЬ
# =================================================================
class ElectionServer:
    """Избирательная комиссия: ключи, реестр избирателей, выдача подписей, урна."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.n = self.e = self.d = None
        self.key_bits = None
        # реестр: имя -> {'issued': bool, 'issued_blinded': str|None}
        self.voters = {}
        self.issuance_log = []   # [{voter, blinded, blinded_sig}] — «кто получал подпись»
        self.ballot_box = []     # [{id, choice, message, signature, valid}] — анонимная урна
        self.rejected = []       # отклонённые бюллетени (дубликат или неверная подпись)

    # ---------- ключи ----------
    def generate_keys(self, bits: int = 1024):
        self.n, self.e, self.d, _, _ = generate_keypair(bits)
        self.key_bits = bits
        return {'n': str(self.n), 'e': str(self.e), 'bits': bits}

    def public_key(self):
        return (self.n, self.e) if self.n else (None, None)

    # ---------- реестр ----------
    def add_voter(self, name: str):
        name = (name or '').strip()
        if not name:
            raise ValueError('Имя избирателя пустое')
        if name in self.voters:
            raise ValueError(f'Избиратель «{name}» уже в реестре')
        if len(self.voters) >= 50:
            raise ValueError('Слишком много избирателей для демонстрации')
        self.voters[name] = {'issued': False, 'issued_blinded': None}
        return name

    # ---------- выдача слепой подписи ----------
    def blind_sign(self, voter: str, blinded_int: int) -> dict:
        if self.n is None:
            raise ValueError('Сначала сгенерируйте ключи сервера')
        if voter not in self.voters:
            raise ValueError(f'Избиратель «{voter}» не зарегистрирован')
        rec = self.voters[voter]
        if rec['issued']:
            # повторная выдача = попытка двойного голосования
            raise ValueError(f'Избиратель «{voter}» уже получил подпись — повторная выдача отклонена')
        s_prime = sign_blinded(int(blinded_int), self.d, self.n)
        rec['issued'] = True
        rec['issued_blinded'] = str(blinded_int)
        self.issuance_log.append({'voter': voter, 'blinded': str(blinded_int), 'blinded_sig': str(s_prime)})
        return {'blinded_sig': str(s_prime)}

    # ---------- урна ----------
    def cast_ballot(self, message: str, choice: str, ballot_id: str, signature_int: int) -> dict:
        if self.n is None:
            raise ValueError('Сначала сгенерируйте ключи сервера')
        # 1. формат и домен-сепарация
        try:
            tag, id_part, choice_part = message.split('|')
        except ValueError:
            self.rejected.append({'message': message, 'reason': 'некорректный формат бюллетеня'})
            raise ValueError('Некорректный формат бюллетеня')
        ballot_id_check = id_part.split('=', 1)[1] if id_part.startswith('id=') else None
        choice_check = choice_part.split('=', 1)[1] if choice_part.startswith('choice=') else None
        if tag != BALLOT_TAG or ballot_id_check != ballot_id or choice_check != choice or choice not in CHOICES:
            self.rejected.append({'message': message, 'reason': 'нарушение формата или домен-сепарации'})
            raise ValueError('Бюллетень не прошёл проверку формата')
        # 2. подпись
        h = hash_message(message)
        if not verify(int(signature_int), h, self.e, self.n):
            self.rejected.append({'message': message, 'reason': 'неверная подпись'})
            raise ValueError('Подпись неверна — бюллетень отклонён')
        # 3. анти-дубликат по id (независимо от подписи)
        if any(b['id'] == ballot_id for b in self.ballot_box):
            self.rejected.append({'message': message, 'reason': 'дубликат бюллетеня'})
            raise ValueError('Такой бюллетень уже в урне (дубликат) — отклонён')
        entry = {'id': ballot_id, 'choice': choice, 'message': message,
                 'signature': str(signature_int), 'hash': format(h, 'x'), 'valid': True}
        self.ballot_box.append(entry)
        return entry

    def verify_all(self) -> list:
        out = []
        for b in self.ballot_box:
            ok = verify(int(b['signature']), hash_message(b['message']), self.e, self.n)
            b['valid'] = ok
            out.append({'id': b['id'], 'choice': b['choice'], 'valid': ok})
        return out

    def results(self) -> dict:
        counts = Counter(b['choice'] for b in self.ballot_box)
        total = sum(counts.values())
        return {
            'counts': {c: counts.get(c, 0) for c in CHOICES},
            'total': total,
            'issued': len(self.issuance_log),
            'registered': len(self.voters),
            'turnout_pct': round(100.0 * len(self.issuance_log) / len(self.voters), 1) if self.voters else 0.0,
        }

    def state(self, include_secrets: bool = False) -> dict:
        d = {
            'keys_generated': self.n is not None,
            'key_bits': self.key_bits,
            'n': str(self.n) if self.n else None,
            'e': str(self.e) if self.n else None,
            'd': str(self.d) if (self.n and include_secrets) else None,
            'voters': [{'name': v, 'issued': rec['issued']} for v, rec in self.voters.items()],
            'issuance_log': self.issuance_log,
            'ballot_box': self.ballot_box,
            'rejected': self.rejected,
            'results': self.results(),
            'choices': CHOICES,
        }
        return d


# =================================================================
#                        КЛИЕНТСКАЯ ЧАСТЬ
# =================================================================
class VoterClient:
    """Избиратель: бюллетень → ослепление → обработка ответа → урна."""

    def __init__(self, voter: str):
        self.voter = voter
        self.reset()

    def reset(self):
        self.ballot = None       # {'id','choice','tag'}
        self.message = None      # каноническая строка
        self.H = None            # SHA-256(message) как int
        self.r = None            # ослепляющий множитель (секрет клиента)
        self.blinded = None      # m'
        self.blinded_sig = None  # s'
        self.signature = None    # s (итоговая подпись)
        self.stage = 'idle'      # idle → ballot → blinded → signed → unblinded → cast

    # шаг 1: сформировать бюллетень
    def create_ballot(self, choice: str) -> dict:
        self.reset()
        self.ballot = new_ballot(choice)
        self.message = ballot_message(self.ballot)
        self.H = hash_message(self.message)
        self.stage = 'ballot'
        return self._view()

    # шаг 2: ослепить
    def do_blind(self, n: int, e: int) -> dict:
        if self.stage != 'ballot':
            raise ValueError('Сначала сформируйте бюллетень (шаг 1)')
        self.r = random_blinding_factor(n)
        self.blinded = blind(self.H, e, n, self.r)
        self.stage = 'blinded'
        return self._view()

    # шаг 3: получение подписи у сервера (выполняется сервером; клиент передаёт только m')
    def on_signed(self, blinded_sig_str: str) -> dict:
        if self.stage != 'blinded':
            raise ValueError('Сначала ослепите бюллетень (шаг 2)')
        self.blinded_sig = int(blinded_sig_str)
        self.stage = 'signed'
        return self._view()

    # шаг 4: снять ослепление и проверить подпись локально
    def do_unblind(self, n: int, e: int) -> dict:
        if self.stage != 'signed':
            raise ValueError('Сначала получите подпись сервера (шаг 3)')
        self.signature = unblind(self.blinded_sig, self.r, n)
        ok = verify(self.signature, self.H, e, n)
        if not ok:
            raise ValueError('Локальная проверка не сошлась — подпись некорректна')
        self.stage = 'unblinded'
        return self._view()

    def _view(self, include_secrets: bool = True) -> dict:
        return {
            'voter': self.voter,
            'stage': self.stage,
            'ballot': self.ballot,
            'message': self.message,
            'H': format(self.H, 'x') if self.H is not None else None,
            'r': str(self.r) if (self.r is not None and include_secrets) else None,
            'blinded': str(self.blinded) if self.blinded is not None else None,
            'blinded_sig': str(self.blinded_sig) if self.blinded_sig is not None else None,
            'signature': str(self.signature) if self.signature is not None else None,
        }
