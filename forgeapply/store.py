from __future__ import annotations
import json
import sqlite3
import threading
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from contextlib import contextmanager
from .config import DB_FILE

_LOCK = threading.RLock()
VALID_STATUSES = {'discovered', 'queued', 'opened', 'prepared', 'submitted', 'blocked', 'skipped', 'rejected'}
PROFILE_FIELDS = {
    'first_name', 'last_name', 'email', 'phone', 'linkedin', 'github', 'portfolio',
    'city', 'country', 'current_title', 'years_ai', 'years_python', 'work_authorized',
    'needs_sponsorship', 'notice_period', 'salary_expectation', 'resume_en', 'resume_it',
    'street_address','postal_code','province',
}
PROFILE_REFERENCE_FIELDS={'first_name','last_name','email','phone','linkedin','github','portfolio','city','country',
                          'street_address','postal_code','province','current_title'}
PROFILE_BINDABLE_FIELDS=PROFILE_REFERENCE_FIELDS|{'years_ai','years_python'}


def now():
    return datetime.now(timezone.utc).isoformat()


def normalized_url(url: str) -> str:
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.netloc:
        raise ValueError('Expected an http(s) URL')
    host = parts.hostname.lower() if parts.hostname else ''
    path = parts.path.rstrip('/') or '/'
    qs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
          if k.lower() not in {'trk','trackingid','refid','utm_source','utm_medium','utm_campaign','utm_content','utm_term','source','gh_src'}]
    if parts.username or parts.password:
        raise ValueError('URL credentials are not permitted')
    if ':' in host:
        host = f'[{host}]'
    return urlunsplit((parts.scheme, host + ((':' + str(parts.port)) if parts.port else ''), path, urlencode(sorted(qs)), ''))


