'use strict';

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

let state = null;
let selectedVoter = null;
let selectedChoice = 'Да';

const STAGE_ORDER = ['idle', 'ballot', 'blinded', 'signed', 'unblinded', 'cast'];

// ---------------- API ----------------

async function api(path, body) {
  const opts = body === undefined
    ? {}
    : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  const resp = await fetch(path, opts);
  const data = await resp.json().catch(() => ({ error: 'Сервер вернул не-JSON' }));
  if (!resp.ok) throw new Error(data.error || `Ошибка ${resp.status}`);
  return data;
}
const showErr = (sel, msg) => { const el = $(sel); el.textContent = msg; el.classList.remove('hidden'); };
const hideErr = (sel) => $(sel).classList.add('hidden');

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}
const short = (s, n = 44) => (s && s.length > n ? s.slice(0, n) + '…' : s || '—');

// ---------------- рендер ----------------

function currentClient() {
  return state && state.clients ? state.clients[selectedVoter] : null;
}

function render() {
  if (!state) return;
  // выбор избирателя
  const sel = $('#voter-select');
  const prev = sel.value || selectedVoter;
  sel.innerHTML = state.voters.map(v => `<option value="${escapeHtml(v.name)}">${escapeHtml(v.name)}${v.issued ? ' — уже голосовал' : ''}</option>`).join('');
  selectedVoter = state.voters.some(v => v.name === prev) ? prev : (state.voters[0] && state.voters[0].name);
  if (selectedVoter) sel.value = selectedVoter;

  const cl = currentClient();
  const stage = cl ? cl.stage : 'idle';

  // кнопки шагов по стадии
  $('#step1').disabled = !selectedVoter;
  $('#step2').disabled = stage !== 'ballot';
  $('#step3').disabled = stage !== 'blinded';
  $('#step4').disabled = stage !== 'signed';
  $('#step5').disabled = stage !== 'unblinded';

  // клиентские числа
  $('#cn-ballot').textContent = cl && cl.ballot ? JSON.stringify(cl.ballot, null, 1) : '—';
  $('#cn-message').textContent = (cl && cl.message) || '—';
  $('#cn-h').textContent = (cl && cl.H) || '—';
  $('#cn-r').textContent = (cl && cl.r) || '— (показывается только до сброса)';
  $('#cn-blinded').textContent = (cl && cl.blinded) || '—';
  $('#cn-bsig').textContent = (cl && cl.blinded_sig) || '—';
  $('#cn-sig').textContent = (cl && cl.signature) || '—';

  // серверные ключи
  $('#key-bits-badge').textContent = state.keys_generated ? `RSA-${state.key_bits}` : 'ключи не сгенерированы';
  $('#sn-n').textContent = state.n || '—';
  $('#sn-e').textContent = state.e || '—';
  $('#sn-d').textContent = state.d || 'скрыт (нажмите «показать d»)';

  // реестр
  $('#voter-list').innerHTML = state.voters.map(v =>
    `<li class="voter${v.issued ? ' voted' : ''}"><span class="dot"></span><span>${escapeHtml(v.name)}</span><span class="st">${v.issued ? 'подпись выдана' : 'не голосовал'}</span></li>`
  ).join('');

  // журнал выдачи
  const ilog = $('#issuance-log');
  ilog.innerHTML = state.issuance_log.length
    ? state.issuance_log.map((it, i) =>
        `<div class="log-item"><b>#${i + 1} · ${escapeHtml(it.voter)}</b> получил подпись<br>m′ = <span class="sig">${escapeHtml(short(it.blinded, 120))}</span><br>s′ = <span class="sig">${escapeHtml(short(it.blinded_sig, 120))}</span></div>`).join('')
    : '<div class="empty">Подписей ещё не выдано</div>';

  // урна
  const bbox = $('#ballot-box');
  bbox.innerHTML = state.ballot_box.length
    ? state.ballot_box.map((b, i) =>
        `<div class="ballot-item"><b>#${i + 1}</b><span class="choice-pill choice-${escapeHtml(b.choice)}">${escapeHtml(b.choice)}</span><small>id ${escapeHtml(b.id)} · подпись ${b.valid ? '✔ верна' : '✘ НЕВЕРНА'} · избиратель: <b>неизвестен</b></small></div>`).join('')
    : '<div class="empty">Урна пуста</div>';

  // отклонённые
  const rej = $('#rejected-box');
  rej.innerHTML = state.rejected.length
    ? state.rejected.map((r, i) => `<div class="log-item bad"><b>✘ #${i + 1}</b> ${escapeHtml(r.reason)}<br><small>${escapeHtml(short(r.message, 120))}</small></div>`).join('')
    : '<div class="empty">Нет отклонённых</div>';

  // итоги
  const res = state.results;
  const maxCount = Math.max(1, ...Object.values(res.counts));
  $('#tally').innerHTML = Object.entries(res.counts).map(([choice, count]) => {
    const pct = res.total ? Math.round(1000 * count / res.total) / 10 : 0;
    const width = Math.round(100 * count / maxCount);
    return `<div class="tally-row"><div class="tally-name">${escapeHtml(choice.toUpperCase())}</div>
      <div class="bar bar-${escapeHtml(choice)}"><div class="bar-fill" style="width:${width}%"></div></div>
      <div class="tally-num">${count} · ${pct}%</div></div>`;
  }).join('');
  $('#tally-meta').innerHTML =
    `Бюллетеней в урне: <b>${res.total}</b> · подписей выдано: <b>${res.issued}</b> из ${res.registered} зарегистрированных · явка: <b>${res.turnout_pct}%</b> · бюллетеней отклонено: <b>${state.rejected.length}</b>`;
}

