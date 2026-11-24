# -*- coding: utf-8 -*-
"""Модульные тесты ЛР №12. Запуск: python3 test_lab12.py"""
import random
import sys

from mental_poker import (is_probable_prime, generate_safe_prime, MentalPokerProtocol,
                          card_encoding, math_gcd)
from holdem import (make_deck, Card, evaluate5, evaluate7, winners_of,
                    CAT_STRAIGHT_FLUSH, CAT_QUADS, CAT_FULL_HOUSE, CAT_PAIR)
from game import Game

PASS = []
FAIL = []


def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(('✓' if cond else '✗'), name)


def test_small_primes():
    for n in (2, 3, 5, 7, 97, 7919, 104729):
        assert is_probable_prime(n), n
    for n in (1, 4, 9, 100, 221, 561):   # 561 — псевдопростое по Ферма, но не простое
        assert not is_probable_prime(n), n
    print('✓ Miller–Rabin small primes')


def test_safe_prime():
    p, q = generate_safe_prime(96)
    check('safe prime: p = 2q + 1', p == 2 * q + 1)
    check('safe prime: p простое', is_probable_prime(p))
    check('safe prime: q простое', is_probable_prime(q))


def test_protocol_roundtrip_256():
    random.seed(42)
    proto = MentalPokerProtocol(['Алиса', 'Боб'], deck_size=36, p_bits=256)
    # шифртексты — перестановка группы: все разные
    check('кодировки уникальны', len(set(proto.encodings)) == len(proto.encodings))
    check('шифртексты уникальны', len(set(proto.encrypted)) == len(proto.encrypted))
    # все шифртексты — квадратичные вычеты (атака Лежандра нейтрализована)
    legendre = [pow(c, (proto.p - 1) // 2, proto.p) for c in proto.encrypted]
    check('все шифртексты — квадратичные вычеты (Лежандр = 1)', all(l == 1 for l in legendre))
    # совместное вскрытие всех позиций даёт ровно колоду без повторов
    cards = [proto.joint_decrypt(pos)[0].label for pos in range(36)]
    check('вскрыто 36 карт без повторов', len(set(cards)) == 36)


def test_encoding_quadratic_residue():
    p, q = generate_safe_prime(96)
    m = card_encoding(0, '36-cards', p, 0)
    check('кодировка — квадрат по модулю p', pow(m, (p - 1) // 2, p) == 1)


def test_game_flow():
    g = Game()
    g.new_game(['Алиса', 'Боб', 'Чарли'], deck_size=36, p_bits=256)
    g.deal()
    g.community_stage('flop')
    g.community_stage('turn')
    g.community_stage('river')
    out = g.showdown()
    names = [p['name'] for p in out['players']]
    check('все игроки получили карты', all(p['hole'] for p in out['players']))
    check('на столе 5 карт', len(out['community']) == 5)
    check('победитель определён', out['winners'] and len(out['winners']) >= 1)
    check('детали по всем игрокам', len(out['details']) == 3)


def test_evaluator():
    # стрит-флеш бьёт каре, каре бьёт фулл-хаус
    sf = [Card(9, 0), Card(10, 0), Card(11, 0), Card(12, 0), Card(13, 0), Card(2, 1), Card(3, 2)]
    quads = [Card(9, 0), Card(9, 1), Card(9, 2), Card(9, 3), Card(12, 0), Card(2, 1), Card(3, 2)]
    boat = [Card(9, 0), Card(9, 1), Card(9, 2), Card(12, 0), Card(12, 1), Card(3, 2), Card(4, 3)]
    k_sf, _ = evaluate7(sf)
    k_q, _ = evaluate7(quads)
    k_b, _ = evaluate7(boat)
    check('категория стрит-флеш', k_sf[0] == CAT_STRAIGHT_FLUSH)
    check('категория каре', k_q[0] == CAT_QUADS)
    check('категория фулл-хаус', k_b[0] == CAT_FULL_HOUSE)
    check('стрит-флеш > каре > фулл-хаус', k_sf > k_q > k_b)
    # колесо A-2-3-4-5
    wheel = [Card(14, 0), Card(2, 1), Card(3, 2), Card(4, 3), Card(5, 0), Card(9, 1), Card(11, 2)]
    k_w, _ = evaluate7(wheel)
    check('колесо — стрит до 5', k_w[0] == 4 and k_w[1] == 5)
    # пары сравнение
    p1 = evaluate5([Card(5, 0), Card(5, 1), Card(9, 2), Card(12, 3), Card(14, 0)])
    p2 = evaluate5([Card(3, 0), Card(3, 1), Card(9, 2), Card(12, 3), Card(14, 0)])
    check('пара пятёрок > пары троек', p1 > p2 and p1[0] == CAT_PAIR)
    # tie: основные примеры победителей
    w_map, winners = winners_of([
        ('A', sf), ('B', quads),
    ])
    check('победитель стрит-флеш против каре', winners == ['A'])


def test_dealer_rotation():
    """Колода из 52 карт на 6 игроков: 12 + 5 = 17 карт, хватает."""
    g = Game()
    g.new_game(['A', 'B', 'C', 'D', 'E', 'F'], deck_size=52, p_bits=256)
    g.deal()
    g.community_stage('flop'); g.community_stage('turn'); g.community_stage('river')
    out = g.showdown()
    check('6 игроков, 52 карты — игра завершилась', out['phase'] == 'showdown')


if __name__ == '__main__':
    test_small_primes()
    test_safe_prime()
    test_protocol_roundtrip_256()
    test_encoding_quadratic_residue()
    test_game_flow()
    test_evaluator()
    test_dealer_rotation()
    print()
    print(f'Итого: {len(PASS)} passed, {len(FAIL)} failed')
    sys.exit(1 if FAIL else 0)
