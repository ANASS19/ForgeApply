import pytest
from forgeapply import store


def test_url_normalization():
    assert store.normalized_url('https://EXAMPLE.com/jobs/123/?utm_source=x&b=1')=='https://example.com/jobs/123?b=1'
    with pytest.raises(ValueError):store.normalized_url('file:///etc/passwd')


def test_db_lifecycle_and_no_duplicate():
    store.init_db()
    j1,yes=store.add_job(title='AI Engineer',url='https://example.com/jobs/x?utm_medium=news',company='A')
    assert yes
    j2,yes=store.add_job(title='AI Engineer',url='https://example.com/jobs/x',company='A')
    assert not yes and j1==j2
    store.set_status(j1,'submitted','Manually confirmed successful submission',acknowledged=True)
    with pytest.raises(ValueError):store.set_status(j1,'discovered')
    j3,yes=store.add_job(title='AI Engineer',url='https://example.com/jobs/x',company='A')
    assert j3==j1 and store.get_job(j1)['status']=='submitted'


def test_profile_and_answers():
    store.init_db(); store.set_setting('llm',{'provider':'ollama','model':'test-model'})
    assert store.get_setting('llm')['model']=='test-model'
    store.upsert_answer('years.*python','3')
    store.upsert_answer('years.*python','4')
    matches=[a for a in store.list_answers() if a['pattern']=='years.*python']
    assert len(matches)==1 and matches[0]['answer']=='4'


def test_answer_schema_migrates_without_erasing_values(tmp_path,monkeypatch):
    import sqlite3
    legacy=tmp_path/'legacy.sqlite3'
    with sqlite3.connect(legacy) as db:
        db.executescript("CREATE TABLE answers(id INTEGER PRIMARY KEY,pattern TEXT UNIQUE,answer TEXT,enabled INTEGER); INSERT INTO answers VALUES(1,'^Email$','fixture@example.org',1);")
    monkeypatch.setattr(store,'DB_FILE',legacy)
    store.init_db()
    store.init_db()
    answer=store.list_answers()[0]
    assert answer['answer']=='fixture@example.org'
    assert answer['source']==''  # Existing records are not falsely marked freshly verified.
    assert answer['fact_path']==answer['scope_host']==''
