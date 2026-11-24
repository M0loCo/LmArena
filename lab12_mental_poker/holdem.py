# -*- coding: utf-8 -*-
"""
Игровая логика Техасского холдема: карты, колода, оценка силы руки.

Оценка руки считается перебором всех C(7,5) = 21 пятёрок из семи карт —
это O(21) элементарных проверок, что надёжнее и проще формализуется,
чем табличные схемы, и полностью корректно для произвольной колоды.
"""
from itertools import combinations
from collections import Counter

# масти: 0 - пики, 1 - червы, 2 - бубны, 3 - трефы
SUIT_SYMBOLS = ['♠', '♥', '♦', '♣']
SUIT_NAMES = ['пики', 'червы', 'бубны', 'трефы']
SUIT_COLORS = ['black', 'red', 'red', 'black']

RANK_LABELS = {2: '2', 3: '3', 4: '4', 5: '5', 6: '6', 7: '7', 8: '8', 9: '9',
               10: '10', 11: 'J', 12: 'Q', 13: 'K', 14: 'A'}
RANK_NAMES_RU = {2: 'двойка', 3: 'тройка', 4: 'четвёрка', 5: 'пятёрка', 6: 'шестёрка',
                 7: 'семёрка', 8: 'восьмёрка', 9: 'девятка', 10: 'десятка',
                 11: 'валет', 12: 'дама', 13: 'король', 14: 'туз'}

# категории комбинаций (больше — лучше)
CAT_HIGH_CARD = 0
CAT_PAIR = 1
CAT_TWO_PAIR = 2
CAT_TRIPS = 3
CAT_STRAIGHT = 4
CAT_FLUSH = 5
CAT_FULL_HOUSE = 6
CAT_QUADS = 7
CAT_STRAIGHT_FLUSH = 8

CATEGORY_NAMES_RU = {
    CAT_HIGH_CARD: 'Старшая карта',
    CAT_PAIR: 'Пара',
    CAT_TWO_PAIR: 'Две пары',
    CAT_TRIPS: 'Тройка',
    CAT_STRAIGHT: 'Стрит',
    CAT_FLUSH: 'Флеш',
    CAT_FULL_HOUSE: 'Фулл-хаус',
    CAT_QUADS: 'Каре',
    CAT_STRAIGHT_FLUSH: 'Стрит-флеш',
}


class Card:
    """Игральная карта. rank: 2..14 (11=J, 12=Q, 13=K, 14=A), suit: 0..3."""

    __slots__ = ('rank', 'suit')

    def __init__(self, rank: int, suit: int):
        if rank < 2 or rank > 14 or suit < 0 or suit > 3:
            raise ValueError('Некорректная карта')
        self.rank = rank
        self.suit = suit

    @property
    def label(self):
        return RANK_LABELS[self.rank] + SUIT_SYMBOLS[self.suit]

    @property
    def color(self):
        return SUIT_COLORS[self.suit]

    def to_dict(self):
        return {'rank': self.rank, 'suit': self.suit, 'label': self.label, 'color': self.color}

    @staticmethod
    def from_dict(d):
        return Card(d['rank'], d['suit'])

    def __eq__(self, other):
        return isinstance(other, Card) and (self.rank, self.suit) == (other.rank, other.suit)

    def __hash__(self):
        return hash((self.rank, self.suit))

    def __repr__(self):
        return self.label


def make_deck(deck_size: int = 52):
    """Собирает колоду. 52 карты — классика, 36 карт — ранги 6..A."""
    if deck_size == 52:
        ranks = range(2, 15)
    elif deck_size == 36:
        ranks = range(6, 15)
    else:
        raise ValueError('Поддерживаются колоды 36 и 52 карты')
    return [Card(r, s) for s in range(4) for r in ranks]


def _straight_high(unique_desc):
    """unique_desc — уникальные ранги по убыванию (5 штук). Возвращает старший ранг стрита или None."""
    if len(unique_desc) != 5:
        return None
    if unique_desc[0] - unique_desc[4] == 4:
        return unique_desc[0]
    # «колесо» A-2-3-4-5
    if unique_desc == [14, 5, 4, 3, 2]:
        return 5
    return None


