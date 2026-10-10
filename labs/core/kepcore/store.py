"""SQLite reference store: idempotence, ordered updates and a transactional outbox.

No external database, production source, social account or push service is used.
"""
from __future__ import annotations
import sqlite3, json
from pathlib import Path
from .core import stable_hash, dt

class Store:
    def __init__(self, path=':memory:'):
        self.db=sqlite3.connect(str(path))
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS objects (
          id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
          content_hash TEXT NOT NULL, record_json TEXT NOT NULL,
          source_observed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS observations (
          observation_id TEXT PRIMARY KEY, object_id TEXT NOT NULL REFERENCES objects(id),
          source_id TEXT NOT NULL, source_url TEXT NOT NULL,
          source_record_hash TEXT NOT NULL, observation_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS outbox (
          event_id TEXT PRIMARY KEY, object_id TEXT NOT NULL REFERENCES objects(id),
          revision INTEGER NOT NULL, event_type TEXT NOT NULL, payload_json TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending'
        );
        CREATE TABLE IF NOT EXISTS push_queue (
          push_id TEXT PRIMARY KEY, object_id TEXT NOT NULL REFERENCES objects(id),
          revision INTEGER NOT NULL, user_key TEXT NOT NULL, status TEXT NOT NULL,
          consent INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS decisions (
          decision_id TEXT PRIMARY KEY, query_json TEXT NOT NULL,
          decision_json TEXT NOT NULL
        );
        ''')

    def close(self): self.db.close()
    def get(self, object_id):
        row=self.db.execute('SELECT * FROM objects WHERE id=?',(object_id,)).fetchone()
        if not row:return None
        r=json.loads(row['record_json']);r['_revision']=row['revision'];return r

    def ingest(self, record:dict) -> str:
        if record.get('rights_scope')!='open_attribution':raise PermissionError('Unapproved source use')
        record={k:v for k,v in record.items() if not k.startswith('_')}
        raw=json.dumps(record,sort_keys=True,ensure_ascii=False)
        h=stable_hash(record); old=self.db.execute('SELECT * FROM objects WHERE id=?',(record['id'],)).fetchone()
        if old:
            if old['content_hash']==h:return 'unchanged'
            oldrecord=json.loads(old['record_json'])
            if oldrecord['source_id']!=record['source_id']:raise ValueError('Cross-source overwrite forbidden; reconcile claims first')
            prev=old['source_observed_at']; now=record.get('source_observed_at')
            if prev and (not now or dt(now)<dt(prev)):return 'ignored_older'
            if prev and now and dt(now)==dt(prev):
                # Same timestamp, incompatible contents: do not silently last-write-win.
                raise ValueError('Conflicting same-timestamp revision; evidence review required')
        rev=old['revision']+1 if old else 1
        with self.db:
            self.db.execute('INSERT INTO objects VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,content_hash=excluded.content_hash,record_json=excluded.record_json,source_observed_at=excluded.source_observed_at', (record['id'],rev,h,raw,record.get('source_observed_at')))
            self.db.execute('INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?,?)',(stable_hash([record['id'],h]),record['id'],record['source_id'],record['source_url'],record['source_record_hash'],raw))
            et='event.cancelled' if record.get('lifecycle')=='cancelled' else 'object.updated'
            self.db.execute('INSERT INTO outbox VALUES (?,?,?,?,?,?)',(stable_hash([record['id'],rev]),record['id'],rev,et,json.dumps({'id':record['id'],'revision':rev,'source_record_hash':record['source_record_hash']}),'pending'))
            self.db.execute("UPDATE push_queue SET status=? WHERE object_id=? AND status='pending'",('cancelled' if et=='event.cancelled' else 'superseded',record['id']))
        return 'updated' if old else 'inserted'

    def queue_push(self, object_id, user_key, *, consent:bool):
        if not consent:raise PermissionError('Push not authorized')
        r=self.get(object_id)
        if r is None:raise KeyError(object_id)
        if r.get('lifecycle')=='cancelled':raise ValueError('Cannot queue cancelled event')
        # Queue a candidate, not permission to dispatch. Fresh eligibility is checked at dispatch.
        key=stable_hash([object_id,r['_revision'],user_key])
        with self.db:self.db.execute('INSERT OR IGNORE INTO push_queue VALUES (?,?,?,?,?,?)',(key,object_id,r['_revision'],user_key,'pending',1))
        return key

    def preview_dispatch(self,push_id,query):
        """Revalidate a candidate; never sends a network notification."""
        from .core import decide
        p=self.db.execute('SELECT * FROM push_queue WHERE push_id=?',(push_id,)).fetchone()
        if p is None:raise KeyError(push_id)
        r=self.get(p['object_id'])
        if p['status']!='pending' or p['revision']!=r['_revision']:
            return dict(send=False,reason='INVALIDATED_OR_SUPERSEDED')
        if not query.proactive or not query.push_opt_in:return dict(send=False,reason='PUSH_QUERY_REQUIRES_CURRENT_CONSENT')
        d=decide([r],query)
        return dict(send=bool(d.selected),reason=d.action,network_send=False)

    def log_decision(self, query:dict, decision:dict):
        key=stable_hash([query,decision])
        with self.db:self.db.execute('INSERT OR IGNORE INTO decisions VALUES (?,?,?)',(key,json.dumps(query,ensure_ascii=False),json.dumps(decision,ensure_ascii=False)))
        return key
    def counts(self):
        return {t:self.db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('objects','observations','outbox','push_queue','decisions')}
