const $ = (selector) => document.querySelector(selector);
const kindLabels = {book: '本', image: '画像', video: '動画', audio: '音楽'};
const viewLabels = {all: 'すべて', favorites: 'お気に入り', unreviewed: '未確認', shelf: '棚に入れたもの'};
const pageSize = 60;
const numberFormat = new Intl.NumberFormat('ja-JP');
const initialParams = new URLSearchParams(location.search);
const state = {
  page: Math.max(0, Number.parseInt(initialParams.get('page') || '0', 10) || 0),
  kind: Object.hasOwn(kindLabels, initialParams.get('kind')) ? initialParams.get('kind') : '',
  view: Object.hasOwn(viewLabels, initialParams.get('view')) ? initialParams.get('view') : 'all',
  q: (initialParams.get('q') || '').slice(0, 300),
  items: [], total: 0, selected: new Set(), token: '',
  panel: null, dirty: false, saving: false
};
let listRequest = 0;
let detailRequest = 0;
let debounceTimer;
let toastTimer;
let returnFocus = null;
const narrowPanel = matchMedia('(max-width: 1180px)');

function toast(message) {
  const el = $('#toast');
  el.textContent = message;
  el.style.display = 'block';
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.style.display = 'none'; }, 3500);
}

async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-Aredoko-Token': state.token},
    body: JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) throw Error(result.error || '通信に失敗しました');
  return result;
}

