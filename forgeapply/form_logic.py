"""Shared deterministic fact mapping for managed browser and extension preparation."""
import re
import unicodedata
from urllib.parse import urlsplit
from .store import PROFILE_REFERENCE_FIELDS,PROFILE_BINDABLE_FIELDS

SENSITIVE_QUESTION=re.compile(
    r'visa|sponsor|work.?authori[sz]|authori[sz].{0,35}work|eligible.{0,35}work|legally.{0,25}work|work permit|right to work|permesso|criminal|disab|convict|'
    r'certif(?:y|ico)|declar|attest|consent|agree|privacy|gender|ethnic|veteran|'
    r'salary|compensation|hourly rate|daily rate|notice period|availability|start date|immediately|citizenship|nationality|reasonable accommodation|'
    r'autorizz.*lavor|diritto.*lavor|visto|sponsoriz|retribuz|stipendio|salario|compenso|remuneraz|tariffa|\bral\b|preavviso|categorie protette|'
    r'disponibilit|disponibile.*(?:lavor|trasfer)|relocation|data di inizio|dichiar|consenso|accetto|acconsento|trattamento.*dati|disabilit|penal|condann|'
    r'cittadinanza|nazionalit|genere|sesso|etni|religio|orientation|orientamento|passport|social security|\bssn\b|tax id|codice fiscale|carta.*identit|documento.*identit|\biban\b|bank account',re.I)

REQUIRED_MARKER=re.compile(r'(?:\s*[*＊]+\s*(?:(?:campo\s+)?(?:obbligatori[oa]|required|mandatory|obligatoire))?|\s*[\[(]\s*(?:campo\s+)?(?:obbligatori[oa]|required|mandatory|obligatoire)\s*[\])])\s*[:.]*\s*$',re.I)


def normalize_label(label:str) -> str:
    """Remove presentation-only required markers, without deleting qualification wording."""
    clean=' '.join(unicodedata.normalize('NFKC',label).split()).strip().rstrip(':').strip()
    return REQUIRED_MARKER.sub('',clean).strip().rstrip(':').strip()


def required_label(label:str) -> bool:
    return bool(REQUIRED_MARKER.search(label))


