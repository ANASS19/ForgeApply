# SPDX-FileCopyrightText: 2026 Anass Nassiri and contributors
# SPDX-License-Identifier: Apache-2.0
"""Conservative reusable answers derived only from explicitly supplied candidate facts."""
from __future__ import annotations


def screening_answers(profile:dict,context:dict) -> list[dict]:
    candidates=[
        (r'^(?:full[ _-]?name|your full name|nome e cognome)\s*[:*?]?$',
         ' '.join(profile.get(k,'').strip() for k in ('first_name','last_name'))
         if profile.get('first_name') and profile.get('last_name') else ''),
        (r'^(?:e[ _-]?mail(?: address)?|indirizzo email)\s*[:*?]?$',profile.get('email')),
        (r'^(?:(?:phone|mobile)(?: number)?|telefono|cellulare)\s*[:*?]?$',profile.get('phone')),
        (r'^(?:(?:current |residence )?city|città(?: di residenza)?)\s*[:*?]?$',profile.get('city')),
        (r'^(?:(?:current )?country(?: of residence)?|paese di residenza)\s*[:*?]?$',profile.get('country')),
        (r'^(?:(?:how many )?years(?: of)? (?:general )?(?:AI|artificial intelligence)(?: experience)?|(?:general )?AI experience(?: \(years\))?)\s*[:*?]?$',profile.get('years_ai')),
    ]
    completed=[e for e in context.get('education',[]) if e.get('completed') is True]
    masters=[e for e in completed if e.get('level')=='masters']
    if masters:
        candidates.extend([
            (r'^(?:highest (?:completed )?(?:level of )?education(?: level)?|highest (?:completed )?degree)\s*[:*?]?$',"Master's degree"),
            (r"^(?:master'?s degree completed|have you completed (?:a |your )?master'?s degree)\s*[:*?]?$",'Yes'),
        ])
    for language,level in context.get('languages',{}).items():
        # Fixed known language keys prevent regex injection from profile content.
        names={'English':'english|inglese','Italian':'italian|italiano',
               'Arabic':'arabic|arabo','French':'french|francese'}
        if language in names and isinstance(level,str) and level:
            candidates.append((rf'^(?:{names[language]})(?: language)? (?:proficiency|level|fluency)\s*[:*?]?$',level))
    return [{'pattern':pattern,'answer':str(answer),'source':context.get('source','user:verified-profile')}
            for pattern,answer in candidates if answer]
