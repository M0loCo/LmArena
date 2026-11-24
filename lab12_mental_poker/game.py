# -*- coding: utf-8 -*-
"""Игровой движок: связывает протокол ментального покера и правила холдема."""
import threading
from mental_poker import MentalPokerProtocol
from holdem import evaluate7, winners_of, make_deck


class Game:
    def __init__(self):
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        self.protocol = None
        self.deck_size = None
        self.player_names = []
        self.hole = []            # [ [Card, Card], ... ] — у каждого игрока по 2
        self.community = []       # вскрытые общие карты
        self.phase = 'idle'       # idle -> ready -> dealt -> flop -> turn -> river -> showdown
        self.winners = None
        self.details = None
        self.reveal_steps = []    # журнал вскрытий (шаги совместной расшифровки), последнее вскрытие

    # ---------------- действия ----------------

    def new_game(self, player_names, deck_size=52, p_bits=512):
        with self.lock:
            self.reset()
            names = [n.strip() for n in player_names if n and n.strip()]
            if not (2 <= len(names) <= 6):
                raise ValueError('Количество игроков должно быть от 2 до 6')
            if len({n.lower() for n in names}) != len(names):
                raise ValueError('Имена игроков должны быть уникальными')
            if deck_size not in (36, 52):
                raise ValueError('Колода: 36 или 52 карты')
            if deck_size == 36 and len(names) > 5:
                raise ValueError('36-карточной колоды хватает максимум на 5 игроков (10 карт + 5 на стол)')
            self.player_names = names
            self.deck_size = deck_size
            self.protocol = MentalPokerProtocol(names, deck_size=deck_size, p_bits=p_bits)
            self.phase = 'ready'
            return self.state_dict(include_secrets=False)

    def deal(self):
        with self.lock:
            self._require_phase('ready')
            n = len(self.player_names)
            self.hole = [[None, None] for _ in range(n)]
            pos = 0
            for i in range(2):                      # по кругу, как в покере: по одной карте за круг
                for p in range(n):
                    card, steps = self.protocol.joint_decrypt(pos)
                    self.reveal_steps.append({'who': self.player_names[p], 'card': card.label, 'steps': steps})
                    self.hole[p][i] = card
                    pos += 1
            self.phase = 'dealt'
            return self.state_dict(include_secrets=False)

    def community_stage(self, stage):
        with self.lock:
            order = {'flop': ('dealt', 3), 'turn': ('flop', 1), 'river': ('turn', 1)}
            if stage not in order:
                raise ValueError('Неизвестный этап')
            prev, count = order[stage]
            self._require_phase(prev)
            n = len(self.player_names)
            pos = 2 * n + len(self.community)
            for _ in range(count):
                card, steps = self.protocol.joint_decrypt(pos)
                self.community.append(card)
                self.reveal_steps.append({'who': 'стол', 'card': card.label, 'steps': steps})
                pos += 1
            self.phase = stage
            return self.state_dict(include_secrets=False)

    def showdown(self):
        with self.lock:
            self._require_phase('river')
            hands = []
            for i, name in enumerate(self.player_names):
                cards7 = list(self.hole[i]) + list(self.community)
                hands.append((name, cards7))
            detail_map, winners = winners_of(hands)
            self.details = [
                {'name': d['name'],
                 'hand': d['hand'],
                 'cards': [c.label for c in d['best5']],
                 'key': list(d['key'])}
                for d in detail_map.values()
            ]
            self.winners = winners
            self.phase = 'showdown'
            return self.state_dict(include_secrets=False)

    # ---------------- состояние для клиента ----------------

    def state_dict(self, include_secrets=False):
        d = {
            'phase': self.phase,
            'deck_size': self.deck_size,
            'players': [],
            'community': [c.to_dict() for c in self.community],
            'winners': self.winners,
            'details': self.details,
            'transcript': self.protocol.transcript if self.protocol else [],
        }
        for i, name in enumerate(self.player_names):
            show_hole = self.phase == 'showdown'
            d['players'].append({
                'name': name,
                'hole': [c.to_dict() for c in self.hole[i]] if (show_hole and self.hole and self.hole[i][0]) else None,
                'hole_count': 2 if self.phase != 'idle' and self.phase != 'ready' else 0,
            })
        if self.protocol:
            proto = {
                'p': str(self.protocol.p),
                'q': str(self.protocol.q),
                'p_bits': self.protocol.p_bits,
                'deck_size': self.protocol.deck_size,
                'encodings_sample': [str(x) for x in self.protocol.encodings[:4]],
                'encrypted_deck': [self.protocol._short(c, 44) for c in self.protocol.encrypted],
                'cards_count': len(self.protocol.encrypted),
                'players': [],
            }
            for pl in self.protocol.players:
                entry = {'name': pl.name, 'e': str(pl.e)}
                if include_secrets:
                    entry['d'] = str(pl.d)
                proto['players'].append(entry)
            d['protocol'] = proto
        return d

    def _require_phase(self, expected):
        if self.phase != expected:
            raise ValueError(f'Недопустимое действие в фазе «{self.phase}» (ожидалось «{expected}»)')
