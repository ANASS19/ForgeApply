# SPDX-FileCopyrightText: 2026 Anass Nassiri and contributors
# SPDX-License-Identifier: Apache-2.0
"""Fast read-only discovery via public company job-board APIs and CSV imports."""
from __future__ import annotations
import csv
import html
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
from . import store

AI_KEYWORDS = re.compile(r'\b(ai|artificial intelligence|generative ai|genai|machine learning|ml engineer|deep learning|computer vision|llm|nlp|mlops|data scientist|data science|python|backend|software engineer|agentic|foundation model)\b', re.I)
SENIOR_KEYWORDS = re.compile(r'\b(chief|director|head of|vice president|principal|staff engineer|architect lead|post.?doc)\b', re.I)
ITALY_KEYWORDS = re.compile(r'\b(italy|italia|italian|milano|milan|roma|rome|torino|turin|bologna|firenze|florence|napoli|naples|padova|padua|trento|genova|venezia|venice|bari|pisa|brescia|bergamo|udine|parma|catania|palermo|trieste|verona|monza|modena|perugia)\b', re.I)


def text_only(value):
    return BeautifulSoup(html.unescape(value or ''), 'html.parser').get_text(' ', strip=True)


def score_job(title, location='', description='', italy_only=True):
    title, location, description = title or '', location or '', description or ''
    score = 15 if AI_KEYWORDS.search(title) else 0
    if re.search(r'\b(ai|ml|llm|genai|machine learning|computer vision)\b', title, re.I): score += 45
    if re.search(r'\b(junior|graduate|entry.?level|associate)\b', title, re.I): score += 15
    if SENIOR_KEYWORDS.search(title): score -= 60
    if re.search(r'\b(intern|stage|tirocinio)\b', title, re.I): score -= 30
    if AI_KEYWORDS.search(description): score += 10
    if ITALY_KEYWORDS.search(location): score += 20
    if re.search(r'\b(remote|remoto)\b', location, re.I): score += 5
    if italy_only and location and not ITALY_KEYWORDS.search(location):
        # Global remote is not equivalent to Italy-eligible.
        if not re.search(r'\b(worldwide|europe|emea|remote)\b', location, re.I): score -= 60
        else: score -= 10
    return max(0, min(100, score))


def detect_language(s):
    words = re.findall(r'\b(?:il|la|della|conoscenza|esperienza|competenze|requisiti|candidatura|lavoro|sviluppo|ingegnere|informatico)\b',s or '', re.I)
    return 'it' if len(words) >= 2 else 'en'


def import_csv(path):
    added = updated = 0
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            url = row.get('url') or row.get('link') or row.get('job_url')
            title = row.get('title') or row.get('job_title')
            if not url or not title: continue
            desc = row.get('description','')
            loc = row.get('location','')
            _, created=store.add_job(title=title,url=url,company=row.get('company',''),location=loc,
                                    source=row.get('source','csv'),description=desc, posted_at=row.get('posted_at') or None,
                                    score=score_job(title,loc,desc),language=detect_language(title+' '+desc))
            added += int(created); updated += int(not created)
    return {'added':added,'updated':updated}


def discover_board(ats, slug, *, client=None, italy_only=True):
    if not re.fullmatch(r'[a-zA-Z0-9._-]{2,100}',slug):
        raise ValueError('Board slug may only contain letters, numbers, dots, hyphens and underscores')
    endpoints = {
        'greenhouse': f'https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true',
        'lever': f'https://api.lever.co/v0/postings/{slug}?mode=json',
        'ashby': f'https://api.ashbyhq.com/posting-api/job-board/{slug}',
    }
    if ats not in endpoints: raise ValueError('Supported boards: greenhouse, lever, ashby')
    owns = client is None
    client = client or httpx.Client(timeout=20,follow_redirects=True)
    try:
        response = client.get(endpoints[ats]); response.raise_for_status(); data=response.json()
    finally:
        if owns: client.close()
    jobs = data if ats=='lever' else data.get('jobs',[])
    found = []
    for item in jobs:
        title=item.get('title') or item.get('text') or ''
        if not title: continue
        if ats=='greenhouse':
            location=(item.get('location') or {}).get('name',''); url=item.get('absolute_url','')
            desc=text_only(item.get('content','')); posted_at=item.get('updated_at')
        elif ats=='lever':
            location=(item.get('categories') or {}).get('location',''); url=item.get('hostedUrl') or item.get('applyUrl') or ''
            desc=text_only(item.get('descriptionPlain') or item.get('description',''))
            millis=item.get('createdAt'); posted_at=datetime.fromtimestamp(millis/1000,timezone.utc).isoformat() if isinstance(millis,(int,float)) else None
        else:
            location=item.get('location',''); url=item.get('jobUrl') or item.get('applyUrl') or ''
            desc=text_only(item.get('descriptionPlain') or item.get('descriptionHtml') or ''); posted_at=item.get('publishedAt')
        if not url: continue
        score=score_job(title,location,desc,italy_only)
        if italy_only and not ITALY_KEYWORDS.search(location) and not re.search(r'\b(europe|emea|worldwide)\b',location,re.I):
            continue
        found.append(dict(title=title, company=slug, location=location, url=url, source=ats,
                          description=desc[:12000], posted_at=posted_at, score=score,
                          language=detect_language(title+' '+desc)))
    return found


def sync_boards(boards=None):
    boards=boards or store.get_setting('boards',{})
    result={'added':0,'updated':0,'errors':[],'boards':0}
    for ats, slugs in boards.items():
        for slug in slugs:
            try:
                jobs=discover_board(ats,slug)
                result['boards']+=1
                for job in jobs:
                    _, new=store.add_job(**job)
                    result['added']+=int(new); result['updated']+=int(not new)
            except Exception as exc:
                result['errors'].append(f'{ats}/{slug}: {str(exc)[:200]}')
    return result
