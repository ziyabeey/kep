'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const storage = {
  read(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } },
  write(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { showToast('Tarayıcı kaydı kapalı; seçimlerin bu oturumda kalacak.'); } },
  remove(key) { try { localStorage.removeItem(key); } catch { /* Private-mode storage can be unavailable. */ } },
};
const fallbackCategories = [
  {id: 'discover', label: 'Keşif', color: '#169a87'},
  {id: 'food', label: 'Yemek', color: '#cc7a43'},
  {id: 'events', label: 'Etkinlik', color: '#8b6cc1'},
  {id: 'services', label: 'Hizmet', color: '#596c60'},
];
const validModes = ['balanced', 'roam', 'work', 'silent'];
// Camera extent for the Istanbul overview; this is not an administrative boundary.
const istanbulExtent = {west: 27.95, south: 40.75, east: 30.02, north: 41.62};
const storedProfile = storage.read('kep.preview.profile', {});
const profile = {
  name: typeof storedProfile.name === 'string' && storedProfile.name.trim() ? storedProfile.name.slice(0, 40) : 'Ziya',
  mode: validModes.includes(storedProfile.mode) ? storedProfile.mode : 'balanced',
};
const state = {
  categories: fallbackCategories,
  filters: {category: 'discover', place_category: null, radius_km: 1, open_now: false, quiet: false, budget: null, mode: profile.mode},
  selected: [], meta: null, ready: false,
  origin: {lat: 41.02563232, lon: 28.97415319},
  center: {lat: 41.02563232, lon: 28.97415319},
  zoom: 9, mapView: 'istanbul', streets: true, activeId: null,
  requestVersion: 0, abort: null, mapFrame: null,
};
let toastTimer;
function showToast(text) {
  const toast = $('#toast'); toast.textContent = text; toast.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { toast.hidden = true; }, 3800);
}
function element(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}
async function api(path, payload, signal) {
  const response = await fetch(path, payload === undefined ? {signal} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload), signal,
  });
  let result;
  try { result = await response.json(); } catch { throw new Error('Kep yanıtını okuyamadı. Biraz sonra tekrar dene.'); }
  if (!response.ok) {
    const message = typeof result.error === 'string' ? result.error : result.error?.message || result.message;
    throw new Error(message || 'İstek tamamlanamadı. Girdilerini kontrol edip tekrar dene.');
  }
  return result;
}
function currentCategory() { return state.categories.find(c => c.id === state.filters.category) || fallbackCategories[0]; }
function setTheme() {
  const category = currentCategory();
  const color = /^#[a-f\d]{6}$/i.test(category.color || '') ? category.color : fallbackCategories.find(c => c.id === category.id)?.color || '#169a87';
  const rgb = [1, 3, 5].map(start => parseInt(color.slice(start, start + 2), 16));
  document.documentElement.style.setProperty('--accent', color);
  document.documentElement.style.setProperty('--accent-rgb', rgb.join(','));
  document.documentElement.style.setProperty('--soft', `rgba(${rgb.join(',')},.07)`);
  $$('[data-category]').forEach(button => {
    const active = button.dataset.category === state.filters.category;
    button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active));
  });
}
function syncFilters() {
  $('#radius').value = String(state.filters.radius_km);
  if (!$('#radius').value) {
    const option = element('option', '', `Galata · ${state.filters.radius_km} km`);
    option.value = String(state.filters.radius_km); $('#radius').append(option); $('#radius').value = option.value;
  }
  $('#open-now').checked = !!state.filters.open_now;
  $('#budget').value = state.filters.budget ?? '';
  $('#quiet').checked = !!state.filters.quiet;
  const moreCount = Number(state.filters.budget !== null) + Number(state.filters.quiet);
  $('#open-filters').firstChild.textContent = moreCount ? `Filtreler (${moreCount}) ` : 'Filtreler ';
  setTheme();
}
function applyResponse(response, updateFilters = true) {
  $('#results-list').setAttribute('aria-busy', 'false');
  if (!response.decision) {
    state.selected = []; state.activeId = null; renderMap();
    $('#results-title').textContent = 'İsteğini netleştirelim';
    $('#result-count').textContent = 'Yeni sonuç yok';
    $('#result-context').textContent = 'Bu mesaj için keşif sorgusu çalıştırılmadı.';
    const box = element('div', 'empty-card');
    box.append(element('strong', '', 'Biraz daha bilgi gerekiyor.'), element('p', '', response.reply || 'İsteğini daha açık yazar mısın?'));
    if (response.interpretation?.route_to === 'plan') {
      const button = element('button', '', 'Gün taslağını aç'); button.type = 'button';
      button.addEventListener('click', () => { renderPlan(); openDialog('plan-dialog'); }); box.append(button);
    }
    $('#results-list').replaceChildren(box); return;
  }
  if (updateFilters && response.query) {
    for (const key of ['category', 'place_category', 'radius_km', 'open_now', 'quiet', 'budget', 'mode']) {
      if (Object.hasOwn(response.query, key)) state.filters[key] = response.query[key];
    }
  }
  state.selected = Array.isArray(response.decision.selected) ? response.decision.selected : [];
  state.activeId = null;
  syncFilters(); renderResults(response); renderMap();
}
async function discover() {
  if (!state.ready) return;
  const version = ++state.requestVersion;
  state.abort?.abort(); state.abort = new AbortController();
  $('#results-list').setAttribute('aria-busy', 'true');
  $('#result-context').textContent = 'Koşulların kontrol ediliyor…';
  try {
    const response = await api('/api/discover', {...state.filters}, state.abort.signal);
    if (version !== state.requestVersion) return;
    applyResponse(response);
  } catch (error) {
    if (error.name !== 'AbortError' && version === state.requestVersion) {
      state.selected = []; renderMap();
      renderError(error.message); showToast(error.message);
    }
  } finally {
    if (version === state.requestVersion) $('#results-list').setAttribute('aria-busy', 'false');
  }
}
function chooseCategory(id) {
  if (!state.categories.some(c => c.id === id) || (id === state.filters.category && !state.filters.place_category)) return;
  state.filters.category = id; state.filters.place_category = null; syncFilters(); discover();
}
function distanceText(distance) {
  if (!Number.isFinite(distance)) return 'Mesafe bilinmiyor';
  return distance < 1 ? `${Math.round(distance * 1000)} m` : `${distance.toLocaleString('tr-TR', {maximumFractionDigits: 1})} km`;
}
function renderResults(response) {
  const list = $('#results-list'); list.replaceChildren();
  const names = {discover: 'Yakınındaki yerler', food: 'Yemek keşfi', events: 'Etkinlik keşfi', services: 'Yakındaki hizmetler'};
  const subtypeNames = {museum: 'Yakındaki müzeler', restaurant: 'Yakındaki restoranlar', cafe: 'Yakındaki kafeler'};
  $('#results-title').textContent = subtypeNames[state.filters.place_category] || names[state.filters.category] || 'Yakınındaki yerler';
  $('#result-count').textContent = `${state.selected.length} kayıt`;
  $('#result-context').textContent = response.reply || 'Kaynak kaydı · Güncel durum teyitli değil.';
  if (!state.selected.length) {
    const box = element('div', 'empty-card');
    const refresh = ['REFRESH', 'CLARIFY'].includes(response.decision.action);
    box.append(element('strong', '', refresh ? 'Bu koşul için bilgi eksik.' : 'Bu görünümde henüz kayıt yok.'));
    box.append(element('p', '', response.reply || 'Araştırma kataloğunda bu koşulları karşılayan bir kayıt bulunamadı.'));
    if (state.filters.category !== 'discover') {
      const button = element('button', '', 'Keşif haritasına dön'); button.type = 'button'; button.addEventListener('click', () => chooseCategory('discover')); box.append(button);
    } else if (state.filters.open_now || state.filters.budget !== null || state.filters.quiet || state.filters.place_category) {
      const button = element('button', '', 'Koşulları temizle'); button.type = 'button'; button.addEventListener('click', resetFilters); box.append(button);
    }
    list.append(box); return;
  }
  state.selected.forEach((place, index) => {
    const card = element('button', 'place-card'); card.type = 'button'; card.dataset.placeId = place.id;
    card.setAttribute('aria-label', `${place.name}, ${distanceText(place.distance_km)} kuş uçuşu. Kaynak bilgilerini aç.`);
    card.append(element('span', 'place-number', String(index + 1).padStart(2, '0')));
    const copy = element('div', 'place-copy'); copy.append(element('strong', '', place.name));
    copy.append(element('p', '', `${distanceText(place.distance_km)} · Kuş uçuşu`));
    copy.append(element('small', '', 'Kaynak kaydı · Güncel durum teyitsiz'));
    card.append(copy, element('span', 'place-arrow', '↗'));
    card.addEventListener('click', () => showPlace(place)); list.append(card);
  });
}
function renderError(message) {
  $('#result-count').textContent = 'Bağlantı yok';
  $('#result-context').textContent = message;
  const box = element('div', 'empty-card'); box.append(element('strong', '', 'Kep’e ulaşamadık.'), element('p', '', message));
  const retry = element('button', '', 'Tekrar dene'); retry.addEventListener('click', () => state.ready ? discover() : bootstrap()); box.append(retry);
  $('#results-list').replaceChildren(box);
}
function resetFilters() {
  Object.assign(state.filters, {place_category: null, radius_km: 1, open_now: false, quiet: false, budget: null}); syncFilters(); discover();
}

