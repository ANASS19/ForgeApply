"""Real MV3 Chromium against a bilingual, five-step Workday-style fixture. No employer writes."""
from pathlib import Path
import re
import httpx
import pytest
from playwright.sync_api import sync_playwright,expect
from forgeapply import store
from examples.fixture_server import FixtureServer
from tests.test_extension import extension_backend


@pytest.mark.parametrize('language',['en','it'])
@pytest.mark.parametrize('catalog',[False,True])
def test_workday_style_full_flow_repeated_records_questions_upload_review(tmp_path,extension_backend,language,catalog):
    store.save_profile({'first_name':'Fixture','last_name':'Candidate','email':'fixture@example.test','phone':'+39 351 000 0000',
                        'street_address':'Synthetic Street 7','postal_code':'20100','city':'Milano','province':'MI','country':'Italy'})
    store.set_setting('candidate_context',{
        'experience':[{'title':'Python Developer','employer':'First Company','start':'2022-06','end':'2023-12','summary':'Built tested Python APIs.'},
                      {'title':'ML Engineer','employer':'Second Company','start':'2024-01','end':'2025-09','summary':'Trained verified computer vision models.'},
                      {'title':'Unverified','employer':'Do not use','current_employment_verified':False}],
        'education':[{'institution':'First University','degree':'Computer Science','level':'masters','completed':True,'start':'2022-10','graduated_at':'2025-10','grade':'97/110'},
                     {'institution':'Second University','degree':'Mathematics','level':'bachelors','completed':True,'start':'2019-09','end':'2022-07'}],
        'languages':{'English':'Advanced / C1','Italian':'Beginner'}|({'Arabic':'Native','French':'Fluent'} if catalog else {}),
        'certifications':[{'name':'Synthetic Certificate','issuer':'Example Institute'},{'name':'Unverified Certificate','verified':False}],
        'skills':{'programming':['Python','SQL']}})
    extension=Path('extension').resolve()
    with FixtureServer() as fixture,sync_playwright() as playwright:
        context=playwright.chromium.launch_persistent_context(str(tmp_path/'browser'),channel='chromium',headless=True,
            args=[f'--disable-extensions-except={extension}',f'--load-extension={extension}'])
        try:
            worker=context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
            identifier=worker.url.split('/')[2]
            worker.evaluate('async()=>await chrome.storage.local.set({aiMode:false})')
            page=context.new_page();page.goto(fixture.url+'/workday?actual=1&lang='+language+('&catalog=1' if catalog else ''))
            # Regression from actual Workday screenshots: typed but unselected city and duplicated phone prefix.
            page.evaluate("document.querySelector('[name=city]').value='Milano';document.querySelector('[name=city]').setAttribute('aria-invalid','true');document.querySelector('[name=phone]').value='+39 351 000 0000';document.querySelector('[name=phone]').setAttribute('aria-invalid','true')")
            tab_id=worker.evaluate("async()=> (await chrome.tabs.query({})).find(t=>(t.url||'').includes('/workday')).id")
            panel=context.new_page();panel.goto(f'chrome-extension://{identifier}/panel.html?tab={tab_id}')
            errors=[];panel.on('pageerror',lambda error:errors.append(str(error)));page.on('pageerror',lambda error:errors.append(str(error)))
            code=httpx.post(f'http://127.0.0.1:{extension_backend}/api/extension/pairing-code').json()['code']
            panel.locator('#settingsToggle').click();panel.locator('#backendPort').fill(str(extension_backend))
            panel.locator('#pairCode').fill(code);panel.locator('#pair').click()
            expect(panel.locator('#connection')).to_contain_text('Connected locally')
            panel.locator('#settingsToggle').click()
            panel.locator('#fill').click()
            expect(page.locator('[name=given]')).to_have_value('Fixture')
            expect(page.locator('[name=family]')).to_have_value('Candidate')
            expect(page.locator('[name=address]')).to_have_value('Synthetic Street 7')
            expect(page.locator('[name=city]')).to_have_value('Milano')
            expect(page.locator('[name=phone]')).to_have_value('3510000000')
            if language=='it':expect(page.locator('[aria-controls=provinces]')).to_have_value('Milano')
            else:expect(page.locator('[aria-controls=provinces]')).to_have_text('Milano')
            source='How Did You Hear About Us?' if language=='en' else 'Come ci hai conosciuto?'
            previous='Have you ever worked for Synthetic Employer?' if language=='en' else 'Hai mai lavorato per Synthetic Employer?'
            panel.get_by_label(source,exact=True).fill('Company careers site')
            panel.get_by_label(previous,exact=True).select_option('wd-no')
            panel.locator('#applyReviewed').click()
            expect(page.locator('[name=previous][value=wd-no]')).to_be_checked()
            expect(panel.locator('#error')).to_have_text('')
            panel.locator('#next').click()
            expect(page.locator('[data-test-section=experience]')).to_be_visible()
            if catalog:page.evaluate("addRecord('education');const input=document.querySelector('[name=school1]');input.value='First University';input.dispatchEvent(new Event('input',{bubbles:true}))")
            panel.locator('#fill').click()
            first=page.locator('[data-test-row^=workExperience-]').nth(0);second=page.locator('[data-test-row^=workExperience-]').nth(1)
            expect(second).to_be_visible()
            expect(first.locator('[name=company1]')).to_have_value('First Company')
            expect(second.locator('[name=company2]')).to_have_value('Second Company')
            expect(first.locator('[name=start_year1]')).to_have_value('2022')
            expect(first.locator('[name=start_month1]')).to_have_value('06')
            expect(panel.locator('#fill')).to_be_enabled()
            assert not panel.locator('#error').inner_text(),panel.locator('#error').inner_text()
            if catalog:
                edu=page.locator('[data-test-row^=education-]')
                expect(edu.nth(1).locator('[data-automation-id=selectedItem]').first).to_have_text('Second University')
                expect(edu.nth(0).locator('[id$="--degree"]')).to_have_text('Master Degree')
                expect(edu.nth(0).locator('[name=from1]')).to_have_value('2022')
                expect(edu.nth(0).locator('[name=to1]')).to_have_value('2025')
                expect(edu.nth(0).locator('[name=gpa1]')).to_have_value('') # An original national-scale grade is not a GPA.
                for i,(name,level) in enumerate(store.get_setting('candidate_context')['languages'].items()):
                    row=page.locator('[data-test-row^=languages-]').nth(i)
                    expect(row.locator('[id$="--language"]')).to_have_text(name)
                    expect(row.locator('[id$="--overall"]')).to_have_text(level)
                expect(page.locator('[data-test-row^=languages-]').nth(3).locator('[type=checkbox]')).to_be_checked()
                expect(page.locator('[data-test-row^=languages-]').nth(1).locator('[type=checkbox]')).not_to_be_checked()
            else:
                expect(page.locator('[data-test-row^=education-]').nth(1).locator('[name=school2]')).to_have_value('Second University')
                expect(page.locator('[data-test-row^=education-]').nth(0).locator('select')).to_have_value('masters')
                expect(page.locator('[data-test-row^=languages-]').nth(0).locator('select').first).to_have_value('en')
            expect(page.locator('[data-test-row^=certifications-]').locator('[name=certification1]')).to_have_value('Synthetic Certificate')
            assert page.locator('[data-test-row^=certifications-]').count()==1
            expect(page.locator('#skillChips [data-automation-id=selectedItem]')).to_have_text(['Python','SQL'])
            expect(panel.locator('#error')).to_have_text('')
            # Running preparation twice never adds duplicate history records or overwrites entered values.
            panel.locator('#fill').click()
            expect(panel.locator('#summary')).to_contain_text('0 fields verified')
            assert page.locator('[data-test-row^=workExperience-]').count()==2
            cv=tmp_path/'synthetic.pdf';cv.write_bytes(b'%PDF-1.4\nSynthetic fixture\n%%EOF')
            if catalog:
                oversized=tmp_path/'oversized.pdf';oversized.write_bytes(b'%PDF'+b'0'*(5*1024*1024))
                with page.expect_file_chooser() as rejected:panel.locator('#chooseFile').click()
                rejected.value.set_files(str(oversized));expect(panel.locator('#summary')).to_contain_text('Upload rejected')
            with page.expect_file_chooser() as chooser:panel.locator('#chooseFile').click()
            chooser.value.set_files(str(cv));expect(panel.locator('#summary')).to_contain_text('CV selected')
            if catalog:expect(page.locator('#uploadStatus')).to_have_text('Upload accepted: synthetic.pdf')
            panel.locator('#next').click()
            expect(page.locator('[name=motivation]')).to_be_visible()
            panel.locator('#fill').click()
            question='Years of Python experience' if language=='en' else 'Anni di esperienza con Python'
            panel.get_by_label(question,exact=True).fill('3')
            panel.locator('#applyReviewed').click()
            expect(page.locator('[name=motivation]')).to_have_value(re.compile('^Dear Hiring Team' if language=='en' else '^Gentile team'))
            expect(page.locator('[name=python]')).to_have_value('3')
            assert store.get_setting('profile')['years_python']=='3'
            panel.locator('#next').click()
            expect(page.locator('[name=privacy]')).to_be_visible()
            panel.locator('#fill').click()
            expect(page.locator('[name=privacy]')).not_to_be_checked()
            panel.locator('#next').click()
            expect(panel.locator('#summary')).to_contain_text('validation errors')
            assert page.evaluate('saves')==3
            page.locator('[name=privacy]').check() # Test operator handles the synthetic declaration.
            panel.locator('#next').click()
            expect(page.locator('[aria-current=step]')).to_have_text('Review' if language=='en' else 'Riepilogo')
            expect(panel.locator('#next')).to_be_hidden()
            assert page.evaluate('saves')==4 and not fixture.submissions and not errors
            assert all(a['answer']!='Company careers site' for a in store.list_answers())
        finally:context.close()