def _known_text_answer(field:dict,profile:dict,answers:list[dict],context:dict|None=None) -> tuple[str,str]|None:
    label=field.get('label') or field.get('name') or field.get('id') or ''
    if field.get('cross_origin') or field.get('value') or field.get('type') in ('file','password','hidden','submit','button','checkbox','radio'):
        return None
    if sensitive_field(field): return None
    clean=normalize_label(label)
    for saved in answers:
        if not saved.get('enabled',True): continue
        if saved.get('scope_host') and saved['scope_host']!=urlsplit(field.get('url','')).hostname:continue
        try:
            if re.search(saved['pattern'],clean,re.I):
                path=saved.get('fact_path','')
                if path:
                    key=path.removeprefix('profile.')
                    if path=='profile.'+key and key in PROFILE_BINDABLE_FIELDS and profile.get(key):return str(profile[key]),'profile:'+key
                    continue
                return str(saved['answer']),'saved_answer'
        except re.error: continue
    if re.fullmatch(r'prefisso(?: telefonico| internazionale)?|country(?:/territory)? phone code|phone country code|calling code|phone prefix',clean,re.I):
        phone=re.sub(r'\s|[().-]','',profile.get('phone',''))
        if re.fullmatch(r'\+\d+',phone):
            candidates=[(code[0],option) for option in field.get('options',[]) if not option.get('disabled')
                        for code in re.finditer(r'\+\d{1,4}\b',option.get('label','')) if phone.startswith(code[0])]
            longest=max((len(code) for code,_ in candidates),default=0)
            matches=[option for code,option in candidates if len(code)==longest]
            if len(matches)==1:return matches[0]['label'],'profile:phone-country-code'
    patterns={
        'first_name':r'first[ _-]?name|given name(?:\(s\))?|nome', 'last_name':r'last[ _-]?name|family name|surname|cognome',
        'email':r'e[ _-]?mail(?: address)?|indirizzo email',
        'phone':r'(?:phone|mobile|telephone|telefono|cellulare)(?: number)?|numero (?:di )?(?:telefono|cellulare)',
        'linkedin':r'linkedin(?: (?:url|profile))?|(?:profilo|link) linkedin|social (?:network url|profile(?: url)?)', 'github':r'github(?: (?:url|profile))?|(?:profilo|link) github',
        'portfolio':r'portfolio(?: personale)?|(?:personal )?website|sito web(?: personale)?',
        'city':r'(?:current )?(?:city|location)|(?:città|comune)(?: di residenza)?',
        'country':r'(?:current )?country(?: of residence)?|country\s*/\s*territory|(?:paese|nazione)(?: di residenza)?',
        'current_title':r'current (?:job )?title|qualifica professionale|titolo professionale',
        'street_address':r'(?:street |residential )?address|address line 1|indirizzo(?: di residenza| riga 1)?|via\s*/\s*piazza',
        'postal_code':r'postal code|zip(?: code)?|cap|codice postale',
        'province':r'province|provincia|state\s*/\s*province',
        'years_ai':r'(?:how many )?years(?: of)? (?:ai|artificial intelligence) experience\??|ai experience(?: \(years\))?|(?:quanti )?anni di esperienza (?:in |con )?(?:ai|intelligenza artificiale)\??',
        'years_python':r'(?:how many )?years(?: of)? python experience\??|python experience(?: \(years\))?|(?:quanti )?anni di esperienza (?:in |con )?python\??',
    }
    for key,pattern in patterns.items():
        if profile.get(key) and re.fullmatch(pattern,clean,re.I): return str(profile[key]),'profile:'+key
    if re.fullmatch(r'full[ _-]?name|nome completo|nome e cognome|nominativo',clean,re.I) and profile.get('first_name') and profile.get('last_name'):
        return profile['first_name']+' '+profile['last_name'],'profile:full_name'
    context=context or {}
    completed=[(i,e) for i,e in enumerate(context.get('education',[])) if e.get('completed') is True and e.get('verified') is not False]
    if completed:
        i,education=max(completed,key=lambda pair:{'doctorate':4,'phd':4,'masters':3,'bachelors':2}.get(pair[1].get('level'),1))
        if re.fullmatch(r'highest (?:completed )?(?:degree|education)|highest level of education|level of education|titolo di studi[o]?|titolo di studio più elevato',clean,re.I):
            names={'masters':("Master's degree",'Laurea magistrale'),'bachelors':("Bachelor's degree",'Laurea triennale'),'phd':('Doctorate','Dottorato'),'doctorate':('Doctorate','Dottorato')}
            if education.get('level') in names:
                language=1 if re.search(r'titolo|studio|laurea',clean,re.I) else 0
                return names[education['level']][language],f'context:education.{i}.level'
        if re.fullmatch(r'university|university name|università|ateneo|istituto',clean,re.I) and education.get('institution'):
            return education['institution'],f'context:education.{i}.institution'
        date=education.get('graduated_at','')
        if date and re.fullmatch(r'graduation date|data (?:di )?laurea',clean,re.I): return date,f'context:education.{i}.graduated_at'
        if date and re.fullmatch(r'(?:year of graduation|graduation year|anno (?:di )?laurea)',clean,re.I): return date[:4],f'context:education.{i}.graduated_at'
    for name,aliases in {'English':'english|inglese','Italian':'italian|italiano','French':'french|francese','Arabic':'arabic|arabo'}.items():
        if re.fullmatch(rf'(?:{aliases})(?: language)? (?:proficiency|level|fluency)|(?:livello(?: di conoscenza)?|conoscenza)(?: (?:di|della lingua))? (?:{aliases})',clean,re.I):
            level=context.get('languages',{}).get(name)
            if level:return level,'context:languages.'+name
    return None