// The map projects actual source coordinates. No invented street or coastline geometry.
function project(lat, lon, zoom = state.zoom) {
  const size = 256 * 2 ** zoom;
  const safeLat = Math.max(-85.05112878, Math.min(85.05112878, lat));
  return {x: (lon + 180) / 360 * size, y: (1 - Math.asinh(Math.tan(safeLat * Math.PI / 180)) / Math.PI) / 2 * size};
}
function unproject(x, y, zoom = state.zoom) {
  const size = 256 * 2 ** zoom;
  return {lon: x / size * 360 - 180, lat: Math.atan(Math.sinh(Math.PI * (1 - 2 * y / size))) * 180 / Math.PI};
}
const tileNodes = new Map();
const failedTiles = new Set();
function mapPadding() {
  return matchMedia('(max-width: 700px)').matches
    ? {top: 205, right: 76, bottom: 100, left: 28}
    : {top: 110, right: 80, bottom: 120, left: 24};
}
function fitMapExtent(extent, maxZoom = 19) {
  const canvas = $('#map-canvas'), padding = mapPadding();
  const width = canvas.clientWidth, height = canvas.clientHeight;
  if (!width || !height) return;
  const northwest = project(extent.north, extent.west, 0);
  const southeast = project(extent.south, extent.east, 0);
  const availableWidth = Math.max(64, width - padding.left - padding.right);
  const availableHeight = Math.max(64, height - padding.top - padding.bottom);
  const ratio = Math.min(availableWidth / Math.max(southeast.x - northwest.x, .00001),
    availableHeight / Math.max(southeast.y - northwest.y, .00001));
  state.zoom = Math.max(7, Math.min(maxZoom, Math.floor(Math.log2(ratio))));
  const scale = 2 ** state.zoom;
  state.center = unproject((northwest.x + southeast.x) / 2 * scale + (padding.right - padding.left) / 2,
    (northwest.y + southeast.y) / 2 * scale + (padding.bottom - padding.top) / 2);
}
function focusPlaces(places) {
  const coordinates = places.filter(place => Number.isFinite(place.lat) && Number.isFinite(place.lon));
  const points = coordinates.length ? coordinates : [state.origin];
  state.mapView = 'free';
  fitMapExtent({west: Math.min(...points.map(p => p.lon)), east: Math.max(...points.map(p => p.lon)),
    south: Math.min(...points.map(p => p.lat)), north: Math.max(...points.map(p => p.lat))},
  points.length > 1 ? 19 : 18);
  renderMap();
}
function clampMapCenter(center) {
  return {lat: Math.max(istanbulExtent.south, Math.min(istanbulExtent.north, center.lat)),
    lon: Math.max(istanbulExtent.west, Math.min(istanbulExtent.east, center.lon))};
}
function updateMapStatus() {
  const tiles = [...tileNodes.values()];
  const failed = tiles.filter(img => img.dataset.loadState === 'error').length;
  const loading = tiles.some(img => img.dataset.loadState === 'loading');
  const loaded = tiles.some(img => img.dataset.loadState === 'loaded');
  $('#map-feedback').hidden = !state.streets || (!failed && !loading);
  $('#retry-streets').hidden = !state.streets || !failed;
  $('#map-status-text').textContent = failed
    ? `${loaded ? 'Haritanın bir bölümü' : 'Harita'} yüklenemedi. Bağlantını kontrol edip tekrar dene; kayıtların konumları korunuyor.`
    : loading ? 'İstanbul haritası yükleniyor…' : '';
  $('#map-mode').textContent = !state.streets || (failed && !loaded && !loading)
    ? 'Konum görünümü' : 'İstanbul haritası';
}
function requestMapRender() {
  if (state.mapFrame !== null) return;
  state.mapFrame = requestAnimationFrame(() => { state.mapFrame = null; renderMap(); });
}
function renderMap() {
  const canvas = $('#map-canvas'); const width = canvas.clientWidth; const height = canvas.clientHeight;
  if (!width || !height) return;
  if (state.mapView === 'istanbul') fitMapExtent(istanbulExtent);
  const center = project(state.center.lat, state.center.lon);
  const offset = {x: width / 2 - center.x, y: height / 2 - center.y};
  const origin = project(state.origin.lat, state.origin.lon);
  const originX = origin.x + offset.x; const originY = origin.y + offset.y;
  const metersPerPixel = 156543.03392 * Math.cos(state.origin.lat * Math.PI / 180) / 2 ** state.zoom;
  const radius = state.filters.radius_km * 1000 / metersPerPixel;
  const ring = $('#search-radius'); ring.style.width = `${radius * 2}px`; ring.style.height = `${radius * 2}px`; ring.style.left = `${originX}px`; ring.style.top = `${originY}px`;
  const originMarker = $('#origin-marker'); originMarker.style.left = `${originX}px`; originMarker.style.top = `${originY}px`;
  $('#coordinate-label').textContent = `${state.center.lat.toFixed(4)}° K  ·  ${state.center.lon.toFixed(4)}° D`;
  const markerLayer = $('#marker-layer'); markerLayer.replaceChildren();
  const groups = [];
  state.selected.forEach((place, index) => {
    if (!Number.isFinite(place.lat) || !Number.isFinite(place.lon)) return;
    const p = project(place.lat, place.lon); const x = p.x + offset.x; const y = p.y + offset.y;
    if (x < -180 || x > width + 30 || y < -40 || y > height + 40) return;
    const nearby = state.zoom < 18 ? groups.find(group => Math.hypot(group.x - x, group.y - y) < 45) : null;
    if (nearby) {
      nearby.x = (nearby.x * nearby.places.length + x) / (nearby.places.length + 1);
      nearby.y = (nearby.y * nearby.places.length + y) / (nearby.places.length + 1);
      nearby.places.push(place);
    } else groups.push({x, y, index, places: [place]});
  });
  groups.forEach(group => {
    const {x, y, index, places} = group;
    const place = places[0];
    const marker = element('button', 'map-marker'); marker.type = 'button';
    marker.style.left = `${x}px`; marker.style.top = `${y}px`;
    if (places.length > 1) {
      marker.classList.add('map-cluster');
      marker.setAttribute('aria-label', `${places.length} kaynak kaydını haritada yakınlaştır`);
      marker.append(element('span', 'pin', String(places.length)), element('span', 'pin-label', `${places.length} yer · Yakınlaştır`));
      marker.addEventListener('click', () => focusPlaces(places)); markerLayer.append(marker); return;
    }
    marker.setAttribute('aria-label', `${place.name}, kaynak bilgilerini aç`);
    marker.classList.toggle('selected', place.id === state.activeId);
    marker.append(element('span', 'pin', String(index + 1)), element('span', 'pin-label', place.name));
    marker.addEventListener('click', () => showPlace(place)); markerLayer.append(marker);
  });
  if (state.streets) renderTiles(center, width, height);
}
function renderTiles(center, width, height) {
  const layer = $('#tile-layer'); const needed = new Set(); const count = 2 ** state.zoom;
  const startX = Math.floor((center.x - width / 2) / 256); const endX = Math.floor((center.x + width / 2) / 256);
  const startY = Math.floor((center.y - height / 2) / 256); const endY = Math.floor((center.y + height / 2) / 256);
  for (let x = startX; x <= endX; x++) for (let y = startY; y <= endY; y++) {
    if (y < 0 || y >= count) continue;
    const tileX = ((x % count) + count) % count; const key = `${state.zoom}/${x}/${y}`; needed.add(key);
    let img = tileNodes.get(key);
    if (!img) {
      img = document.createElement('img'); img.alt = ''; img.draggable = false; img.decoding = 'async';
      img.dataset.loadState = failedTiles.has(key) ? 'error' : 'loading';
      img.addEventListener('load', () => { img.dataset.loadState = 'loaded'; updateMapStatus(); }, {once: true});
      img.addEventListener('error', () => { img.dataset.loadState = 'error'; failedTiles.add(key); updateMapStatus(); }, {once: true});
      // A normal browser request, only for currently visible tiles; default cache/referer preserved.
      // Failed tiles are retried only by the explicit retry button, never by re-rendering.
      if (!failedTiles.has(key)) img.src = `https://tile.openstreetmap.org/${state.zoom}/${tileX}/${y}.png`;
      tileNodes.set(key, img); layer.append(img);
    }
    img.style.left = `${x * 256 - center.x + width / 2}px`; img.style.top = `${y * 256 - center.y + height / 2}px`;
  }
  for (const [key, img] of tileNodes) if (!needed.has(key)) { img.remove(); tileNodes.delete(key); }
  updateMapStatus();
}
function setZoom(zoom) {
  // Keep the city/place under the usable viewport's center, not under overlays.
  const padding = mapPadding(), center = project(state.center.lat, state.center.lon);
  const focus = unproject(center.x + (padding.left - padding.right) / 2,
    center.y + (padding.top - padding.bottom) / 2);
  state.mapView = 'free'; state.zoom = Math.max(7, Math.min(19, zoom));
  const next = project(focus.lat, focus.lon);
  state.center = unproject(next.x + (padding.right - padding.left) / 2,
    next.y + (padding.bottom - padding.top) / 2);
  renderMap();
}
$('#zoom-in').addEventListener('click', () => setZoom(state.zoom + 1));
$('#zoom-out').addEventListener('click', () => setZoom(state.zoom - 1));
$('#recenter').addEventListener('click', () => { state.mapView = 'istanbul'; renderMap(); });
$('#focus-discovery').addEventListener('click', () => focusPlaces(state.selected));
$('#toggle-streets').addEventListener('click', () => {
  state.streets = !state.streets;
  $('#toggle-streets').textContent = state.streets ? 'Haritayı gizle' : 'Haritayı göster';
  $('#toggle-streets').setAttribute('aria-pressed', String(state.streets));
  $('#osm-attribution').hidden = !state.streets;
  if (!state.streets) { $('#tile-layer').replaceChildren(); tileNodes.clear(); }
  renderMap(); updateMapStatus();
});
$('#retry-streets').addEventListener('click', () => {
  for (const [key, img] of tileNodes) if (img.dataset.loadState === 'error') {
    img.remove(); tileNodes.delete(key); failedTiles.delete(key);
  }
  renderMap();
});
let pan = null;
$('#map-canvas').addEventListener('pointerdown', event => {
  if (event.target.closest('button') || event.button !== 0) return;
  pan = {x: event.clientX, y: event.clientY, center: project(state.center.lat, state.center.lon), id: event.pointerId};
  event.currentTarget.setPointerCapture(event.pointerId); event.currentTarget.classList.add('dragging');
});
$('#map-canvas').addEventListener('pointermove', event => {
  if (!pan || event.pointerId !== pan.id) return;
  const next = unproject(pan.center.x - (event.clientX - pan.x), pan.center.y - (event.clientY - pan.y));
  state.mapView = 'free'; state.center = clampMapCenter(next); requestMapRender();
});
function endPan() { pan = null; $('#map-canvas').classList.remove('dragging'); }
$('#map-canvas').addEventListener('pointerup', endPan); $('#map-canvas').addEventListener('pointercancel', endPan);
$('#map-canvas').addEventListener('keydown', event => {
  if (event.target !== event.currentTarget) return;
  const shifts = {ArrowLeft: [-80, 0], ArrowRight: [80, 0], ArrowUp: [0, -80], ArrowDown: [0, 80]};
  if (shifts[event.key]) { event.preventDefault(); const p = project(state.center.lat, state.center.lon); const d = shifts[event.key]; state.mapView = 'free'; state.center = clampMapCenter(unproject(p.x + d[0], p.y + d[1])); renderMap(); }
  if (event.key === '+' || event.key === '=') { event.preventDefault(); setZoom(state.zoom + 1); }
  if (event.key === '-') { event.preventDefault(); setZoom(state.zoom - 1); }
});
new ResizeObserver(requestMapRender).observe($('#map-canvas'));

