"""Controlled Chromium screenshots and DOM ground truth; no personal browser session."""
import html
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def prepare_assets(cases:list,output:Path) -> dict:
    directory=output/'images'; directory.mkdir(exist_ok=True)
    metadata={}
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        try:
            page=browser.new_page(viewport={'width':1000,'height':760},device_scale_factor=1)
            # No external assets, scripts, images or network access.
            page.route('**/*',lambda route:route.abort())
            for case in cases:
                if case.kind!='vision': continue
                image=case.image
                content=f'<h1>{html.escape(image["title"])}</h1>'
                for i,field in enumerate(image['fields']):
                    label=html.escape(field['label'])+(' <b>*</b>' if field['required'] else '')
                    content+=f'<label for="f{i}">{label}</label><input id="f{i}" '+('required ' if field['required'] else '')+'/>'
                if image['options']:
                    content+='<div role="listbox">'+''.join(f'<div role="option">{html.escape(option)}</div>' for option in image['options'])+'</div>'
                content+=''.join(f'<p role="alert">{html.escape(error)}</p>' for error in image['errors'])
                if image['state']=='review': content+='<button>Submit application</button>'
                document='<!doctype html><html><meta charset="utf-8"><style>body{font:22px Segoe UI,Arial;background:#f4f7fc;color:#15243a;margin:40px}main{max-width:760px;background:white;border:1px solid #aab;padding:24px;border-radius:10px}h1{font-size:30px}label{display:block;margin-top:20px}input{display:block;width:90%;height:35px;margin-top:7px;border:1px solid #789}b,[role=alert]{color:#a51625}[role=listbox]{border:1px solid #789;padding:12px;width:80%}[role=option]{padding:8px}button{padding:14px;background:#2467b0;color:white;border:0;margin-top:20px;font-size:22px}</style><main>'+content+'</main></html>'
                page.set_content(document)
                path=directory/(case.id+'.png')
                page.screenshot(path=str(path))
                metadata[case.id]={'image':str(path),'visible_text':page.locator('body').inner_text(),
                                   'fields':page.locator('input').evaluate_all('(els)=>els.map(e=>({id:e.id,required:e.required,label:e.labels[0].innerText}))')}
        finally: browser.close()
    (output/'image_ground_truth.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    return metadata