@contextmanager
def conn():
    with _LOCK:
        db = sqlite3.connect(DB_FILE, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


def init_db():
    with conn() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            company TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL,
            location TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'manual',
            description TEXT NOT NULL DEFAULT '',
            posted_at TEXT,
            score INTEGER NOT NULL DEFAULT 0,
            language TEXT NOT NULL DEFAULT 'en',
            status TEXT NOT NULL DEFAULT 'discovered',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            submitted_at TEXT
        );
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern TEXT NOT NULL UNIQUE,
            answer TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL REFERENCES jobs(id),
            status TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_status_score ON jobs(status, score DESC);
        CREATE TABLE IF NOT EXISTS browser_runs (
            job_id INTEGER PRIMARY KEY REFERENCES jobs(id),
            state TEXT NOT NULL, url TEXT NOT NULL, trace TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS submission_attempts (
            job_id INTEGER PRIMARY KEY REFERENCES jobs(id),
            url TEXT NOT NULL, state TEXT NOT NULL, evidence TEXT NOT NULL DEFAULT '', at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS extension_pair_codes (code_hash TEXT PRIMARY KEY,expires_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS extension_pairs (extension_id TEXT PRIMARY KEY,token_hash TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS extension_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,extension_id TEXT NOT NULL,url TEXT NOT NULL,
            action TEXT NOT NULL,detail TEXT NOT NULL,at TEXT NOT NULL
        );
        ''')
        columns={row['name'] for row in db.execute('PRAGMA table_info(answers)')}
        for name in ('source','verified_at','fact_path','scope_host'):
            if name not in columns:
                db.execute(f"ALTER TABLE answers ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
        if 'origin_url' not in {row['name'] for row in db.execute('PRAGMA table_info(jobs)')}:
            db.execute("ALTER TABLE jobs ADD COLUMN origin_url TEXT NOT NULL DEFAULT ''")
        if db.execute('SELECT 1 FROM settings WHERE key="profile"').fetchone() is None:
            db.execute('INSERT INTO settings VALUES (?,?)', ('profile', json.dumps({
                'first_name':'', 'last_name':'', 'email':'', 'phone':'',
                'linkedin':'', 'github':'', 'portfolio':'', 'city':'',
                'country':'', 'current_title':'',
                'years_ai':'', 'years_python':'', 'work_authorized':'',
                'needs_sponsorship':'', 'notice_period':'', 'salary_expectation':'',
                'resume_en':'', 'resume_it':''
            })))
        if db.execute('SELECT 1 FROM settings WHERE key="boards"').fetchone() is None:
            db.execute('INSERT INTO settings VALUES (?,?)', ('boards', json.dumps({
                'greenhouse':[], 'lever':[], 'ashby':[]
            })))


def get_setting(key, default=None):
    with conn() as db:
        r = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(r['value']) if r else default


def set_setting(key, value):
    with conn() as db:
        db.execute('INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key,json.dumps(value)))


def scoped_answers(url:str) -> list[dict]:
    """Explicit job-specific answers must not leak into another vacancy's preparation."""
    try:key=normalized_url(url)
    except ValueError:return []
    return get_setting('application_specific_answers',{}).get(key,[])


def save_profile(data: dict, source: str = 'user:local-dashboard') -> dict:
    """Merge explicitly supplied facts and their provenance in a single transaction."""
    updates = {k: v for k, v in data.items() if k in PROFILE_FIELDS and isinstance(v, str)}
    with conn() as db:
        profile = json.loads(db.execute('SELECT value FROM settings WHERE key=?', ('profile',)).fetchone()[0])
        row = db.execute('SELECT value FROM settings WHERE key=?', ('profile_provenance',)).fetchone()
        provenance = json.loads(row[0]) if row else {}
        for key, value in updates.items():
            profile[key] = value
            provenance[key] = {'source': source, 'verified_at': now(), 'verified': bool(value)}
        for key, value in (('profile', profile), ('profile_provenance', provenance)):
            db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                       (key, json.dumps(value)))
    return profile


def add_job(*, title, url, company='', location='', source='manual', description='', posted_at=None, language='en', score=0,origin_url=''):
    url = normalized_url(url)
    origin_url=normalized_url(origin_url) if origin_url else ''
    t=now()
    with conn() as db:
        r=db.execute('SELECT id FROM jobs WHERE url=?', (url,)).fetchone()
        if r:
            # Never reset a submitted/processed status during re-import.
            db.execute('UPDATE jobs SET title=?, company=?, location=?, description=CASE WHEN ? != "" THEN ? ELSE description END, updated_at=? WHERE id=?',
                       (title, company, location, description, description, t, r['id']))
            if origin_url: db.execute('UPDATE jobs SET origin_url=? WHERE id=?',(origin_url,r['id']))
            return r['id'], False
        cur=db.execute('''INSERT INTO jobs(url,title,company,location,source,description,posted_at,score,language,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (url,title,company,location,source,description,posted_at,score,language,t,t))
        if origin_url: db.execute('UPDATE jobs SET origin_url=? WHERE id=?',(origin_url,cur.lastrowid))
        return cur.lastrowid, True


def get_job(job_id):
    with conn() as db:
        r=db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        return dict(r) if r else None


def save_browser_run(job_id:int,state:str,url:str,trace:list[dict]) -> None:
    with conn() as db:
        db.execute('INSERT INTO browser_runs VALUES (?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET state=excluded.state,url=excluded.url,trace=excluded.trace,updated_at=excluded.updated_at',
                   (job_id,state,url,json.dumps(trace[-100:]),now()))


def get_browser_run(job_id:int) -> dict | None:
    with conn() as db:
        row=db.execute('SELECT * FROM browser_runs WHERE job_id=?',(job_id,)).fetchone()
        if not row: return None
        result=dict(row)
        result['trace']=json.loads(result['trace'])
        return result


def begin_submission(job_id:int,url:str) -> None:
    """Record intent before the consequential click, including across process restarts."""
    with conn() as db:
        if db.execute('SELECT 1 FROM submission_attempts WHERE job_id=?',(job_id,)).fetchone():
            raise ValueError('A submission was already attempted; verify manually before any further action')
        db.execute('INSERT INTO submission_attempts(job_id,url,state,at) VALUES (?,?,?,?)',
                   (job_id,url,'confirmation_pending',now()))


def finish_submission(job_id:int,verified:bool,evidence:dict) -> None:
    with conn() as db:
        db.execute('UPDATE submission_attempts SET state=?,evidence=? WHERE job_id=?',
                   ('confirmed' if verified else 'manual_review',json.dumps(evidence),job_id))


def list_jobs(status=None, search=None, limit=500):
    clauses=[]; args=[]
    if status and status != 'all':
        clauses.append('status=?'); args.append(status)
    if search:
        clauses.append('(title LIKE ? OR company LIKE ? OR location LIKE ?)')
        args.extend([f'%{search}%']*3)
    q='SELECT * FROM jobs'+(' WHERE '+' AND '.join(clauses) if clauses else '')+' ORDER BY CASE status WHEN "queued" THEN 0 WHEN "discovered" THEN 1 ELSE 2 END, score DESC, id DESC LIMIT ?'
    args.append(min(int(limit),2000))
    with conn() as db: return [dict(r) for r in db.execute(q,args)]


def set_status(job_id, status, note='', *, acknowledged=False):
    if status not in VALID_STATUSES: raise ValueError('Invalid status')
    if status == 'submitted' and not (acknowledged and note.strip()):
        raise ValueError('Submitted requires explicit confirmation and an evidence note')
    with conn() as db:
        old=db.execute('SELECT status FROM jobs WHERE id=?',(job_id,)).fetchone()
        if not old: raise KeyError(job_id)
        if old['status']=='submitted' and status != 'submitted':
            raise ValueError('Cannot overwrite a confirmed submission')
        t=now()
        db.execute('UPDATE jobs SET status=?, notes=CASE WHEN ? != "" THEN ? ELSE notes END, updated_at=?, submitted_at=CASE WHEN ?="submitted" THEN COALESCE(submitted_at,?) ELSE submitted_at END WHERE id=?',
                   (status,note,note,t,status,t,job_id))
        db.execute('INSERT INTO events(job_id,status,note,at) VALUES (?,?,?,?)',(job_id,status,note,t))


def set_job_score(job_id, score, language):
    with conn() as db:
        db.execute('UPDATE jobs SET score=?, language=? WHERE id=?',(score,language,job_id))


def upsert_answer(pattern,answer,enabled=True,source='user:local-dashboard',*,fact_path='',scope_host=''):
    pattern=pattern.strip()
    if not pattern or len(pattern)>500: raise ValueError('Use a question pattern of 1–500 characters')
    re.compile(pattern)
    if fact_path and fact_path not in {'profile.'+key for key in PROFILE_BINDABLE_FIELDS}:raise ValueError('Unsupported profile fact reference')
    if scope_host and (len(scope_host)>255 or not re.fullmatch(r'[a-zA-Z0-9.:-]+',scope_host)):raise ValueError('Invalid answer host scope')
    with conn() as db:
        db.execute('INSERT INTO answers(pattern,answer,enabled,source,verified_at,fact_path,scope_host) VALUES (?,?,?,?,?,?,?) ON CONFLICT(pattern) DO UPDATE SET answer=excluded.answer, enabled=excluded.enabled, source=excluded.source, verified_at=excluded.verified_at, fact_path=excluded.fact_path, scope_host=excluded.scope_host',
                   (pattern,str(answer),int(enabled),source,now(),fact_path,scope_host))


def list_answers():
    with conn() as db:
        return [dict(r) for r in db.execute('SELECT * FROM answers ORDER BY pattern')]


def delete_answer(answer_id):
    with conn() as db: db.execute('DELETE FROM answers WHERE id=?',(answer_id,))


def stats():
    with conn() as db:
        r=db.execute('SELECT status,COUNT(*) n FROM jobs GROUP BY status')
        counts={row['status']:row['n'] for row in r}
        counts['total']=sum(counts.values())
        return counts