// Category swipe is scoped to the category band, leaving map pan independent.
$$('[data-category]').forEach(button => button.addEventListener('click', () => chooseCategory(button.dataset.category)));
let categorySwipe = null; let suppressCategoryClick = false;
$('#category-band').addEventListener('pointerdown', event => { categorySwipe = {x: event.clientX, y: event.clientY}; });
$('#category-band').addEventListener('pointerup', event => {
  if (!categorySwipe) return;
  const dx = event.clientX - categorySwipe.x, dy = event.clientY - categorySwipe.y; categorySwipe = null;
  if (Math.abs(dx) > 45 && Math.abs(dx) > Math.abs(dy) * 1.3) {
    const index = state.categories.findIndex(c => c.id === state.filters.category);
    const next = Math.max(0, Math.min(state.categories.length - 1, index + (dx < 0 ? 1 : -1)));
    suppressCategoryClick = true; chooseCategory(state.categories[next].id); setTimeout(() => { suppressCategoryClick = false; }, 0);
  }
});
$('#category-band').addEventListener('click', event => { if (suppressCategoryClick) { event.preventDefault(); event.stopImmediatePropagation(); } }, true);
$('#category-band').addEventListener('pointercancel', () => { categorySwipe = null; });
$('#category-band').addEventListener('keydown', event => {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault(); const index = state.categories.findIndex(c => c.id === state.filters.category);
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? state.categories.length - 1 : Math.max(0, Math.min(state.categories.length - 1, index + (event.key === 'ArrowRight' ? 1 : -1)));
  chooseCategory(state.categories[next].id); $(`[data-category="${state.categories[next].id}"]`).focus();
});
$('#radius').addEventListener('change', event => { state.filters.radius_km = Number(event.target.value); discover(); });
$('#open-now').addEventListener('change', event => { state.filters.open_now = event.target.checked; discover(); });
$('#filter-form').addEventListener('submit', event => event.preventDefault());

