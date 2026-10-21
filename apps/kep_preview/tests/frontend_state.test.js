'use strict';

// Exercise the actual event handlers with deliberately late transport replies.
// This is a small state-boundary harness, not a browser or a duplicate planner.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
function section(start, end) {
  const first = source.indexOf(start);
  const last = source.indexOf(end, first);
  assert.ok(first >= 0 && last > first, 'Actual UI boundary must be present');
  return source.slice(first, last);
}
function draft(dinnerMinutes = 60) {
  return {date: '2026-10-20', arrival_buffer_minutes: 15,
    stops: [
      {id: 'maslak', label: 'Maslak', arrival: '16:00', duration_minutes: 30},
      {id: 'levent', label: 'Levent', arrival: '17:00', duration_minutes: 45},
      {id: 'dinner', label: 'Ekip yemeği', arrival: null, duration_minutes: dinnerMinutes},
      {id: 'zorlu', label: 'Zorlu PSM', arrival: '20:00', duration_minutes: 0},
    ], travel_minutes: [10, 15, 20]};
}
function harness() {
  const listeners = new Map();
  const nodes = new Map();
  const requests = [], rendered = [], errors = [];
  let input = draft();
  function $(selector) {
    if (!nodes.has(selector)) nodes.set(selector, {hidden: true, disabled: false,
      addEventListener(type, handler) { listeners.set(`${selector}:${type}`, handler); },
    });
    return nodes.get(selector);
  }
  const context = vm.createContext({AbortController, $, storage: {write() {}},
    readPlan: () => structuredClone(input),
    api: (url, payload, signal) => new Promise((resolve, reject) => requests.push({url, payload, signal, resolve, reject})),
    renderPlanResult: (result, snapshot) => { $('#plan-result').hidden = false; rendered.push({result, snapshot}); },
    renderPlanError: message => { $('#plan-result').hidden = false; errors.push(message); },
  });
  vm.runInContext("'use strict'; let planDraft;\n" +
    section('let planRevision =', 'function renderPlan()') +
    section("$('#plan-dialog').addEventListener('close'", '\nfunction clockText'), context);
  return {requests, rendered, errors, nodes,
    submit: () => listeners.get('#plan-form:submit')({preventDefault() {}}),
    edit: value => { input = value; listeners.get('#plan-form:input')(); },
    close: () => listeners.get('#plan-dialog:close')(),
  };
}

test('malformed persisted stop cannot abort startup', () => {
  const context = vm.createContext({value: {...draft(), stops: [null, null, null, null]}});
  const valid = vm.runInContext(section('function validDraft(', '\nconst storedDraft') + '\nvalidDraft(value)', context);
  assert.equal(valid, false);
});

test('editing a submitted plan invalidates a late feasible response', async () => {
  const h = harness();
  const pending = h.submit();
  h.edit(draft(100));
  assert.equal(h.requests[0].signal.aborted, true);
  // The fake transport deliberately ignores abort, proving the revision guard.
  h.requests[0].resolve({status: 'feasible'});
  await pending;
  assert.equal(h.rendered.length, 0);
  assert.equal(h.nodes.get('#plan-result').hidden, true);
  assert.equal(h.nodes.get('#calculate-plan').disabled, false);
});

test('older response cannot replace a new result or mix draft labels', async () => {
  const h = harness();
  const old = h.submit();
  const changed = draft(100); changed.stops[2].label = 'Yeni yemek';
  h.edit(changed);
  const latest = h.submit();
  h.requests[1].resolve({status: 'conflict'}); await latest;
  h.requests[0].resolve({status: 'feasible'}); await old;
  assert.equal(h.rendered.length, 1);
  assert.equal(h.rendered[0].result.status, 'conflict');
  assert.equal(h.rendered[0].snapshot.stops[2].label, 'Yeni yemek');
  assert.equal(Object.isFrozen(h.rendered[0].snapshot), true);
  assert.equal(Object.isFrozen(h.rendered[0].snapshot.stops[2]), true);
});

test('closing the plan invalidates its pending response', async () => {
  const h = harness(), pending = h.submit();
  h.close(); h.requests[0].resolve({status: 'feasible'}); await pending;
  assert.equal(h.rendered.length, 0);
  assert.equal(h.requests[0].signal.aborted, true);
});

test('transport failure is not rendered as a planning conflict', async () => {
  const h = harness(), pending = h.submit();
  h.requests[0].reject(new Error('Bağlantı kurulamadı.')); await pending;
  assert.equal(h.rendered.length, 0);
  assert.deepEqual(h.errors, ['Bağlantı kurulamadı.']);
  assert.equal(h.nodes.get('#calculate-plan').disabled, false);
});

test('zoom preserves the fitted city focus within the usable viewport', () => {
  for (const [width, height, mobile] of [[320, 646, true], [390, 646, true], [959, 854, false]]) {
    const state = {zoom: 9, center: {lat: 0, lon: 0}};
    const context = vm.createContext({state, matchMedia: () => ({matches: mobile}),
      $: () => ({clientWidth: width, clientHeight: height}), renderMap() {}});
    vm.runInContext(section('function project(', 'function requestMapRender()') +
      section('function setZoom(', "$('#zoom-in').addEventListener"), context);
    vm.runInContext('fitMapExtent({west: 27.95, south: 40.75, east: 30.02, north: 41.62});', context);
    const focus = `(() => {
      const padding = mapPadding(), center = project(state.center.lat, state.center.lon);
      return unproject(center.x + (padding.left - padding.right) / 2,
        center.y + (padding.top - padding.bottom) / 2);
    })()`;
    const before = vm.runInContext(focus, context);
    vm.runInContext('setZoom(state.zoom + 1);', context);
    const after = vm.runInContext(focus, context);
    assert.ok(Math.abs(before.lat - after.lat) < 1e-10, 'Zoom must not move Istanbul toward the Black Sea');
    assert.ok(Math.abs(before.lon - after.lon) < 1e-10, 'Zoom must keep the same east-west focus');
  }
});