def _choice_key(value:str) -> str:
    value=normalize_label(value).casefold().strip()
    cefr=re.search(r'\b([abc][12])\b',value)
    if cefr:return 'cefr:'+cefr[1]
    aliases={'italy':'italia','it':'italia','mi':'milano','english':'inglese','italian':'italiano','french':'francese','arabic':'arabo','beginner':'principiante','advanced':'avanzato','native':'madrelingua','native or bilingual':'madrelingua','yes':'true','si':'true','sì':'true','on':'true','1':'true',
             'no':'false','off':'false','0':'false',"master's degree":'masters','laurea magistrale':'masters',
             "bachelor's degree":'bachelors','laurea triennale':'bachelors'}
    return aliases.get(value,value)


def matching_choice(answer:str,options:list[dict]) -> dict|None:
    """Use explicit equivalent labels/codes; never guess a proficiency level or option."""
    key=_choice_key(answer)
    matches=[o for o in options if not o.get('disabled') and o.get('value') and
             key in (_choice_key(o.get('label','')),_choice_key(o['value']))]
    return matches[0] if len(matches)==1 else None


def verified_records(context:dict,section:str) -> list[tuple[int,dict]]:
    items=([context.get('language_details',{}).get(name,{})|{'name':name,'level':level} for name,level in context.get('languages',{}).items()]
           if section=='languages' else context.get(section,[]))
    return [(i,r) for i,r in enumerate(items) if r.get('verified') is not False
            and (r.get('completed') is True if section=='education' else r.get('current_employment_verified') is not False)]


def verified_skills(context:dict) -> list[str]:
    return list(dict.fromkeys(skill for group,values in context.get('skills',{}).items()
                if group not in ('learning','planned','independent_learning') for skill in values if isinstance(skill,str) and skill.strip()))


def record_data(context:dict,section:str,index:int) -> dict:
    if section=='languages':
        name=list(context.get('languages',{}))[index]
        return context.get('language_details',{}).get(name,{})|{'name':name,'level':context['languages'][name]}
    return context[section][index]


def record_storage(context:dict,section:str,index:int) -> dict:
    if section=='languages':return context.setdefault('language_details',{}).setdefault(list(context['languages'])[index],{})
    return context[section][index]


def bind_records(fields:list[dict],context:dict) -> dict:
    """Match populated rows by explicit identity, then allocate empty rows without duplicates."""
    bindings={}
    for section in ('experience','education','languages','certifications'):
        rows={}
        for f in fields:
            if f.get('section')==section and f.get('record_index') is not None:rows.setdefault(f['record_index'],[]).append(f)
        records=verified_records(context,section);used=set();blanks=[];conflict=False
        for row,items in sorted(rows.items()):
            identity={k:v for f in items for k,v in f.get('record_identity',{}).items() if v}
            if not identity:
                if any(f.get('checked') if f.get('type') in ('checkbox','radio') else f.get('value') for f in items):bindings[(section,row)]=None;conflict=True
                else:blanks.append(row)
                continue
            matches=[i for i,r in records if all(str(r.get(k,'')).strip().casefold()==v.strip().casefold() for k,v in identity.items()) and i not in used]
            if len(matches)==1:bindings[(section,row)]=matches[0];used.add(matches[0])
            else:bindings[(section,row)]=None;conflict=True
        for row in blanks:
            remaining=[i for i,_ in records if i not in used]
            index=remaining[0] if remaining and not conflict else None
            bindings[(section,row)]=index
            if index is not None:used.add(index)
    return bindings