const dialogOpener = new WeakMap();
function openDialog(id) {
  const dialog = $(`#${id}`); if (dialog.open) return;
  dialogOpener.set(dialog, document.activeElement); dialog.showModal();
}
$$('dialog').forEach(dialog => {
  $('[data-close]', dialog)?.addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target !== dialog) return; const rect = dialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close(); });
  dialog.addEventListener('close', () => { const opener = dialogOpener.get(dialog); if (opener?.isConnected) opener.focus(); });
});
$('#open-chat').addEventListener('click', () => { openDialog('chat-dialog'); $('#chat-input').focus(); });
$('#open-profile').addEventListener('click', () => openDialog('profile-dialog'));
$('#open-filters').addEventListener('click', () => { syncFilters(); openDialog('filters-dialog'); });
$('#advanced-filter-form').addEventListener('submit', event => {
  event.preventDefault(); state.filters.budget = $('#budget').value === '' ? null : Number($('#budget').value); state.filters.quiet = $('#quiet').checked;
  $('#filters-dialog').close(); syncFilters(); discover();
});
$('#reset-filters').addEventListener('click', () => { $('#filters-dialog').close(); resetFilters(); });

function showPlace(place) {
  state.activeId = place.id; renderMap(); $('#detail-title').textContent = place.name;
  const content = $('#detail-content'); content.replaceChildren();
  const metric = element('div', 'detail-metric'); metric.append(element('strong', '', distanceText(place.distance_km)), element('span', '', 'Galata merkezinden kuş uçuşu · Yol süresi değildir')); content.append(metric);
  const fields = [['Bilginin durumu', 'Kaynak kaydı'], ['Şu anda açık mı?', 'Teyit edilmedi'], ['Güncel fiyat', place.price === null || place.price === undefined ? 'Bilinmiyor' : `${place.price} TL`], ['Kalabalık', 'Bilinmiyor']];
  const rows = element('div', 'detail-list');
  fields.forEach(([label, value]) => { const row = element('div', 'detail-row'); row.append(element('span', '', label), element('strong', '', value)); rows.append(row); }); content.append(rows);
  content.append(element('p', 'detail-note', 'Bu yer, araştırma kataloğundaki kaynaktan gösteriliyor. Ziyaret öncesi çalışma saatini, erişimi ve fiyatı yetkili kaynaktan kontrol et.'));
  if (place.source_note) content.append(element('p', 'detail-note', place.source_note));
  const focus = element('button', 'primary-button', 'Haritada yakınlaştır'); focus.type = 'button';
  focus.addEventListener('click', () => { $('#detail-dialog').close(); focusPlaces([place]); }); content.append(focus);
  const sourceParts = [place.source_label, place.acquired_date ? `Alıntı tarihi: ${place.acquired_date}` : '', place.license].filter(Boolean);
  if (sourceParts.length) content.append(element('p', 'detail-note', sourceParts.join(' · ')));
  try { const url = new URL(place.source_url); if (url.protocol === 'https:' || url.protocol === 'http:') { const link = element('a', 'source-link', 'Kaynak kaydını aç ↗'); link.href = url.href; link.target = '_blank'; link.rel = 'noopener'; content.append(link); } } catch { /* A missing source is shown as missing, never fabricated. */ }
  openDialog('detail-dialog');
}
function renderProfile() {
  $('#profile-name').value = profile.name;
  const initial = [...profile.name.trim()][0]?.toLocaleUpperCase('tr-TR') || 'K'; $('#avatar-initial').textContent = initial; $('#profile-initial').textContent = initial;
  $(`input[name="mode"][value="${profile.mode}"]`).checked = true;
}
$('#profile-form').addEventListener('submit', event => {
  event.preventDefault(); profile.name = $('#profile-name').value.trim().slice(0, 40) || 'Ziya'; profile.mode = $('input[name="mode"]:checked').value;
  state.filters.mode = profile.mode; storage.write('kep.preview.profile', profile); renderProfile(); $('#profile-dialog').close(); showToast('Tercihlerin bu tarayıcıda kaydedildi.'); discover();
});
$('#reset-local').addEventListener('click', () => {
  storage.remove('kep.preview.profile'); storage.remove('kep.preview.plan');
  profile.name = 'Ziya'; profile.mode = 'balanced'; state.filters.mode = 'balanced'; renderProfile(); planDraft = defaultPlan(); renderPlan();
  showToast('Bu tarayıcıdaki profil ve gün taslağı temizlendi.'); discover();
});
let hold = null; let holdTimer; let skipAvatarClick = false;
$('#avatar').addEventListener('pointerdown', event => {
  if (event.button !== 0) return;
  hold = {y: event.clientY, started: performance.now(), pointerId: event.pointerId, opened: false}; skipAvatarClick = false;
  event.currentTarget.setPointerCapture(event.pointerId);
  holdTimer = setTimeout(() => { if (hold) $('#avatar').classList.add('held'); }, 350);
});
$('#avatar').addEventListener('pointermove', event => {
  if (!hold || hold.pointerId !== event.pointerId) return;
  if (Math.abs(hold.y - event.clientY) > 10) skipAvatarClick = true;
  if (!hold.opened && performance.now() - hold.started >= 350 && hold.y - event.clientY >= 70) {
    hold.opened = true; skipAvatarClick = true; $('#avatar').classList.remove('held'); openDialog('profile-dialog');
  }
});
function releaseAvatar(event) {
  clearTimeout(holdTimer); $('#avatar').classList.remove('held');
  if (hold && !hold.opened && performance.now() - hold.started >= 350 && hold.y - event.clientY >= 70) { skipAvatarClick = true; openDialog('profile-dialog'); }
  hold = null;
}
$('#avatar').addEventListener('pointerup', releaseAvatar);
$('#avatar').addEventListener('pointercancel', () => { clearTimeout(holdTimer); hold = null; skipAvatarClick = true; $('#avatar').classList.remove('held'); });
$('#avatar').addEventListener('click', () => { if (skipAvatarClick) { skipAvatarClick = false; return; } openDialog('chat-dialog'); $('#chat-input').focus(); });

