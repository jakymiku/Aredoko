import React, {useState, useEffect, useCallback, useRef, useLayoutEffect} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';

const kinds = {all: 'すべて', book: '本', image: '画像', video: '動画', audio: '音楽'};
const nf = new Intl.NumberFormat('ja-JP');
async function request(url, options) {
  const response = await fetch(url, options);
  const json = await response.json();
  if (!response.ok) throw Error(json.error || `HTTP ${response.status}`);
  return json;
}

function App() {
  const [token, setToken] = useState('');
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [kind, setKind] = useState('');
  const [page, setPage] = useState(0);
  const [result, setResult] = useState({items: [], total: 0});
  const [selected, setSelected] = useState(null);
  const [tags, setTags] = useState('');
  const [shelf, setShelf] = useState('');
  const [favorite, setFavorite] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [message, setMessage] = useState('読み込み中…');
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const sequence = useRef(0);
  const latest = useRef(0);
  const [scrollTop, setScrollTop] = useState(0);
  const listRef = useRef(null);
  // Reset the DOM scroll position as well as React state when the dataset changes.
  // Otherwise the virtual window renders rows 0..N while the scroll container
  // remains at an old offset, leaving the page blank until the next scroll event.
  useLayoutEffect(() => {
    if (listRef.current) listRef.current.scrollTop = 0;
    setScrollTop(0);
  }, [page, search, kind]);
  useEffect(() => {request('/api/session').then(x => {setToken(x.token);}).catch(e => setMessage(e.message));}, []);
  // Debounce only when the query has actually changed. The previous initial
  // 220ms timer always reset page 0, racing a quick user's first Next click.
  useEffect(() => {
    if (query === search) return;
    const id = setTimeout(() => {setSearch(query);setPage(0);}, 220);
    return () => clearTimeout(id);
  }, [query, search]);
  const load = useCallback(async () => {
    const n = ++sequence.current;
    const start = performance.now();
    setMessage('検索中…');
    const params = new URLSearchParams({q: search, kind, page: String(page)});
    try {
      const data = await request('/api/items?' + params);
      if (n !== sequence.current) return;
      setResult(data); setMessage('');
      latest.current = performance.now() - start;
      window.__aredokoBench = {lastFetchMs: latest.current, count: data.total, rendered: data.items.length};
    } catch (e) {if (n === sequence.current) {setResult({items: [], total: 0}); setMessage(`読み込み失敗: ${e.message}`);}}
  }, [search, kind, page]);
  useEffect(() => {load();}, [load]);
  const openItem = async id => {
    if (dirty && !window.confirm('未保存の変更を破棄しますか？')) return;
    try {
      const data = await request('/api/items/' + id);
      setSelected(data); setTags(data.tags.join(', ')); setShelf(data.shelf);
      setFavorite(data.favorite); setReviewed(data.reviewed); setDirty(false);
    } catch (e) {setMessage(`詳細の取得に失敗: ${e.message}`);}
  };
  const save = async () => {
    if (!selected || saving || !dirty) return;
    const values = [...new Set(tags.split(/[,、]/).map(x => x.trim()).filter(Boolean))];
    if (values.length > 30 || values.some(x => x.length > 60) || shelf.length > 80) {
      setMessage('タグは30個・各60文字、棚は80文字以内にしてください。');return;
    }
    setSaving(true);
    try {
      await request('/api/items/update', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Aredoko-Token': token},
        body: JSON.stringify({ids: [selected.id], changes: {tags: values, shelf, favorite, reviewed}})});
      setDirty(false); setMessage('保存しました'); await load();
    } catch (e) {setMessage(`保存または再表示に失敗: ${e.message}`);}
    finally {setSaving(false);}
  };
  const rowHeight = 54;
  const viewport = 550;
  const startIndex = Math.max(0, Math.floor(scrollTop / rowHeight) - 4);
  const endIndex = Math.min(result.items.length, startIndex + Math.ceil(viewport / rowHeight) + 8);
  return <div className="app">
    <aside className="sidebar"><div className="brand">Aredoko</div><div className="small">比較用 · Tauri/React</div><div className="nav-title">ライブラリ</div><button className="nav active">すべての作品</button><p className="hint">ローカル架空データだけを表示。GUI方式は未決定。</p></aside>
    <main className="workspace"><header><h1>ライブラリ</h1><span className="count">{nf.format(result.total)} 件</span></header>
      <div className="toolbar"><label className="search">検索<input aria-label="作品名・タグで検索" placeholder="タイトルやタグ…" value={query} onChange={e => setQuery(e.target.value)}/></label>
      <label className="filter">種類<select aria-label="メディアの種類" value={kind} onChange={e=> {setKind(e.target.value);setPage(0);}}>{Object.entries(kinds).map(([value,label])=><option key={value} value={value === 'all' ? '' : value}>{label}</option>)}</select></label></div>
      <div className="message" role="status" aria-live="polite">{message || '60件ずつの一覧・行仮想化'}</div>
      <div className="list-heading"><span>作品</span><span>種別 / タグ</span></div>
      <div ref={listRef} className="list" aria-label="作品一覧" onScroll={e => setScrollTop(e.currentTarget.scrollTop)}>
        <div style={{height: result.items.length * rowHeight, position:'relative'}}>
          {result.items.slice(startIndex, endIndex).map((item,index) => <button type="button" key={item.id} className={'item '+(selected?.id===item.id?'chosen':'')}
            style={{position:'absolute',top:(startIndex+index)*rowHeight,left:0,right:0,height:rowHeight}} onClick={()=>openItem(item.id)}>
            <strong>{item.title}</strong><span>{kinds[item.kind]} · {item.tags.join('、')}</span></button>)}
        </div>
      </div>
      <footer><button disabled={page===0} onClick={() => setPage(p => Math.max(0, p-1))}>前へ</button><span>{page+1} / {Math.max(1,Math.ceil(result.total/60))}</span><button disabled={(page+1)*60>=result.total} onClick={() => setPage(p => p+1)}>次へ</button></footer>
    </main>
    <aside className="inspector"><h2>詳細・タグ編集</h2>{selected ? <><strong className="item-title">{selected.title}</strong><span className="small">ID {selected.id} · {kinds[selected.kind]}</span>
      <label>タグ（カンマ区切り）<textarea value={tags} onChange={e=>{setTags(e.target.value);setDirty(true);}}/></label>
      <label>棚<input value={shelf} onChange={e=>{setShelf(e.target.value);setDirty(true);}}/></label>
      <label className="check"><input type="checkbox" checked={favorite} onChange={e=>{setFavorite(e.target.checked);setDirty(true);}}/> お気に入り</label>
      <label className="check"><input type="checkbox" checked={reviewed} onChange={e=>{setReviewed(e.target.checked);setDirty(true);}}/> 確認済み</label>
      <button className="primary" disabled={!dirty||saving||!token} onClick={save}>{saving?'保存中…':'変更を保存'}</button>
      </> : <p className="hint">一覧の作品を選択すると、ここでタグを編集できます。</p>}</aside>
  </div>;
}

createRoot(document.getElementById('root')).render(<App/>);
