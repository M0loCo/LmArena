# -*- coding: utf-8 -*-
"""Модульные тесты ЛР №13. Запуск: python3 test_lab13.py"""
import sys

from blind_rsa import (generate_keypair, hash_message, random_blinding_factor,
                       blind, sign_blinded, unblind, verify)
from election import ElectionServer, VoterClient, new_ballot, ballot_message, BALLOT_TAG, CHOICES

PASS, FAIL = [], []


def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(('✓' if cond else '✗'), name)


def test_blind_roundtrip():
    n, e, d, p, q = generate_keypair(512)
    msg = f'{BALLOT_TAG}|id=deadbeef1234|choice=Да'
    H = hash_message(msg)
    r = random_blinding_factor(n)
    m_blind = blind(H, e, n, r)
    check('ослепление меняет число', m_blind != H)
    s_prime = sign_blinded(m_blind, d, n)
    s = unblind(s_prime, r, n)
    check('снятая подпись проверяется открытым ключом', verify(s, H, e, n))
    check('итоговая подпись ≠ ослеплённая подпись', s != s_prime)


def test_tampered_rejected():
    n, e, d, _, _ = generate_keypair(512)
    msg = f'{BALLOT_TAG}|id=deadbeef1234|choice=Да'
    H = hash_message(msg)
    r = random_blinding_factor(n)
    s = unblind(sign_blinded(blind(H, e, n, r), d, n), r, n)
    H_fake = hash_message(f'{BALLOT_TAG}|id=deadbeef1234|choice=Нет')
    check('подмена выбора ломает проверку', not verify(s, H_fake, e, n))


def test_full_election_flow():
    srv = ElectionServer()
    srv.generate_keys(512)
    for v in ('Алиса', 'Боб', 'Чарли', 'Диана'):
        srv.add_voter(v)
    choices = {'Алиса': 'Да', 'Боб': 'Нет', 'Чарли': 'Воздержался'}
    for voter, choice in choices.items():
        cl = VoterClient(voter)
        cl.create_ballot(choice)
        cl.do_blind(srv.n, srv.e)
        resp = srv.blind_sign(voter, cl.blinded)
        cl.on_signed(resp['blinded_sig'])
        cl.do_unblind(srv.n, srv.e)
        srv.cast_ballot(cl.message, cl.ballot['choice'], cl.ballot['id'], cl.signature)
        cl.stage = 'cast'
    res = srv.results()
    check('3 бюллетеня в урне', res['total'] == 3)
    check('3 подписи выдано', res['issued'] == 3)
    check('подсчитано верно', res['counts'] == {'Да': 1, 'Нет': 1, 'Воздержался': 1})
    check('все подписи валидны', all(b['valid'] for b in srv.verify_all()))
    # Диана не голосовала — явка 75%
    check('явка 75%', abs(res['turnout_pct'] - 75.0) < 0.01)


def test_double_vote_protection():
    srv = ElectionServer()
    srv.generate_keys(512)
    srv.add_voter('Алиса')
    cl = VoterClient('Алиса')
    cl.create_ballot('Да')
    cl.do_blind(srv.n, srv.e)
    srv.blind_sign('Алиса', cl.blinded)
    try:
        srv.blind_sign('Алиса', cl.blinded)
        check('повторная выдача отклонена', False)
    except ValueError:
        check('повторная выдача отклонена', True)


def test_double_cast_protection():
    srv = ElectionServer()
    srv.generate_keys(512)
    srv.add_voter('Алиса')
    cl = VoterClient('Алиса')
    cl.create_ballot('Да')
    cl.do_blind(srv.n, srv.e)
    resp = srv.blind_sign('Алиса', cl.blinded)
    cl.on_signed(resp['blinded_sig'])
    cl.do_unblind(srv.n, srv.e)
    srv.cast_ballot(cl.message, cl.ballot['choice'], cl.ballot['id'], cl.signature)
    try:
        srv.cast_ballot(cl.message, cl.ballot['choice'], cl.ballot['id'], cl.signature)
        check('повторный вброс отклонён', False)
    except ValueError:
        check('повторный вброс отклонён', True)


def test_fake_ballot_rejected():
    srv = ElectionServer()
    srv.generate_keys(512)
    srv.add_voter('Алиса')
    cl = VoterClient('Алиса')
    cl.create_ballot('Да')
    cl.do_blind(srv.n, srv.e)
    resp = srv.blind_sign('Алиса', cl.blinded)
    cl.on_signed(resp['blinded_sig'])
    cl.do_unblind(srv.n, srv.e)
    forged = dict(cl.ballot)
    try:
        srv.cast_ballot(ballot_message({**forged, 'choice': 'Нет'}), 'Нет', forged['id'], cl.signature)
        check('подделанный бюллетень отклонён', False)
    except ValueError:
        check('подделанный бюллетень отклонён', True)


def test_unlinkability_display():
    """В журнале выдачи и в урне нет общего публичного значения (кроме случайностей)."""
    srv = ElectionServer()
    srv.generate_keys(512)
    srv.add_voter('Алиса')
    cl = VoterClient('Алиса')
    cl.create_ballot('Да')
    cl.do_blind(srv.n, srv.e)
    resp = srv.blind_sign('Алиса', cl.blinded)
    cl.on_signed(resp['blinded_sig'])
    cl.do_unblind(srv.n, srv.e)
    srv.cast_ballot(cl.message, cl.ballot['choice'], cl.ballot['id'], cl.signature)
    iss = srv.issuance_log[0]
    box = srv.ballot_box[0]
    check('m′ не встречается в урне', str(cl.blinded) not in (box['message'], box['signature']))
    check('s′ не встречается в урне', str(cl.blinded_sig) != box['signature'])
    check('H вычислим из M, но не связан с m′ публично', hash_message(cl.message) == int(box['hash'], 16))


if __name__ == '__main__':
    test_blind_roundtrip()
    test_tampered_rejected()
    test_full_election_flow()
    test_double_vote_protection()
    test_double_cast_protection()
    test_fake_ballot_rejected()
    test_unlinkability_display()
    print()
    print(f'Итого: {len(PASS)} passed, {len(FAIL)} failed')
    sys.exit(1 if FAIL else 0)