function appendMessage(text, type = 'assistant') {
  const message = element('div', `chat-message ${type}`);
  if (type !== 'user') message.append(element('span', 'message-avatar', 'k'));
  message.append(element('p', '', text)); $('#chat-log').append(message); $('#chat-log').scrollTop = $('#chat-log').scrollHeight;
}
let chatBusy = false;
async function sendChat(message) {
  if (chatBusy || !message.trim()) return;
  if (!state.ready) { appendMessage('Önce Kep bağlantısının kurulmasını bekleyelim.', 'error'); return; }
  chatBusy = true; $('#chat-send').disabled = true; $$('[data-prompt]').forEach(b => { b.disabled = true; });
  appendMessage(message.trim(), 'user'); $('#chat-input').value = '';
  const version = ++state.requestVersion; state.abort?.abort();
  $('#results-list').setAttribute('aria-busy', 'true'); $('#result-context').textContent = 'Mesajın kontrol ediliyor…';
  try {
    const response = await api('/api/chat', {message: message.trim(), filters: {...state.filters}});
    appendMessage(response.reply || response.clarifications?.join('\n') || 'Bu isteği biraz daha açık yazar mısın?');
    if (version === state.requestVersion) applyResponse(response);
  } catch (error) {
    appendMessage(error.message, 'error');
    if (version === state.requestVersion) { state.selected = []; renderMap(); renderError(error.message); }
  }
  finally {
    if (version === state.requestVersion) $('#results-list').setAttribute('aria-busy', 'false');
    chatBusy = false; $('#chat-send').disabled = false; $$('[data-prompt]').forEach(b => { b.disabled = false; });
  }
}
$('#chat-form').addEventListener('submit', event => { event.preventDefault(); sendChat($('#chat-input').value); });
$$('[data-prompt]').forEach(button => button.addEventListener('click', () => sendChat(button.dataset.prompt)));