def record_answer(field:dict,context:dict) -> tuple[str,str]|None:
    section=field['section'];row=field.get('record_index')
    if row is None or field.get('value') or field.get('cross_origin') or field.get('type') in ('file','password','checkbox','radio'):return None
    index=context.get('_form_bindings',{}).get((section,row))
    if index is None:return None
    record=record_data(context,section,index);label=normalize_label(field.get('label',''))
    remembered=record.get('form_answers',{}).get(record_question_key(label))
    if isinstance(remembered,dict) and remembered.get('value'):return remembered['value'],f'context:{section}.{index}.reviewed_answer'
    patterns=({'title':r'job title|role|ruolo|qualifica','employer':r'company|employer|azienda|datore di lavoro',
               'summary':r'role description|job description|description|descrizione(?: del ruolo)?',
               'location':r'location|sede|localit[aà]'} if section=='experience' else
              {'institution':r'school or university|school|university|istituto|universit[aà]|scuola o universit[aà]',
               'degree':r'field of study|major|area di studio|corso di studi','grade':r'overall result.*|voto(?: finale)?','gpa':r'gpa|grade point average'} if section=='education' else
              {'name':r'language|lingua','level':r'(?:overall )?(?:proficiency|level)|livello(?: generale)?',
               'speaking':r'speaking|orale|parlato','reading':r'reading|lettura','writing':r'writing|scrittura','comprehension':r'comprehension|comprensione'} if section=='languages' else
              {'name':r'certification|certification name|certificate|certificazione|nome certificazione',
               'issuer':r'issuer|issued by|issuing organization|ente(?: certificatore)?','credential_id':r'credential id|certification number|numero certificazione',
               'url':r'credential url|certification url|url certificazione','issued_at':r'issue date|data (?:di )?rilascio',
               'expires_at':r'expiration date|expiry date|data (?:di )?scadenza'})
    for key,pattern in patterns.items():
        if re.fullmatch(pattern,label,re.I) and record.get(key):return str(record[key]),f'context:{section}.{index}.{key}'
    if section=='education' and re.fullmatch(r'degree|titolo di studio|titolo',label,re.I):
        names={'masters':"Master's degree",'bachelors':"Bachelor's degree",'doctorate':'Doctorate','phd':'Doctorate'}
        if record.get('level') in names:return names[record['level']],f'context:education.{index}.level'
    start=re.fullmatch(r'(?:from|start(?: date)?|data (?:di )?inizio|issue(?: date)?|data (?:di )?rilascio)(?: (?:month|year|mese|anno))?',label,re.I)
    end=re.fullmatch(r'(?:to|end(?: date)?|data (?:di )?fine|graduation|expiry|expiration(?: date)?|data (?:di )?scadenza)(?: (?:month|year|mese|anno))?',label,re.I)
    if start or end:
        date=record.get('start_date',record.get('start','')) if start else record.get('end_date',record.get('end',record.get('graduated_at','')))
        if section=='certifications':date=record.get('issued_at' if start else 'expires_at','')
        if not date and section=='education':date=record.get('start_year' if start else 'end_year','')
        date=str(date)
        if re.fullmatch(r'\d{4}(?:-\d{2}(?:-\d{2})?)?',date):
            if re.search(r'year|anno',label,re.I):date=date[:4]
            elif re.search(r'month|mese',label,re.I):
                if len(date)<7:return None
                date=str(int(date[5:7]))
                if field.get('automation_id')=='dateSectionMonth-input':date=date.zfill(2)
            if field.get('type')=='date' and len(date)!=10:return None
            if field.get('type')=='month':
                if len(date)<7:return None
                date=date[:7]
            return date,f'context:{section}.{index}.date'
    return None


def record_question_key(label:str) -> str:
    clean=normalize_label(label)
    for prefix,pattern in [('start',r'from|start(?: date)?|data (?:di )?inizio'),('end',r'to|end(?: date)?|data (?:di )?fine|graduation')]:
        match=re.fullmatch(rf'(?:{pattern})(?: (month|year|mese|anno))?',clean,re.I)
        if match:return prefix+'_'+({'month':'month','mese':'month','year':'year','anno':'year'}.get((match[1] or '').lower(),'date'))
    return clean.casefold()


def sensitive_field(field:dict) -> bool:
    text=' '.join(str(field.get(k,'')) for k in ('label','group_label','name','id'))
    historical_date=field.get('section') in ('education','experience') and record_question_key(field.get('label','')) in {
        'start_date','start_year','start_month','end_date','end_year','end_month'}
    return any(not(historical_date and m[0].casefold() in ('start date','data di inizio')) for m in SENSITIVE_QUESTION.finditer(text))