async function refresh() {
  try {
    state = await api('/api/state');
    hideErr('#client-error'); hideErr('#server-error');
    render();
  } catch (e) {
    showErr('#server-error', e.message);
  }
}

async function act(path, body, errSel) {
  try {
    state = await api(path, body);
    hideErr(errSel || '#client-error');
    render();
  } catch (e) {
    showErr(errSel || '#client-error', e.message);
  }
}

// ---------------- события ----------------

$('#voter-select').addEventListener('change', (ev) => { selectedVoter = ev.target.value; render(); });
$$('#choice-group .choice').forEach(btn => btn.addEventListener('click', () => {
  selectedChoice = btn.dataset.choice;
  $$('#choice-group .choice').forEach(b => b.classList.toggle('selected', b === btn));
}));

$('#add-voter-form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const input = $('#add-voter-name');
  const name = input.value.trim();
  if (!name) return;
  await act('/api/voters', { name }, '#server-error');
  input.value = '';
  if (state && state.voters.some(v => v.name === name)) selectedVoter = name;
  render();
});

$('#step1').addEventListener('click', () => act('/api/client/ballot', { voter: selectedVoter, choice: selectedChoice }));
$('#step2').addEventListener('click', () => act('/api/client/blind', { voter: selectedVoter }));
$('#step3').addEventListener('click', () => act('/api/client/sign', { voter: selectedVoter }));
$('#step4').addEventListener('click', () => act('/api/client/unblind', { voter: selectedVoter }));
$('#step5').addEventListener('click', () => act('/api/client/cast', { voter: selectedVoter }));

$('#btn-keys').addEventListener('click', async () => {
  const bits = Number($('#key-bits').value);
  await act('/api/keys', { bits }, '#server-error');
});
$('#toggle-server-secrets').addEventListener('change', async (ev) => {
  if (ev.target.checked) {
    try {
      const sec = await api('/api/secrets');
      $('#sn-d').textContent = sec.d || '—';
      $('#sn-d-row').classList.remove('hidden');
    } catch (e) { showErr('#server-error', e.message); }
  } else {
    $('#sn-d-row').classList.add('hidden');
  }
});
$('#btn-verify-all').addEventListener('click', async () => {
  try {
    const data = await api('/api/verify_all', {});
    state = data.state;
    render();
    hideErr('#server-error');
  } catch (e) { showErr('#server-error', e.message); }
});
$('#btn-reset').addEventListener('click', () => act('/api/reset', {}, '#server-error'));

refresh();