def evaluate5(cards):
    """Оценивает пятёрку карт. Возвращает сравнимый ключ (больше — сильнее)."""
    assert len(cards) == 5
    ranks = sorted((c.rank for c in cards), reverse=True)
    flush = len({c.suit for c in cards}) == 1
    straight = _straight_high(sorted(set(ranks), reverse=True))

    counts = Counter(ranks)
    # группы по (частота, ранг), по убыванию
    groups = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)

    if straight and flush:
        return (CAT_STRAIGHT_FLUSH, straight)
    if groups[0][1] == 4:
        quad = groups[0][0]
        kicker = groups[1][0]
        return (CAT_QUADS, quad, kicker)
    if groups[0][1] == 3 and groups[1][1] == 2:
        trip = groups[0][0]
        pair = groups[1][0]
        return (CAT_FULL_HOUSE, trip, pair)
    if flush:
        return (CAT_FLUSH, *ranks)
    if straight:
        return (CAT_STRAIGHT, straight)
    if groups[0][1] == 3:
        trip = groups[0][0]
        kickers = sorted((r for r in ranks if r != trip), reverse=True)
        return (CAT_TRIPS, trip, *kickers)
    if groups[0][1] == 2 and groups[1][1] == 2:
        p1, p2 = groups[0][0], groups[1][0]
        hi, lo = max(p1, p2), min(p1, p2)
        kicker = groups[2][0]
        return (CAT_TWO_PAIR, hi, lo, kicker)
    if groups[0][1] == 2:
        pair = groups[0][0]
        kickers = sorted((r for r in ranks if r != pair), reverse=True)
        return (CAT_PAIR, pair, *kickers)
    return (CAT_HIGH_CARD, *ranks)


def evaluate7(cards):
    """Лучшая пятёрка из 7 карт. Возвращает (ключ, лучшая_пятёрка)."""
    assert len(cards) >= 5
    best_key, best_combo = None, None
    for combo in combinations(cards, 5):
        key = evaluate5(combo)
        if best_key is None or key > best_key:
            best_key, best_combo = key, combo
    return best_key, list(best_combo)


def hand_name(key):
    return CATEGORY_NAMES_RU[key[0]]


def describe_key(key):
    """Человекочитаемое пояснение комбинации, напр. «Пара валетов»."""
    cat = key[0]
    if cat == CAT_STRAIGHT_FLUSH:
        return f'Стрит-флеш до {RANK_NAMES_RU[key[1]] if key[1] != 14 else "туза"}а'
    if cat == CAT_QUADS:
        return f'Каре {RANK_NAMES_RU[key[1]]}ей' if False else f'Каре ({RANK_LABELS[key[1]]})'
    if cat == CAT_FULL_HOUSE:
        return f'Фулл-хаус: {RANK_LABELS[key[1]]} над {RANK_LABELS[key[2]]}'
    if cat == CAT_FLUSH:
        return 'Флеш'
    if cat == CAT_STRAIGHT:
        return f'Стрит до {RANK_LABELS[key[1]]}'
    if cat == CAT_TRIPS:
        return f'Тройка ({RANK_LABELS[key[1]]})'
    if cat == CAT_TWO_PAIR:
        return f'Две пары: {RANK_LABELS[key[1]]} и {RANK_LABELS[key[2]]}'
    if cat == CAT_PAIR:
        return f'Пара ({RANK_LABELS[key[1]]})'
    return 'Старшая карта'


def winners_of(players_hands):
    """
    players_hands: list[(player_name, [Card]*7)]
    Возвращает (winning_keys dict name->key, list победителей, детали).
    Ничья — делится банк.
    """
    details = []
    for name, cards in players_hands:
        key, best5 = evaluate7(cards)
        details.append({'name': name, 'key': key, 'best5': best5, 'hand': hand_name(key)})
    best = max(d['key'] for d in details)
    winners = [d['name'] for d in details if d['key'] == best]
    return {d['name']: d for d in details}, winners
