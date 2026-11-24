'use strict';

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

let state = { phase: 'idle', players: [], community: [], transcript: [], protocol: null };

const PHASE_NAMES = {
  idle: 'Ожидание', ready: 'Ключи готовы — раздача', dealt: 'Карты розданы',
  flop: 'Флоп', turn: 'Тёрн', river: 'Ривер', showdown: 'Вскрытие',
};

// ---------------- утилиты ----------------

async function api(path, body) {
  const opts = body === undefined
    ? {}
    : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  const resp = await fetch(path, opts);
  const data = await resp.json().catch(() => ({ error: 'Сервер вернул не-JSON' }));
  if (!resp.ok) throw new Error(data.error || `Ошибка ${resp.status}`);
  return data;
}

function showError(el, msg) { el.textContent = msg; el.classList.remove('hidden'); }
function clearError(el) { el.textContent = ''; el.classList.add('hidden'); }

function cardHTML(card) {
  if (!card) return '<div class="card slot"></div>';
  const red = card.color === 'red' ? ' red' : '';
  const suit = ['♠', '♥', '♦', '♣'][card.suit];
  const label = { 11: 'J', 12: 'Q', 13: 'K', 14: 'A' }[card.rank] || String(card.rank);
  return `<div class="card${red}">
      <div class="rank">${label}<br>${suit}</div>
      <div class="suit-big">${suit}</div>
      <div class="rank corner">${label}<br>${suit}</div>
    </div>`;
}
const cardBack = () => '<div class="card back">♠</div>';

// ---------------- рендер ----------------

function render() {
  const inGame = state.phase !== 'idle';
  $('#setup-panel').classList.toggle('hidden', inGame);
  $('#poker-table').classList.toggle('hidden', !inGame);
  if (!inGame) return;

  $('#phase-badge').textContent = PHASE_NAMES[state.phase] || state.phase;
  $('#deck-info').textContent = state.protocol
    ? `Колода: ${state.protocol.deck_size} карт · p: ${state.protocol.p_bits} бит · безопасное простое p = 2q + 1`
    : '';

  // стол: 5 слотов, вскрытые карты
  const community = [...state.community];
  let comm = '';
  for (let i = 0; i < 5; i++) comm += cardHTML(community[i] || null);
  $('#community-row').innerHTML = comm;

  // игроки
  const showdown = state.phase === 'showdown';
  const winners = state.winners || [];
  const detailMap = {};
  (state.details || []).forEach(d => { detailMap[d.name] = d; });
  $('#players-area').innerHTML = state.players.map((p, i) => {
    let hole = '';
    if (showdown && p.hole) {
      hole = p.hole.map(cardHTML).join('');
    } else if (p.hole_count > 0) {
      hole = cardBack() + cardBack();
    }
    const detail = showdown && detailMap[p.name] ? detailMap[p.name] : null;
    const handLine = detail ? `${detail.hand} · лучшие 5: ${detail.cards.join(' ')}` : (p.hole_count ? 'карты закрыты' : '');
    const winCls = winners.includes(p.name) ? ' winner' : '';
    return `<div class="player${winCls}">
        <div class="seat-tag">МЕСТО ${i + 1}</div>
        <div class="player-name">${escapeHtml(p.name)}</div>
        <div class="player-hand">${escapeHtml(handLine)}</div>
        <div class="hole-row">${hole}</div>
      </div>`;
  }).join('');

  // баннер результата
  const banner = $('#result-banner');
  if (showdown && winners.length) {
    banner.classList.remove('hidden');
    const names = winners.map(escapeHtml).join(', ');
    const hand = detailMap[winners[0]] ? detailMap[winners[0]].hand : '';
    banner.innerHTML = (winners.length > 1
      ? `🤝 Ничья: ${names}`
      : `🏆 Победитель: ${names}`) + `<small>${escapeHtml(hand)}</small>`;
  } else {
    banner.classList.add('hidden');
  }

  // кнопки по фазам
  const vis = {
    '#btn-deal': state.phase === 'ready',
    '#btn-flop': state.phase === 'dealt',
    '#btn-turn': state.phase === 'flop',
    '#btn-river': state.phase === 'turn',
    '#btn-showdown': state.phase === 'river',
  };
  for (const [sel, show] of Object.entries(vis)) $(sel).classList.toggle('hidden', !show);

  renderProtocol();
}