function cover(item) {
  // Deterministic fictional thumbnail; never reads real user files.
  const palettes = [
    ['#304c55', '#94b8b5'], ['#4b483a', '#d0bd8a'],
    ['#443a52', '#b8a8ca'], ['#354937', '#b0c29b'], ['#593e35', '#d6ad8a']
  ];
  const [base, highlight] = palettes[item.id % palettes.length];
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="400" viewBox="0 0 320 400"><rect width="320" height="400" fill="${base}"/><circle cx="${80 + item.id % 120}" cy="140" r="90" fill="${highlight}" opacity=".26"/><path d="M0 310 L100 160 L205 300 L265 220 L320 300 V400 H0Z" fill="${highlight}" opacity=".25"/><path d="M25 25 H295 V375 H25Z" fill="none" stroke="${highlight}" opacity=".4"/><text x="42" y="62" font-family="sans-serif" font-size="10" fill="${highlight}" letter-spacing="3">AREDOKO COLLECTION</text><text x="42" y="320" font-family="serif" font-size="36" fill="${highlight}">${String(item.id).padStart(5, '0')}</text><text x="42" y="347" font-family="sans-serif" font-size="10" fill="${highlight}" letter-spacing="3">${item.kind.toUpperCase()} / DEMO</text></svg>`;
  return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
}

function syncUrl() {
  const params = new URLSearchParams();
  if (state.q) params.set('q', state.q);
  if (state.kind) params.set('kind', state.kind);
  if (state.view !== 'all') params.set('view', state.view);
  if (state.page) params.set('page', String(state.page));
  history.replaceState(null, '', location.pathname + (params.size ? '?' + params : ''));
}

function updateNavigation() {
  $('#query').value = state.q;
  $('#breadcrumb').textContent = viewLabels[state.view];
  $('#nav').querySelectorAll('[data-view]').forEach((b) => {
    const active = b.dataset.view === state.view;
    b.classList.toggle('active', active);
    b.setAttribute('aria-pressed', String(active));
  });
  $('#filters').querySelectorAll('[data-kind]').forEach((b) => {
    const active = b.dataset.kind === state.kind;
    b.classList.toggle('active', active);
    b.setAttribute('aria-pressed', String(active));
  });
}

function selection() {
  const n = state.selected.size;
  const check = $('#select-page');
  const all = state.items.length > 0 && state.items.every((item) => state.selected.has(item.id));
  check.checked = all;
  check.indeterminate = !all && n > 0;
  check.disabled = state.items.length === 0;
  $('#selected-count').textContent = `${numberFormat.format(n)}件選択`;
  $('#clear').disabled = n === 0;
  $('#bulk').disabled = n === 0;
}

function createCard(item, index) {
  const card = document.createElement('article');
  card.className = 'card';
  if (state.panel?.mode === 'single' && state.panel.ids[0] === item.id) card.classList.add('is-inspected');
  const art = document.createElement('div');
  art.className = 'art';
  const img = document.createElement('img');
  img.src = cover(item);
  img.alt = '';
  img.width = 320;
  img.height = 400;
  img.decoding = 'async';
  img.loading = index < 6 ? 'eager' : 'lazy';
  const open = document.createElement('button');
  open.type = 'button';
  open.className = 'art-open';
  open.setAttribute('aria-label', `${item.title}の詳細と編集を開く`);
  open.onclick = () => openSingle(item.id, open);
  const label = document.createElement('label');
  const check = document.createElement('input');
  check.type = 'checkbox';
  check.checked = state.selected.has(item.id);
  check.setAttribute('aria-label', `${item.title}を選択`);
  check.onchange = () => {
    if (check.checked) state.selected.add(item.id);
    else state.selected.delete(item.id);
    selection();
  };
  label.append(check);
  const badge = document.createElement('span');
  badge.className = 'media-badge';
  badge.textContent = kindLabels[item.kind];
  art.append(img, open, label, badge);
  if (item.favorite) {
    const star = document.createElement('span');
    star.className = 'star';
    star.textContent = '★';
    star.setAttribute('aria-label', 'お気に入り');
    art.append(star);
  }
  const title = document.createElement('h3');
  title.textContent = item.title;
  title.title = item.title;
  const tags = document.createElement('p');
  tags.textContent = item.tags.join(' · ') || 'タグなし';
  card.append(art, title, tags);
  return card;
}

function render() {
  const fragment = document.createDocumentFragment();
  state.items.forEach((item, index) => fragment.append(createCard(item, index)));
  if (!state.items.length) {
    const empty = document.createElement('div');
    empty.className = 'empty';
    const title = document.createElement('strong');
    title.textContent = '見つかりませんでした';
    const description = document.createElement('span');
    description.textContent = '検索語や絞り込み条件を変えてみてください。';
    const clear = document.createElement('button');
    clear.type = 'button';
    clear.textContent = '検索条件をクリア';
    clear.onclick = () => {
      if (!confirmDiscard()) return;
      closePanel(false);
      state.q = '';
      state.kind = '';
      state.view = 'all';
      reset();
    };
    empty.append(title, description, clear);
    fragment.append(empty);
  }
  $('#grid').replaceChildren(fragment);
  $('#result-count').textContent = `${numberFormat.format(state.total)} 件`;
  $('#page-info').textContent = `${numberFormat.format(state.page + 1)} / ${numberFormat.format(Math.max(1, Math.ceil(state.total / pageSize)))} ページ`;
  $('#prev').disabled = state.page === 0;
  $('#next').disabled = (state.page + 1) * pageSize >= state.total;
  selection();
}

async function load() {
  const myRequest = ++listRequest;
  const grid = $('#grid');
  grid.setAttribute('aria-busy', 'true');
  grid.classList.add('is-loading');
  $('#grid-status').hidden = true;
  try {
    const params = new URLSearchParams({q: state.q, kind: state.kind, view: state.view, page: String(state.page)});
    const data = await api('/api/items?' + params);
    if (myRequest !== listRequest) return;
    state.items = data.items;
    state.total = data.total;
    if (!state.items.length && state.page > 0) {
      state.page = Math.max(0, Math.ceil(state.total / pageSize) - 1);
      syncUrl();
      return load();
    }
    render();
  } catch (error) {
    if (myRequest !== listRequest) return;
    const status = $('#grid-status');
    status.textContent = `一覧を読み込めませんでした: ${error.message} `;
    const retry = document.createElement('button');
    retry.textContent = '再試行';
    retry.type = 'button';
    retry.onclick = load;
    status.append(retry);
    status.hidden = false;
    $('#result-count').textContent = '読み込みに失敗しました';
  } finally {
    if (myRequest === listRequest) {
      grid.setAttribute('aria-busy', 'false');
      grid.classList.remove('is-loading');
    }
  }
}

function confirmDiscard() {
  return !state.saving && (!state.dirty || confirm('未保存の変更があります。破棄して移動しますか？'));
}

function setDirty(dirty) {
  state.dirty = dirty;
  $('#save-state').textContent = dirty ? '未保存の変更があります' : '変更なし';
  $('#save-state').classList.toggle('is-dirty', dirty);
  $('#save').disabled = !dirty || state.saving;
  $('#reset-edit').disabled = !dirty || state.saving;
}

function showPanel() {
  $('#inspector').classList.add('is-open');
  if (narrowPanel.matches) {
    $('#panel-scrim').hidden = false;
    $('.sidebar').inert = true;
    $('.workspace').inert = true;
    $('#close').focus();
  }
}

function closePanel(restoreFocus = true) {
  detailRequest++;
  state.panel = null;
  state.saving = false;
  setDirty(false);
  $('#edit-form').hidden = true;
  $('#panel-empty').hidden = false;
  $('#panel-empty').querySelector('h3').textContent = 'アイテムを選択';
  $('#form-error').hidden = true;
  $('#inspector').classList.remove('is-open');
  $('#inspector').setAttribute('aria-busy', 'false');
  $('#panel-scrim').hidden = true;
  $('.sidebar').inert = false;
  $('.workspace').inert = false;
  $('#grid').querySelectorAll('.is-inspected').forEach((card) => card.classList.remove('is-inspected'));
  if (restoreFocus) (returnFocus?.isConnected ? returnFocus : $("#query")).focus();
  returnFocus = null;
}

function fillPanel() {
  const panel = state.panel;
  if (!panel) return;
  const bulk = panel.mode === 'bulk';
  const item = panel.item;
  $('#detail-cover').hidden = bulk;
  if (!bulk) $('#detail-cover').src = cover(item);
  $('#detail-kind').textContent = bulk ? '一括編集' : kindLabels[item.kind] + ' · 架空データ';
  $('#edit-title').textContent = bulk ? `${panel.ids.length}件のアイテム` : item.title;
  $('#edit-description').textContent = bulk ? 'このページで選択した項目' : `ID ${numberFormat.format(item.id).padStart(5, '0')}`;
  $('#tags').value = bulk ? '' : item.tags.join(', ');
  $('#shelf').value = bulk ? '' : item.shelf;
  $('#favorite').checked = bulk ? false : item.favorite;
  $('#reviewed').checked = bulk ? false : item.reviewed;
  $('#bulk-note').hidden = !bulk;
  if (bulk) $('#bulk-note').textContent = '注意：保存すると選択した全件のタグ・棚・お気に入り・確認済みを、この入力内容で置き換えます。空欄は消去、チェックなしは解除です。';
  $('#form-error').hidden = true;
  $('#panel-empty').hidden = true;
  $('#edit-form').hidden = false;
  $('#inspector').setAttribute('aria-busy', 'false');
  setDirty(false);
  $('#grid').querySelectorAll('.is-inspected').forEach((card) => card.classList.remove('is-inspected'));
  if (!bulk) {
    const index = state.items.findIndex((x) => x.id === item.id);
    if (index >= 0) $('#grid').children[index]?.classList.add('is-inspected');
  }
}

async function openSingle(id, trigger) {
  if (state.panel?.mode === 'single' && state.panel.ids[0] === id) { showPanel(); return; }
  if (!confirmDiscard()) return;
  returnFocus = trigger;
  const requestId = ++detailRequest;
  state.panel = {mode: 'single', ids: [id], item: null};
  $('#panel-empty').hidden = false;
  $('#panel-empty').querySelector('h3').textContent = '詳細を読み込み中…';
  $('#edit-form').hidden = true;
  $('#inspector').setAttribute('aria-busy', 'true');
  showPanel();
  setDirty(false);
  try {
    const item = await api('/api/items/' + id);
    if (requestId !== detailRequest) return;
    state.panel.item = item;
    fillPanel();
    $('#tags').focus();
  } catch (error) {
    if (requestId !== detailRequest) return;
    $('#panel-empty').querySelector('h3').textContent = '詳細を取得できませんでした';
    toast(error.message);
    $('#inspector').setAttribute('aria-busy', 'false');
  }
}

function openBulk() {
  if (!state.selected.size || !confirmDiscard()) return;
  detailRequest++;
  returnFocus = $('#bulk');
  state.panel = {mode: 'bulk', ids: [...state.selected], item: null};
  showPanel();
  fillPanel();
  $('#tags').focus();
}

function reset() {
  state.page = 0;
  state.selected.clear();
  updateNavigation();
  syncUrl();
  load();
}

$('#nav').onclick = (event) => {
  const button = event.target.closest('[data-view]');
  if (!button || button.dataset.view === state.view || !confirmDiscard()) return;
  closePanel(false);
  state.view = button.dataset.view;
  reset();
};
$('#filters').onclick = (event) => {
  const button = event.target.closest('[data-kind]');
  if (!button || button.dataset.kind === state.kind || !confirmDiscard()) return;
  closePanel(false);
  state.kind = button.dataset.kind;
  reset();
};
$('#query').oninput = () => {
  clearTimeout(debounceTimer);
  const next = $('#query').value;
  if (state.dirty && !confirmDiscard()) {
    $('#query').value = state.q;
    return;
  }
  closePanel(false);
  debounceTimer = setTimeout(() => { state.q = next; reset(); }, 220);
};
$('#prev').onclick = () => navigatePage(-1);
$('#next').onclick = () => navigatePage(1);
function navigatePage(direction) {
  if (!confirmDiscard()) return;
  closePanel(false);
  state.page += direction;
  state.selected.clear();
  syncUrl();
  load();
  window.scrollTo({top: 0, behavior: 'auto'});
}
$('#select-page').onchange = (event) => {
  state.selected.clear();
  if (event.target.checked) state.items.forEach((item) => state.selected.add(item.id));
  $('#grid').querySelectorAll('.card input[type="checkbox"]').forEach((input) => { input.checked = event.target.checked; });
  selection();
};
$('#clear').onclick = () => {
  state.selected.clear();
  $('#grid').querySelectorAll('.card input[type="checkbox"]').forEach((input) => { input.checked = false; });
  selection();
};
$('#bulk').onclick = openBulk;
$('#close').onclick = () => { if (confirmDiscard()) closePanel(); };
$('#panel-scrim').onclick = () => { if (confirmDiscard()) closePanel(); };
$('#edit-form').oninput = () => { $('#form-error').hidden = true; setDirty(true); };
$('#edit-form').onchange = () => { $('#form-error').hidden = true; setDirty(true); };
$('#reset-edit').onclick = fillPanel;
$('#edit-form').onsubmit = async (event) => {
  event.preventDefault();
  if (!state.panel || state.saving || !state.dirty) return;
  const tags = $('#tags').value.split(/[,、]/).map((t) => t.trim()).filter(Boolean);
  if (tags.length > 30 || tags.some((tag) => tag.length > 60)) {
    $('#form-error').textContent = 'タグは30個以内、1個あたり60文字以内にしてください。';
    $('#form-error').hidden = false;
    $('#tags').focus();
    return;
  }
  if ($('#shelf').value.length > 80) {
    $('#form-error').textContent = '棚の名前は80文字以内にしてください。';
    $('#form-error').hidden = false;
    $('#shelf').focus();
    return;
  }
  const changes = {
    tags, shelf: $('#shelf').value.trim(),
    favorite: $('#favorite').checked, reviewed: $('#reviewed').checked
  };
  state.saving = true;
  $('#save').textContent = '保存中…';
  $('#save').disabled = true;
  $('#reset-edit').disabled = true;
  try {
    const ids = state.panel.ids;
    await api('/api/items/update', {ids, changes});
    setDirty(false);
    if (state.panel.mode === 'single') state.panel.item = await api('/api/items/' + ids[0]);
    else state.panel = {mode: 'bulk', ids, item: null};
    state.selected.clear();
    await load();
    fillPanel();
    toast(`${numberFormat.format(ids.length)}件を保存しました`);
  } catch (error) {
    $('#form-error').textContent = `保存できませんでした: ${error.message}。入力内容を確認し、再試行してください。`;
    $('#form-error').hidden = false;
    toast('保存に失敗しました');
  } finally {
    state.saving = false;
    $('#save').textContent = '変更を保存';
    setDirty(state.dirty);
  }
};
window.addEventListener('beforeunload', (event) => {
  if (!state.dirty) return;
  event.preventDefault();
  event.returnValue = '';
});
document.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault();
    if (narrowPanel.matches && state.panel) {
      if (!confirmDiscard()) return;
      closePanel(false);
    }
    $('#query').focus();
  }
  if (event.key === 'Escape' && state.panel) {
    event.preventDefault();
    if (confirmDiscard()) closePanel();
  }
  if (event.key === 'Tab' && narrowPanel.matches && state.panel) {
    const buttons = [...$('#inspector').querySelectorAll('button:not(:disabled),input:not(:disabled),textarea:not(:disabled)')]
      .filter((el) => !el.closest('[hidden]'));
    const first = buttons[0], last = buttons.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
});
narrowPanel.addEventListener('change', () => {
  if (!state.panel) return;
  if (narrowPanel.matches) showPanel();
  else {
    $('#panel-scrim').hidden = true;
    $('.sidebar').inert = false;
    $('.workspace').inert = false;
  }
});

updateNavigation();
api('/api/session').then((session) => {
  state.token = session.token;
  $('#total').textContent = numberFormat.format(session.stats.total);
  syncUrl();
  return load();
}).catch((error) => {
  $('#grid').setAttribute('aria-busy', 'false');
  $('#result-count').textContent = '起動に失敗しました';
  const status = $('#grid-status');
  status.textContent = `デモに接続できません: ${error.message}。サーバーを起動して再読み込みしてください。`;
  status.hidden = false;
});
