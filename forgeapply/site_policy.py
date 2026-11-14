# SPDX-FileCopyrightText: 2026 Anass Nassiri and contributors
# SPDX-License-Identifier: Apache-2.0
"""Technical capability registry. Recognition never grants permission from a website."""
from urllib.parse import urlsplit
import re


def capabilities(url:str) -> dict:
    parsed=urlsplit(url)
    host=(parsed.hostname or '').lower()
    matches=lambda domain:host==domain or host.endswith('.'+domain)
    platform='generic'
    for name,domains in {'linkedin':['linkedin.com'],'indeed':['indeed.com','indeed.it','indeed.co.uk'],
                         'greenhouse':['greenhouse.io'],'lever':['lever.co'],'ashby':['ashbyhq.com'],
                         'workday':['myworkdayjobs.com','myworkdaysite.com'],'smartrecruiters':['smartrecruiters.com']}.items():
        if any(matches(domain) for domain in domains): platform=name;break
    if re.search(r'(^|\.)indeed\.(?:com|[a-z]{2}|co\.[a-z]{2}|com\.[a-z]{2})$',host): platform='indeed'
    restricted=platform in ('linkedin','indeed')
    valid=parsed.scheme in ('http','https') and bool(host) and not parsed.username and not parsed.password
    return {'platform':platform,'url_import':valid,'dom_inspection':valid and not restricted,
            'form_preparation':valid and not restricted,'requires_site_authorization':True,
            'native_submission':'manual','automation':'manual_only' if restricted else 'operator_authorized',
            'verified_live_ats':False,'message':('Use URL import and manually supplied job text. Native scraping, Easy Apply clicks and autofill are disabled.' if restricted else
                'Inspect only on your explicit request. Confirm the site permits assistance before filling. Final submission stays manual in the extension.')}


def require_automation(url:str):
    policy=capabilities(url)
    if not policy['dom_inspection']: raise PermissionError(policy['message'])
    return policy