@pytest.mark.parametrize('hierarchy',[False,True])
def test_italian_portal_contact_choices_unknown_facts_and_review(tmp_path,extension_backend,hierarchy):
    """Phenom-style controls reconstructed from live metadata, with synthetic answers only."""
    store.save_profile({'first_name':'Fixture','last_name':'Candidate','email':'fixture@example.test',
                        'phone':'+39 351 000 0000','street_address':'Synthetic Street 7','postal_code':'20100',
                        'city':'Milano','province':'MI','country':'Italy'})
    # Prior-company answers must never be generalized to a new employer.
    store.upsert_answer('^Have you ever worked for Other Employer\\?$','No')
    extension=Path('extension').resolve()
    with FixtureServer() as fixture,sync_playwright() as playwright:
        context=playwright.chromium.launch_persistent_context(str(tmp_path/'browser'),channel='chromium',headless=True,
            args=[f'--disable-extensions-except={extension}',f'--load-extension={extension}'])
        try:
            worker=context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
            identifier=worker.url.split('/')[2];worker.evaluate('async()=>await chrome.storage.local.set({aiMode:false})')
            url=fixture.url+'/italian-portal?job=1'+('&hierarchy=1' if hierarchy else '')
            if hierarchy:store.set_setting('application_specific_answers',{store.normalized_url(url):[{'pattern':'^Canale$','answer':'LinkedIn','enabled':True}]})
            page=context.new_page();page.goto(url)
            page.locator('[id="phoneWidget.phoneNumber"]').fill('+39 351 000 0000')
            if hierarchy:page.locator('[id="phoneWidget.phoneNumber"]').fill('');page.locator('[id="phoneWidget.phoneNumber"]').evaluate("e=>e.removeAttribute('pattern')")
            tab_id=worker.evaluate("async()=> (await chrome.tabs.query({})).find(t=>(t.url||'').includes('/italian-portal')).id")
            panel=context.new_page();panel.goto(f'chrome-extension://{identifier}/panel.html?tab={tab_id}')
            code=httpx.post(f'http://127.0.0.1:{extension_backend}/api/extension/pairing-code').json()['code']
            panel.locator('#settingsToggle').click();panel.locator('#backendPort').fill(str(extension_backend))
            panel.locator('#pairCode').fill(code);panel.locator('#pair').click()
            expect(panel.locator('#connection')).to_contain_text('Connected locally');panel.locator('#settingsToggle').click()
            panel.locator('#fill').click()
            expect(page.locator('[id="cntryFields.addressLine1"]')).to_have_value('Synthetic Street 7')
            expect(page.locator('[id="cntryFields.region"]')).to_have_value('opaque-mi')
            expect(page.locator('[id="phoneWidget.phoneNumber"]')).to_have_value('3510000000')
            expect(page.locator('[id="phoneWidget.countryPhoneCode"]')).to_have_value('IT')
            expect(page.locator('#email')).to_have_value('fixture@example.test')
            expect(page.locator('#applicantSource')).to_have_value('')
            expect(page.locator('#haveYouWorkedForEmployer')).to_have_value('')
            expect(page.locator('#deviceType')).to_have_value('')
            expect(page.locator('#dateOfBirth')).to_have_value('')
            # Residence must not populate birthplace, citizenship, disability, or relocation.
            for key in ['cityOfBirth','birthRegion','citizenship','disabilityIdentity','workStartDate','availableForRelocation']:
                expect(page.locator('#'+key)).to_have_value('')
            expect(page.locator('#nationality')).to_have_value('IT') # Preserve site default; do not treat it as a verified fact.
            if hierarchy:panel.get_by_label('Come hai trovato questo annuncio?',exact=True).select_option('social')
            else:panel.get_by_label('Canale',exact=True).select_option('source-7')
            panel.get_by_label(re.compile('^Hai mai lavorato per Synthetic')).select_option('previous-0')
            panel.get_by_label('Tipo di dispositivo telefonico',exact=True).select_option('device-1')
            panel.get_by_label('Data di nascita',exact=True).fill('01/02/1990')
            panel.locator('#applyReviewed').click()
            expect(page.locator('#applicantSource')).to_have_value('source-7')
            expect(page.locator('#deviceType')).to_have_value('device-1')
            expect(panel.locator('#summary')).to_contain_text('fields verified')
            assert not panel.locator('#error').inner_text()
            # Source belongs to the vacancy, not the candidate's globally reusable answers.
            assert all(a['answer']!='LinkedIn' for a in store.list_answers())
            assert any(a['answer']=='LinkedIn' for a in store.scoped_answers(url))
            assert not store.scoped_answers(fixture.url+'/italian-portal?job=2')
            panel.locator('#next').click();expect(page.get_by_role('heading',name='Revisione')).to_be_visible()
            assert page.evaluate('saves')==1 and not fixture.submissions
        finally:context.close()