def known_answer(field:dict,profile:dict,answers:list[dict],context:dict|None=None) -> tuple[str,str]|None:
    context=context or {};typ=field.get('type')
    # Repair only invalid values that still exactly match a verified profile fact.
    # This covers a previously typed search term and an international number in a national-only field.
    if field.get('value') and not field.get('valid',True) and (field.get('selection_required') or field.get('phone_prefix')):
        fact=_known_text_answer(field|{'value':''},profile,[],context)
        if fact and fact[1]=='profile:phone' and field.get('phone_prefix'):
            digits=re.sub(r'[^\d+]','',fact[0]);current=re.sub(r'[^\d+]','',field['value']);prefix=field['phone_prefix']
            if digits==current and digits.startswith(prefix):return digits[len(prefix):],fact[1]
        elif fact and field.get('selection_required') and _choice_key(fact[0])==_choice_key(field['value']):return fact
    if field.get('section') in ('experience','education','languages','certifications'):
        if sensitive_field(field):return None
        if typ=='radio':
            if field.get('checked') or field.get('group_answered'):return None
            fact=record_answer(field|{'label':field.get('group_label',''),'value':'','type':'text'},context)
            option=matching_choice(fact[0],field.get('options',[])) if fact else None
            return ('true',fact[1]) if option and option['value']==field.get('value') else None
        if typ=='checkbox':
            if field.get('checked') or field.get('cross_origin'):return None
            index=context.get('_form_bindings',{}).get((field['section'],field.get('record_index')))
            if index is None:return None
            record=record_data(context,field['section'],index);label=normalize_label(field.get('label',''))
            if field['section']=='experience' and re.fullmatch(r'I currently work here|attualmente lavoro qui',label,re.I) and record.get('currently_work_here') is True:return 'true','context:current-employment-explicit'
            if field['section']=='languages' and re.fullmatch(r'native|mother tongue|madrelingua',label,re.I) and (record.get('native') is True or re.search(r'\bnative\b|madrelingua',record.get('level',''),re.I)):return 'true','context:explicit-native-language'
            return None
        fact=record_answer(field,context)
        if fact and typ=='select' and field.get('options'):
            option=matching_choice(fact[0],field['options'])
            return (option['label'],fact[1]) if option else None
        return fact
    if typ in ('checkbox','radio'):
        if field.get('checked') or field.get('cross_origin') or field.get('group_answered'):return None
        combined=' '.join(field.get(k,'') for k in ('label','group_label','name','id'))
        if SENSITIVE_QUESTION.search(combined):return None
        if typ=='checkbox':
            fact=_known_text_answer(field|{'type':'text','value':''},profile,answers,context)
            if fact and _choice_key(fact[0]) in ('true','false'):return _choice_key(fact[0]),fact[1]
            # A checked technology represents possession of a verified skill, not willingness/consent.
            if re.fullmatch(r'(?:technical )?skills|technologies|competenze(?: tecniche)?|tecnologie',field.get('group_label',''),re.I):
                skills=[s for group,values in context.get('skills',{}).items() if group not in ('independent_learning','planned','learning') for s in values]
                if normalize_label(field.get('label','')).casefold() in [s.casefold() for s in skills]:return 'true','context:skills'
            return None
        question=field.get('group_label','')
        if not question:return None
        fact=_known_text_answer(field|{'type':'text','label':question,'value':''},profile,answers,context)
        if not fact:return None
        option=matching_choice(fact[0],field.get('options',[]))
        if option and option['value']==field.get('value'):return 'true',fact[1]
        return None
    fact=_known_text_answer(field,profile,answers,context)
    if fact and fact[1]=='profile:phone' and field.get('phone_prefix'):
        digits=re.sub(r'[^\d+]','',fact[0]);prefix=field['phone_prefix']
        if digits.startswith(prefix):fact=(digits[len(prefix):],fact[1])
    if fact and typ in ('select','combobox') and field.get('options'):
        option=matching_choice(fact[0],field['options'])
        if not option:return None
        return option.get('label') or option['value'],fact[1]
    return fact
