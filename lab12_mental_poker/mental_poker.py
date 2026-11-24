# -*- coding: utf-8 -*-
"""
Ментальный покер по протоколу Shamir–Rivest–Adleman (SRA, 1978).

Идея: коммутативное шифрование на модульной степени.
  Каждый игрок i выбирает секретную пару (e_i, d_i) mod (p-1),
  где p — большое простое число (безопасное простое: p = 2q + 1, q — простое),
  НОД(e_i, p-1) = 1, d_i = e_i^{-1} mod (p-1).
  Шифрование карты m:  c = m^e mod p.
  Т.к. степени складываются в показателе: m^{e1·e2} = (m^{e1})^{e2},
  игроки шифруют колоду по очереди — порядок не важен,
  расшифровка в обратном (любом) порядке тем же свойством коммутирует.

Честность: колоду перемешивает КАЖДЫЙ игрок (Фишер–Йетс) своей случайностью,
значит, пока хотя бы один игрок честен, итоговый порядок никто не знает
и никто не может его подтасовать.

Скрытость: карту можно вскрыть только совместным применением d_i ВСЕХ игроков
(n из n, пороговая расшифровка). Пока этого не сделано — карта информационно
скрыта (при корректном выборе p).
"""
import hashlib
import secrets
import random
from holdem import make_deck


# ---------------------------------------------------------------- простые числа

def is_probable_prime(n: int, rounds: int = 48) -> bool:
    """Тест Миллера–Рабина (детерминирован для общих целей с 48 раундами)."""
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d = n - 1
    r = 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def generate_safe_prime(bits: int = 512):
    """Генерирует безопасное простое p = 2q + 1 (q — простое), p длиной ~bits бит."""
    if bits < 64:
        raise ValueError('bits должно быть не меньше 64')
    q_bits = bits - 1
    while True:
        q = secrets.randbits(q_bits) | (1 << (q_bits - 1)) | 1
        if not is_probable_prime(q, 32):
            continue
        p = 2 * q + 1
        if p.bit_length() <= bits and is_probable_prime(p, 32):
            return p, q


def random_coprime_exponent(p: int, max_bits: int = 31) -> int:
    """Случайное нечётное e < p-1 с НОД(e, p-1) = 1 (для p = 2q+1 это e ≠ q и нечётное)."""
    while True:
        e = secrets.randbelow(1 << max_bits) | 1
        if e < 3:
            continue
        if math_gcd(e, p - 1) == 1:   # для p-1 = 2q эквивалентно «e нечётно и e ≠ q»
            return e


def math_gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


# ---------------------------------------------------------------- протокол

class PlayerCrypto:
    def __init__(self, name: str, p: int):
        self.name = name
        self.p = p
        self.e = random_coprime_exponent(p)
        self.d = pow(self.e, -1, p - 1)

    def public_dict(self):
        return {'name': self.name, 'e': str(self.e)}


def card_encoding(index: int, deck_label: str, p: int, salt: int = 0) -> int:
    """Детерминированное публичное кодирование карты числом из (2, p-1).

    Кодировка берётся КАК КВАДРАТ: m = h² mod p. Тогда все открытые тексты —
    квадратичные вычеты, символ Лежандра любого шифртекста равен 1, и классическая
    атака на схему SRA (угадывание карты по признаку квадратичной вычетности,
    т.к. (m^e / p) = (m / p)^e = (m / p) при нечётном e) ничего не даёт.
    Знание открытого текста само по себе не ослабляет схему: инвертировать
    x ↦ x^e mod p без d_i нельзя.
    """
    digest = hashlib.sha256(f'mental-poker|{deck_label}|{index}|{salt}'.encode('utf-8')).hexdigest()
    h = int(digest, 16) % (p - 3) + 2
    return pow(h, 2, p)


class MentalPokerProtocol:
    """Полный протокол: генерация параметров → шифрование → тасовка → вскрытие."""

    def __init__(self, player_names, deck_size: int = 52, p_bits: int = 512):
        self.deck_size = deck_size
        self.deck_label = f'{deck_size}-cards'
        self.p_bits = p_bits
        self.transcript = []   # список шагов протокола (для наглядного вывода)
        self._log('Инициализация',
                  f'Игроков: {len(player_names)}; колода: {deck_size} карт; '
                  f'генерируем безопасное простое p = 2q + 1 ({p_bits} бит)…')
        self.p, self.q = generate_safe_prime(p_bits)
        self._log('Параметры поля', f'p = {self.p}\nq = (p-1)/2 = {self.q}\nφ(p) = p-1 = {self.p - 1}')

        self.deck = make_deck(deck_size)          # Card в исходном порядке
        encs, seen = [], set()
        for i in range(len(self.deck)):
            salt = 0
            while True:
                e_enc = card_encoding(i, self.deck_label, self.p, salt)
                if e_enc not in seen and e_enc > 1:
                    seen.add(e_enc)
                    encs.append(e_enc)
                    break
                salt += 1
        self.encodings = encs

        self.players = [PlayerCrypto(name, self.p) for name in player_names]
        for pl in self.players:
            self._log(f'Ключи игрока {pl.name}',
                      f'e = {pl.e}\nd = e^(-1) mod (p-1) = {pl.d}')

        # шифрование колоды каждым игроком по очереди
        self.encrypted = list(self.encodings)
        for pl in self.players:
            self.encrypted = [pow(c, pl.e, self.p) for c in self.encrypted]
            self._log(f'{pl.name} зашифровал колоду',
                      f'c_j ← c_j^e mod p для всех {len(self.encrypted)} карт. '
                      f'Пример: c₀ = {self._short(self.encrypted[0])}')

        # перемешивание каждым игроком (Фишер–Йетс, системная энтропия)
        rng = random.SystemRandom()
        for pl in self.players:
            perm = list(range(len(self.encrypted)))
            rng.shuffle(perm)
            self.encrypted = [self.encrypted[i] for i in perm]
            self._log(f'{pl.name} перетасовал колоду',
                      'Случайная перестановка (Фишер–Йетс) зашифрованной колоды. '
                      'Порядок знает только он и никто другой.')

        # соответствие «зашифрованное число → карта» для вскрытия
        self._enc_to_index = {}

    def _log(self, title, details):
        self.transcript.append({'step': len(self.transcript) + 1, 'title': title, 'details': details})

    @staticmethod
    def _short(x: int, head: int = 36) -> str:
        s = str(x)
        return s if len(s) <= head else f'{s[:head]}… ({len(s)} цифр)'

    def encrypted_card_preview(self, pos: int):
        return self._short(self.encrypted[pos], 48)

    def joint_decrypt(self, pos: int):
        """Совместное вскрытие карты в позиции pos. Возвращает (Card, шаги расшифровки)."""
        c = self.encrypted[pos]
        steps = [{'actor': 'начало', 'value': str(c), 'note': 'зашифрованная карта'}]
        acc = c
        for pl in self.players:
            acc = pow(acc, pl.d, self.p)
            steps.append({'actor': pl.name, 'value': str(acc), 'note': f'применён d игрока {pl.name}'})
        encoding = acc
        try:
            idx = self.encodings.index(encoding)
        except ValueError:
            raise RuntimeError('Совместная расшифровка не дала кодировку карты — сбой протокола')
        card = self.deck[idx]
        steps.append({'actor': 'итог', 'value': f'{encoding} → {card.label}', 'note': 'карта вскрыта'})
        self._log(f'Вскрытие карты в позиции {pos}',
                  'Последовательно применены d всех игроков: ' + ' → '.join(pl.name for pl in self.players) +
                  f'. Итог: {card.label}')
        return card, steps
