"""Shared deterministic fact mapping for managed browser and extension preparation."""
import re

SENSITIVE_QUESTION=re.compile(
    r'visa|sponsor|work.?authori[sz]|right to work|permesso|criminal|disab|convict|'
    r'certif(?:y|ico)|declar|attest|consent|agree|privacy|gender|ethnic|veteran|'
    r'salary|compensation|notice period|availability|start date|immediately|citizenship|nationality',re.I)


def known_answer(field:dict,profile:dict,answers:list[dict]) -> tuple[str,str]|None:
    label=field.get('label') or field.get('name') or field.get('id') or ''
    if field.get('cross_origin') or field.get('value') or field.get('type') in ('file','password','hidden','submit','button','checkbox','radio'):
        return None
    if SENSITIVE_QUESTION.search(' '.join(str(field.get(k,'')) for k in ('label','name','id'))): return None
    for saved in answers:
        if not saved.get('enabled',True): continue
        try:
            if re.search(saved['pattern'],label,re.I): return str(saved['answer']),'saved_answer'
        except re.error: continue
    patterns={
        'first_name':r'first[ _-]?name|given name|nome', 'last_name':r'last[ _-]?name|surname|cognome',
        'email':r'e[ _-]?mail(?: address)?|indirizzo email',
        'phone':r'(?:phone|mobile|telefono|cellulare)(?: number)?',
        'linkedin':r'linkedin(?: (?:url|profile))?', 'github':r'github(?: (?:url|profile))?',
        'portfolio':r'portfolio|website|sito web', 'city':r'(?:current )?(?:city|città|comune|location)',
        'country':r'(?:current )?(?:country|paese|nazione)(?: of residence)?',
        'years_ai':r'(?:years(?: of)? (?:ai|artificial intelligence) experience|ai experience(?: \(years\))?)',
        'years_python':r'(?:years(?: of)? python experience|python experience(?: \(years\))?)',
    }
    clean=label.strip().rstrip(':* ').strip()
    for key,pattern in patterns.items():
        if profile.get(key) and re.fullmatch(pattern,clean,re.I): return str(profile[key]),'profile:'+key
    return None