function istanbulDate() {
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone: 'Europe/Istanbul', year: 'numeric', month: '2-digit', day: '2-digit'}).formatToParts(new Date());
  const value = type => parts.find(p => p.type === type).value; return `${value('year')}-${value('month')}-${value('day')}`;
}
function defaultPlan() { return {date: istanbulDate(), stops: [
  {id: 'maslak', label: 'Maslak', arrival: '16:00', duration_minutes: null},
  {id: 'levent', label: 'Levent', arrival: '17:00', duration_minutes: null},
  {id: 'dinner', label: 'Ekip yemeği', arrival: null, duration_minutes: null},
  {id: 'zorlu', label: 'Zorlu PSM', arrival: '20:00', duration_minutes: 0},
], travel_minutes: [null, null, null], arrival_buffer_minutes: 15}; }
function validDraft(value) { return value && typeof value === 'object' && /^\d{4}-\d{2}-\d{2}$/.test(value.date || '') && Array.isArray(value.stops) && value.stops.length === 4 && value.stops.every(s => s && typeof s === 'object' && typeof s.id === 'string' && typeof s.label === 'string') && Array.isArray(value.travel_minutes) && value.travel_minutes.length === 3; }
const storedDraft = storage.read('kep.preview.plan', null);
let planDraft = validDraft(storedDraft) ? storedDraft : defaultPlan();
let planRevision = 0;
let planAbort = null;
function invalidatePlan() {
  ++planRevision;
  planAbort?.abort(); planAbort = null;
  $('#calculate-plan').disabled = false;
  $('#plan-result').hidden = true;
}
function renderPlan() {
  invalidatePlan();
  $('#plan-date').value = planDraft.date; $('#plan-buffer').value = planDraft.arrival_buffer_minutes ?? 15;
  const container = $('#plan-stops'); container.replaceChildren();
  planDraft.stops.forEach((stop, index) => {
    const row = element('div', 'plan-stop'); row.append(element('span', 'stop-dot', String(index + 1)));
    const content = element('div', 'stop-content'); const name = element('div', 'stop-name');
    const input = document.createElement('input'); input.value = stop.label; input.dataset.stopName = index; input.maxLength = 60; input.required = true; input.setAttribute('aria-label', `${index + 1}. durağın adı`);
    name.append(input, element('span', '', index === 2 ? 'ESNEK DURAK' : 'SABİT SAAT')); content.append(name);
    const fields = element('div', 'stop-fields');
    const arrivalLabel = element('label', '', index === 2 ? 'Esnek başlangıç' : 'Varış saati');
    const arrival = document.createElement('input'); arrival.className = 'text-input'; arrival.type = 'time'; arrival.value = stop.arrival || ''; arrival.dataset.stopArrival = index; arrival.setAttribute('aria-label', `${stop.label} varış saati`);
    if (index === 2) { arrival.disabled = true; arrival.title = 'Önceki duraktan sonra hesaplanır'; } else arrival.required = true;
    arrivalLabel.append(arrival);
    const durationLabel = element('label', '', 'Burada geçecek süre · dk');
    const duration = document.createElement('input'); duration.className = 'text-input'; duration.type = 'number'; duration.min = '0'; duration.max = '1440'; duration.step = '1'; duration.placeholder = index === 2 ? 'Örn. 75' : index === 3 ? '0' : 'Örn. 45'; duration.value = stop.duration_minutes ?? ''; duration.dataset.stopDuration = index; duration.setAttribute('aria-label', `${stop.label} süresi dakika`); durationLabel.append(duration);
    fields.append(arrivalLabel, durationLabel); content.append(fields); row.append(content); container.append(row);
    if (index < 3) {
      const travel = element('label', 'travel-field'); travel.append(element('span', 'travel-arrow', '↓'), document.createTextNode('Tahmini yol'));
      const time = document.createElement('input'); time.type = 'number'; time.min = '0'; time.max = '1440'; time.step = '1'; time.placeholder = '…'; time.value = planDraft.travel_minutes[index] ?? ''; time.dataset.travel = index; time.setAttribute('aria-label', `${stop.label} ile ${planDraft.stops[index + 1].label} arası tahmini yol süresi dakika`);
      travel.append(time, document.createTextNode('dk')); container.append(travel);
    }
  });
  $('#plan-result').hidden = true;
}
function readPlan() {
  return {date: $('#plan-date').value, arrival_buffer_minutes: Number($('#plan-buffer').value),
    stops: planDraft.stops.map((stop, index) => ({id: stop.id, label: $(`[data-stop-name="${index}"]`).value.trim(), arrival: index === 2 ? null : $(`[data-stop-arrival="${index}"]`).value || null, duration_minutes: $(`[data-stop-duration="${index}"]`).value === '' ? null : Number($(`[data-stop-duration="${index}"]`).value)})),
    travel_minutes: [0, 1, 2].map(index => $(`[data-travel="${index}"]`).value === '' ? null : Number($(`[data-travel="${index}"]`).value)),
  };
}
$('#open-plan').addEventListener('click', () => { renderPlan(); openDialog('plan-dialog'); });
$('#plan-dialog').addEventListener('close', invalidatePlan);
$('#plan-form').addEventListener('input', () => { planDraft = readPlan(); storage.write('kep.preview.plan', planDraft); invalidatePlan(); });
$('#plan-form').addEventListener('submit', async event => {
  event.preventDefault(); invalidatePlan();
  const draft = readPlan();
  const snapshot = Object.freeze({...draft,
    stops: Object.freeze(draft.stops.map(stop => Object.freeze({...stop}))),
    travel_minutes: Object.freeze([...draft.travel_minutes]),
  });
  planDraft = snapshot; storage.write('kep.preview.plan', snapshot);
  const revision = planRevision;
  const controller = new AbortController(); planAbort = controller;
  $('#calculate-plan').disabled = true;
  try {
    const result = await api('/api/plan', snapshot, controller.signal);
    if (revision === planRevision) renderPlanResult(result, snapshot);
  } catch (error) {
    if (error.name !== 'AbortError' && revision === planRevision) renderPlanError(error.message);
  } finally {
    if (revision === planRevision) { planAbort = null; $('#calculate-plan').disabled = false; }
  }
});
function clockText(value) {
  if (typeof value !== 'string') return '—';
  const match = value.match(/(?:T|^)(\d{2}:\d{2})/); return match ? match[1] : value;
}
function renderPlanError(message) {
  const box = $('#plan-result'); box.hidden = false; box.replaceChildren(); box.classList.remove('conflict');
  box.append(element('h3', '', 'Hesap tamamlanamadı.'), element('p', '', message),
    element('small', '', 'Yeni bir zaman hesabı üretilemedi. Bağlantını ve formdaki bilgileri kontrol edip yeniden dene.'));
  box.scrollIntoView({block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
}
function renderPlanResult(result, snapshot) {
  const box = $('#plan-result'); box.hidden = false; box.replaceChildren(); box.classList.toggle('conflict', result.status === 'conflict');
  const titles = {needs_input: 'Süreleri tamamlayalım.', feasible: 'Verdiğin sürelere göre plan sığıyor.', conflict: 'Bu sürelerle bir çakışma var.'};
  box.append(element('h3', '', titles[result.status] || 'Gün taslağı'));
  const messages = [...(result.missing || []), ...(result.conflicts || [])];
  if (messages.length) { const list = document.createElement('ul'); messages.forEach(m => list.append(element('li', '', typeof m === 'string' ? m : JSON.stringify(m)))); box.append(list); }
  if (result.status === 'feasible') {
    const stopMap = new Map(snapshot.stops.map(s => [s.id, s.label]));
    (result.legs || []).forEach(leg => {
      if (!leg.latest_departure) return;
      const row = element('div', 'plan-leg'); row.append(element('span', '', `${stopMap.get(leg.from_id) || leg.from_id} → ${stopMap.get(leg.to_id) || leg.to_id}`), element('strong', '', `En geç ${clockText(leg.latest_departure)}`)); box.append(row);
    });
    (result.stops || []).filter(s => s.arrival === null && s.planned_arrival).forEach(stop => box.append(element('p', '', `${stop.label}: ${clockText(stop.planned_arrival)}–${clockText(stop.planned_departure)}`)));
  }
  box.append(element('small', '', 'Hesap, girdiğin yol ve durak sürelerine dayanır. Canlı trafik veya rezervasyon teyidi değildir.'));
  box.scrollIntoView({block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
}

async function bootstrap() {
  $('#results-list').setAttribute('aria-busy', 'true');
  try {
    const response = await api('/api/bootstrap'); state.meta = response.meta;
    if (Number.isInteger(response.meta?.catalog_count)) $('#catalog-status').textContent = `Galata'dan arama · ${response.meta.catalog_count} örnek kayıt`;
    if (Array.isArray(response.categories) && response.categories.length) state.categories = response.categories;
    if (Number.isFinite(response.meta?.center?.lat) && Number.isFinite(response.meta?.center?.lon)) state.origin = {...response.meta.center};
    state.ready = true; applyResponse(response.initial);
    state.filters.mode = profile.mode;
  } catch (error) { renderError(error.message); }
  finally { $('#results-list').setAttribute('aria-busy', 'false'); }
}
renderProfile(); renderPlan(); syncFilters(); renderMap(); bootstrap();
