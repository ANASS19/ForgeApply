import asyncio
from types import SimpleNamespace

from forgeapply import browser as browser_module


def test_required_field_answered_by_saved_profile_is_not_unknown(monkeypatch):
    manager=browser_module.BrowserManager()
    fields=[{'index':0,'label':'Email','name':'email','id':'email','type':'email','required':True,'value':''}]
    async def snapshot(): return {'fields':fields,'text':'Email'}
    async def fill(i,value): return {'field_index':i,'value':value,'ok':True}
    manager._snapshot=snapshot
    manager._fill=fill
    manager._page=SimpleNamespace(url='https://example.com/apply')
    monkeypatch.setattr(browser_module, 'get_setting', lambda key, default=None: {'email':'test@example.com'} if key=='profile' else default)
    monkeypatch.setattr(browser_module, 'list_answers', lambda: [])
    result=asyncio.run(manager._autofill(False,False))
    assert result['filled'][0]['value']=='test@example.com'
    assert result['unknown']==[]


def test_failed_fill_keeps_required_question_unknown(monkeypatch):
    manager=browser_module.BrowserManager()
    fields=[{'index':0,'label':'Email','name':'email','id':'email','type':'email','required':True,'value':''}]
    async def snapshot(): return {'fields':fields,'text':'Email'}
    async def fail_fill(i,value): raise RuntimeError('blocked')
    manager._snapshot=snapshot
    manager._fill=fail_fill
    manager._page=SimpleNamespace(url='https://example.com/apply')
    monkeypatch.setattr(browser_module, 'get_setting', lambda key, default=None: {'email':'test@example.com'} if key=='profile' else default)
    monkeypatch.setattr(browser_module, 'list_answers', lambda: [])
    result=asyncio.run(manager._autofill(False,False))
    assert 'Email email email' in result['unknown'] or result['unknown']
    assert len(result['errors'])==1