function renderProtocol() {
  const proto = state.protocol;
  $('#params-box').innerHTML = proto
    ? `<b>Открытые параметры</b>\np = ${proto.p}\nq = (p−1)/2 = ${proto.q}\n\n` +
      `<b>Игроки и их открытые ключи eᵢ</b>\n` +
      proto.players.map(pl => `${pl.name}: e = ${pl.e}`).join('\n') +
      `\n\n<b>Кодировки первых карт (h² mod p)</b>\n` + proto.encodings_sample.join('\n') +
      `\n\n<b>Колода после шифрования всеми игроками и тасовки (первые 8 из ${proto.cards_count})</b>\n` +
      proto.encrypted_deck.slice(0, 8).map((c, i) => `c${i} = ${c}`).join('\n')
    : 'Параметры ещё не сгенерированы.';

  $('#transcript').innerHTML = (state.transcript || []).map(s =>
    `<li class="tstep"><div class="t-title"><span class="t-num">${s.step}</span>${escapeHtml(s.title)}</div><div class="t-body">${escapeHtml(s.details)}</div></li>`
  ).join('');
  const box = $('#transcript');
  box.scrollTop = box.scrollHeight;
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

// ---------------- действия ----------------

const loading = (on, text) => {
  $('#table-loading').classList.toggle('hidden', !on);
  if (text) $('#table-loading-text').textContent = text;
  clearError($('#table-error'));
};

async function refresh() {
  state = await api('/api/state');
  render();
}

async function doAction(path, body, loadingText) {
  loading(true, loadingText);
  try {
    state = await api(path, body);
    render();
  } catch (e) {
    showError($('#table-error'), e.message);
  } finally {
    loading(false);
  }
}

// ---------------- настройка ----------------

const setupCount = $('#setup-count');
for (let n = 2; n <= 6; n++) {
  const o = document.createElement('option');
  o.value = n; o.textContent = String(n);
  if (n === 2) o.selected = true;
  setupCount.appendChild(o);
}
function defaultName(i) { return ['Алиса', 'Боб', 'Чарли', 'Диана', 'Ева', 'Фрэнк'][i] || `Игрок ${i + 1}`; }
function renderNameInputs() {
  const n = Number(setupCount.value);
  const deck = Number($('#setup-deck').value);
  const maxByDeck = deck === 36 ? 5 : 6;
  if (n > maxByDeck) { setupCount.value = maxByDeck; }
  const count = Math.min(Number(setupCount.value), maxByDeck);
  $('#setup-names').innerHTML = Array.from({ length: count }, (_, i) =>
    `<input type="text" class="player-name-input" maxlength="24" value="${defaultName(i)}" placeholder="Имя игрока ${i + 1}">`
  ).join('');
}
setupCount.addEventListener('change', renderNameInputs);
$('#setup-deck').addEventListener('change', renderNameInputs);
renderNameInputs();

$('#btn-start').addEventListener('click', async () => {
  clearError($('#setup-error'));
  $('#setup-loading').classList.remove('hidden');
  $('#btn-start').disabled = true;
  try {
    const players = $$('.player-name-input').map(i => i.value);
    state = await api('/api/new_game', {
      players,
      deck_size: Number($('#setup-deck').value),
      p_bits: Number($('#setup-bits').value),
    });
    render();
  } catch (e) {
    showError($('#setup-error'), e.message);
  } finally {
    $('#setup-loading').classList.add('hidden');
    $('#btn-start').disabled = false;
  }
});

$('#btn-new-game').addEventListener('click', async () => {
  await api('/api/reset', {});
  await refresh();
});
$('#btn-deal').addEventListener('click', () => doAction('/api/deal', {}, 'Совместная расшифровка закрытых карт…'));
$('#btn-flop').addEventListener('click', () => doAction('/api/community', { stage: 'flop' }, 'Вскрытие флопа…'));
$('#btn-turn').addEventListener('click', () => doAction('/api/community', { stage: 'turn' }, 'Вскрытие тёрна…'));
$('#btn-river').addEventListener('click', () => doAction('/api/community', { stage: 'river' }, 'Вскрытие ривера…'));
$('#btn-showdown').addEventListener('click', () => doAction('/api/showdown', {}, 'Вскрытие карт игроков…'));

// секреты dᵢ
$('#toggle-secrets').addEventListener('change', async (ev) => {
  if (!ev.target.checked) { renderProtocol(); return; }
  try {
    const secrets = await api('/api/secrets');
    const box = $('#params-box');
    const lines = (secrets.players || []).map(pl => `${pl.name}: e = ${pl.e}\n   d = ${pl.d}  ← секрет`).join('\n');
    box.innerHTML = `<b>СЕКРЕТНЫЕ КЛЮЧИ (только для демонстрации преподавателю!)</b>\n${escapeHtml(lines)}\n\n<b>Открытые параметры</b>\np = ${secrets.p}\nq = ${secrets.q}`;
  } catch (e) { /* нет игры — просто перерисуем */ renderProtocol(); }
});

// модалка теории
$('#btn-theory').addEventListener('click', () => $('#theory-modal').classList.remove('hidden'));
$('#btn-close-theory').addEventListener('click', () => $('#theory-modal').classList.add('hidden'));
$('#theory-modal').addEventListener('click', (e) => { if (e.target.id === 'theory-modal') e.currentTarget.classList.add('hidden'); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') $('#theory-modal').classList.add('hidden'); });

refresh();
