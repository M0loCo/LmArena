# -*- coding: utf-8 -*-
"""
Слепая цифровая подпись Чаума на базе RSA (Chaum, 1982).

Схема:
  Сервер (подписывающий): ключ RSA (n, e, d).
  Клиент (избиратель):
    M  = сообщение (бюллетень) в канонической форме
    H  = SHA-256(M) как целое число
    r  = случайное «ослепляющий множитель», 1 < r < n, НОД(r, n) = 1
    m' = H · r^e mod n          — ослеплённое сообщение (сервер его НЕ может прочитать)
  Сервер подписывает ослеплённое:
    s' = m'^d mod n
  Клиент снимает ослепление:
    s  = s' · r^(−1) mod n
  Тогда s^e ≡ H (mod n) — обычная RSA-подпись под H, проверяемая всеми.

Свойство слепоты: сервер видит только m'; по равномерности r величина
r^e mod n распределена равномерно в Z*_n, поэтому m' не раскрывает H.
Свойство неотслеживаемости: (m', s') на стороне сервера и (M, s) в урне
не связаны никаким публичным значением — сопоставить их может только
клиент, владеющий r.
"""
import hashlib
import secrets

E_DEFAULT = 65537


# ---------------- простые числа (Миллер–Рабин) ----------------

def is_probable_prime(n: int, rounds: int = 40) -> bool:
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


def generate_prime(bits: int) -> int:
    while True:
        c = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if is_probable_prime(c, 40):
            return c


def generate_keypair(bits: int = 1024):
    """Генерирует RSA-ключи. Возвращает (n, e, d, p, q)."""
    if bits < 512:
        raise ValueError('Минимум 512 бит')
    half = bits // 2
    while True:
        p = generate_prime(half)
        q = generate_prime(bits - half)
        if p == q:
            continue
        n = p * q
        phi = (p - 1) * (q - 1)
        if math_gcd(E_DEFAULT, phi) == 1:
            d = pow(E_DEFAULT, -1, phi)
            return n, E_DEFAULT, d, p, q


def math_gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


# ---------------- примитивы слепой подписи ----------------

def hash_message(message: str) -> int:
    """H = SHA-256(message) как целое число (младше любого разумного RSA-модуля)."""
    return int(hashlib.sha256(message.encode('utf-8')).hexdigest(), 16)


def random_blinding_factor(n: int) -> int:
    """r ∈ (1, n), НОД(r, n) = 1 — «ослепляющий множитель» (одноразовый!)."""
    while True:
        r = secrets.randbelow(n - 3) + 2
        if math_gcd(r, n) == 1:
            return r


def blind(message_int: int, e: int, n: int, r: int) -> int:
    """m' = H · r^e mod n"""
    return (message_int * pow(r, e, n)) % n


def sign_blinded(blinded: int, d: int, n: int) -> int:
    """s' = m'^d mod n"""
    if not (0 < blinded < n):
        raise ValueError('Ослеплённое сообщение вне диапазона')
    return pow(blinded, d, n)


def unblind(blinded_signature: int, r: int, n: int) -> int:
    """s = s' · r^(−1) mod n"""
    return (blinded_signature * pow(r, -1, n)) % n


def verify(signature: int, message_int: int, e: int, n: int) -> bool:
    """Проверка: s^e mod n == H"""
    return pow(signature, e, n) == message_int % n
