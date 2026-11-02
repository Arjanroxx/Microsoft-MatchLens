"""Local SQLite event journal and insight audit trail; no model credentials stored."""
import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path


class Journal:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock()
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS matches(id TEXT PRIMARY KEY, metadata TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(match_id TEXT, sequence INTEGER, id TEXT, payload TEXT NOT NULL,
                    PRIMARY KEY(match_id, sequence), UNIQUE(match_id,id));
                CREATE TABLE IF NOT EXISTS insights(id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    match_id TEXT, cutoff INTEGER, payload TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10)
        try:
            with db:yield db
        finally:db.close()

    @staticmethod
    def encode(value):
        return json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':'))

    def restore(self,store):
        key=store.metadata['match_id'];encoded=self.encode(store.metadata)
        with self.lock,self.connect() as db:
            old=db.execute('SELECT metadata FROM matches WHERE id=?',(key,)).fetchone()
            if old and old[0]!=encoded:raise ValueError('Journal match ID has different metadata; use a different database')
            db.execute('INSERT OR IGNORE INTO matches VALUES (?,?)',(key,encoded))
            rows=db.execute('SELECT payload FROM events WHERE match_id=? ORDER BY sequence',(key,)).fetchall()
        if not store.replay:
            for row in rows:store.ingest(json.loads(row[0]))

    def event(self,event):
        encoded=self.encode(event)
        with self.lock,self.connect() as db:
            old=db.execute('SELECT payload FROM events WHERE match_id=? AND sequence=?',
                           (event['match_id'],event['sequence'])).fetchone()
            if old and old[0]!=encoded:raise ValueError('Journal sequence has conflicting data')
            db.execute('INSERT OR IGNORE INTO events VALUES (?,?,?,?)',
                       (event['match_id'],event['sequence'],event['event_id'],encoded))

    def insight(self,result):
        with self.lock,self.connect() as db:
            db.execute('INSERT INTO insights(match_id,cutoff,payload) VALUES (?,?,?)',
                       (result['match_id'],result['as_of_match_time_ms'],self.encode(result)))

    def history(self,match_id,time_ms,limit=20):
        with self.lock,self.connect() as db:
            rows=db.execute('SELECT payload FROM insights WHERE match_id=? AND cutoff<=? ORDER BY id DESC LIMIT ?',
                            (match_id,time_ms,limit)).fetchall()
        return [json.loads(row[0]) for row in rows]
