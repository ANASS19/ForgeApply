# SPDX-FileCopyrightText: 2026 Anass Nassiri and contributors
# SPDX-License-Identifier: Apache-2.0
"""Bilingual drafts built from verified structured facts, without model inference."""
from __future__ import annotations
import re
from .form_logic import normalize_label,SENSITIVE_QUESTION


def response_language(label:str='',page_language:str='',preferred:str='auto') -> str:
    if preferred in ('en','it'): return preferred
    if re.search(r'lettera|motivazion|presentazion|perch[eé]|parlaci|descriv|competenze|esperienz|formazion|italiano|candidatur',label,re.I): return 'it'
    if re.search(r'cover letter|motivation|why |tell us|describe|yourself|skills|experience|education|background',label,re.I): return 'en'
    return 'it' if page_language.lower().startswith('it') else 'en'


def question_kind(label:str) -> str|None:
    if SENSITIVE_QUESTION.search(label): return None
    label=normalize_label(label)
    if re.search(r'cover[ _-]?letter|motivation(?:al)? (?:letter|statement)|lettera (?:di )?(?:motivazione|presentazione)|lettera motivazionale|why.*(?:apply|position|role|company)|perch[eé].*(?:candid|posizion|ruolo)|motivazion.*candidatur|^(?:motivation|motivazione)$|messaggio (?:al|per il) (?:recruiter|selezionatore)',label,re.I): return 'motivation'
    if re.search(r'tell us about yourself|professional (?:summary|background)|parlaci di te|presentati|profilo professionale|descriv.*esperienz|describe.*experience|esperienze professionali',label,re.I): return 'background'
    if re.fullmatch(r'(?:technical |relevant )?skills|competenze(?: tecniche| professionali)?|descrivi le tue competenze',label,re.I): return 'skills'
    if re.fullmatch(r'education(?:al)? (?:summary|background)|formazione(?: accademica| professionale)?|percorso (?:di studi|formativo)',label,re.I): return 'education'
    return None


def needs_exact_fact(label:str) -> bool:
    return application_specific_question(label) or bool(re.search(r'how many|quanti|quante|anni.*esperienz|years.*experience|exact.*years|\bdata\b|\bdate\b|birth|nascita|salary|retribuz|address|indirizzo|postal|\bcap\b|\bzip\b|ever worked|previously employ|hai.*lavorato|lavorato.*(?:presso|per)|province|provincia|via\s*/\s*piazza|domicilio|residenza',label,re.I))


def application_specific_question(label:str) -> bool:
    """Referral sources describe this application, not a permanent candidate fact."""
    return bool(re.search(r'how did.*hear|come.*conosciut|come.*trovat.*(?:annuncio|posizione)|^(?:canale(?: di provenienza)?|fonte|source)$',normalize_label(label),re.I))


def evidence_catalog(profile:dict,context:dict) -> list[dict]:
    """Only explicit facts, excluding unverified/current-status conflicts and local paths."""
    facts=[{'id':'profile.'+key,'value':value} for key,value in profile.items() if value and not key.startswith('resume_')]
    for group in ('education','experience','certifications'):
        for i,item in enumerate(context.get(group,[])):
            if item.get('verified') is False or item.get('current_employment_verified') is False: continue
            facts.append({'id':f'{group}.{i}','value':{k:v for k,v in item.items() if k not in ('source','verified_at')}})
    skills={k:v for k,v in context.get('skills',{}).items() if k not in ('independent_learning','planned','learning')}
    if skills:facts.append({'id':'skills','value':skills})
    if context.get('languages'):facts.append({'id':'languages','value':context['languages']})
    return facts


def retrieve_reviewed_answers(questions:list[dict],answers:list[dict],profile:dict,*,limit:int=8) -> list[dict]:
    """Local lexical retrieval of human-approved answers, with source and scope.

    Retrieved answers support reviewable proposals; they never bypass field type,
    legal declarations, or exact-fact guards. No embeddings or remote index needed.
    """
    tokens=lambda text:set(re.findall(r'[\w]{3,}',text.casefold()))-{'the','and','your','you','are','what','with','this','how','per','con','una','dei','della'}
    query=tokens(' '.join(q.get('label','') for q in questions))
    ranked=[]
    for answer in answers:
        pattern=answer.get('pattern','')
        if not answer.get('enabled',True) or not answer.get('source','').startswith('user:') or SENSITIVE_QUESTION.search(pattern):continue
        if re.search(r'why|perch[eé]|company|azienda|this (?:role|position)|quest[oa] (?:ruolo|posizione)|birth|nascita',pattern,re.I):continue
        score=len(query&tokens(pattern))
        if not score:continue
        path=answer.get('fact_path','')
        value=profile.get(path.removeprefix('profile.')) if path.startswith('profile.') else answer.get('answer','')
        if not value:continue
        ranked.append((score,{'id':'reviewed_answer.'+str(answer['id']),
                              'value':{'question':pattern,'answer':str(value)[:8000]},
                              'source':answer['source'],'verified_at':answer.get('verified_at',''),
                              'scope_host':answer.get('scope_host','')}))
    return [fact for _,fact in sorted(ranked,key=lambda item:(-item[0],item[1]['id']))[:limit]]


def fact_fragments(profile:dict,context:dict,language:str,job_context:str='') -> tuple[dict,list[dict]]:
    sources=[];parts={'education':'','experience':'','skills':''}
    for i,education in enumerate(context.get('education',[])):
        if education.get('completed') is not True or education.get('verified') is False: continue
        degree=education.get('degree','');school=education.get('institution','')
        if not degree: continue
        if language=='it':
            level='una laurea magistrale in ' if education.get('level')=='masters' else 'un titolo in '
            text='Ho conseguito '+level+degree+(' presso '+school if school else '')+'.'
        else:
            level="a Master's degree in " if education.get('level')=='masters' else 'a qualification in '
            text='I hold '+level+degree+(' from '+school if school else '')+'.'
        parts['education']=text;sources.append({'id':f'education.{i}','text':text,'source':education.get('source') or context.get('source','user:verified-context')});break
    experiences=[]
    for i,entry in enumerate(context.get('experience',[])):
        if entry.get('verified') is False or entry.get('current_employment_verified') is False: continue
        role=entry.get('title','');employer=entry.get('employer','')
        if not role or not employer: continue
        experiences.append(role+(' presso ' if language=='it' else ' at ')+employer)
        sources.append({'id':f'experience.{i}','text':experiences[-1],'source':entry.get('source') or context.get('source','user:verified-context')})
        if len(experiences)==2: break
    if experiences: parts['experience']=('Ho maturato esperienza nei ruoli di ' if language=='it' else 'My experience includes roles as ')+(' e ' if language=='it' else ' and ').join(experiences)+'.'
    skills=[];groups=[]
    for group,values in context.get('skills',{}).items():
        if group in ('independent_learning','planned','learning'): continue
        groups.append([value for value in values if isinstance(value,str)])
    all_skills=list(dict.fromkeys(skill for group in groups for skill in group))
    relevant=[skill for skill in all_skills if re.search(r'(?<!\w)'+re.escape(skill)+r'(?!\w)',job_context,re.I)]
    balanced=[skill for i in range(2) for group in groups for skill in group[i:i+1]]
    skills=list(dict.fromkeys(relevant+balanced+all_skills))[:8]
    if skills:
        parts['skills']=('Le mie competenze includono ' if language=='it' else 'My skills include ')+', '.join(skills)+'.'
        sources.append({'id':'skills','text':parts['skills'],'source':context.get('source','user:verified-context')})
    return parts,sources


def draft_answer(label:str,profile:dict,context:dict,*,language='auto',page_language='',job_title='',company='',job_description='') -> dict|None:
    kind=question_kind(label)
    if kind is None: return None
    lang=response_language(label,page_language,language)
    parts,sources=fact_fragments(profile,context,lang,job_title+' '+job_description)
    if not sources: return None
    if kind=='skills': body=parts['skills']; sources=[s for s in sources if s['id']=='skills']
    elif kind=='education': body=parts['education']; sources=[s for s in sources if s['id'].startswith('education.')]
    else: body='\n\n'.join(text for text in parts.values() if text)
    if not body: return None
    if kind=='motivation':
        title=job_title.strip()[:160];employer=company.strip()[:120]
        if lang=='it':
            opening='Desidero presentare la mia candidatura'+(' per il ruolo di '+title if title else ' per questa posizione')+(' presso '+employer if employer else '')+'.'
            closing='Sarei lieto di approfondire in un colloquio come il mio percorso possa contribuire alle esigenze del ruolo.'
            body='Gentile team di selezione,\n\n'+opening+'\n\n'+body+'\n\n'+closing+'\n\nCordiali saluti,'
        else:
            opening='I would like to apply'+(' for the '+title+' position' if title else ' for this position')+(' at '+employer if employer else '')+'.'
            closing='I would welcome the opportunity to discuss how my background could contribute to the needs of this role.'
            body='Dear Hiring Team,\n\n'+opening+'\n\n'+body+'\n\n'+closing+'\n\nKind regards,'
        name=' '.join(profile.get(k,'').strip() for k in ('first_name','last_name')).strip()
        if name: body+='\n'+name
    return {'value':body,'kind':kind,'language':lang,'source':'verified_fact_template','facts_used':sources,'needs_review':True}


def draft_resume(profile:dict,context:dict,language:str='en',*,job_description:str='') -> dict|None:
    """A transparent ATS-friendly draft. No employment or skills are inferred from a role title."""
    it=language=='it'
    sources=[];lines=[]
    name=' '.join(profile.get(k,'').strip() for k in ('first_name','last_name')).strip()
    if name:lines.append(name)
    contact=[profile[k] for k in ('email','phone') if profile.get(k)]
    location=', '.join(profile[k] for k in ('city','country') if profile.get(k))
    if location:contact.append(location)
    if contact:lines.append(' | '.join(contact))
    for k in ('linkedin','github','portfolio'):
        if profile.get(k):lines.append(profile[k])
    education=[]
    for i,e in enumerate(context.get('education',[])):
        if e.get('completed') is not True or e.get('verified') is False or not e.get('degree'):continue
        education.append(' - '.join(str(e[k]) for k in ('degree','institution','graduated_at') if e.get(k)))
        if e.get('thesis'):education.append(('Tesi: ' if it else 'Thesis: ')+str(e['thesis']))
        sources.append({'id':f'education.{i}','text':education[-1]})
    experience=[]
    for i,e in enumerate(context.get('experience',[])):
        if e.get('verified') is False or e.get('current_employment_verified') is False or not e.get('title') or not e.get('employer'):continue
        experience.append(e['title']+' - '+e['employer'])
        dates=' - '.join(str(e.get(k) or e.get(alias)) for k,alias in (('start_date','start'),('end_date','end')) if e.get(k) or e.get(alias))
        if dates:experience.append(dates)
        if isinstance(e.get('summary'),str) and e['summary'].strip():experience.append(e['summary'])
        for key in ('responsibilities','achievements'):
            if isinstance(e.get(key),list):experience.extend('- '+x for x in e[key] if isinstance(x,str) and x.strip())
        sources.append({'id':f'experience.{i}','text':e['title']+' - '+e['employer']})
    skills=list(dict.fromkeys(s for group,values in context.get('skills',{}).items() if group not in ('independent_learning','planned','learning') for s in values if isinstance(s,str)))
    # Emphasize existing skills requested by this vacancy, without adding any.
    if job_description:skills.sort(key=lambda skill:not bool(re.search(r'(?<!\w)'+re.escape(skill)+r'(?!\w)',job_description,re.I)))
    if skills:sources.append({'id':'skills','text':', '.join(skills)})
    certificates=[]
    for i,item in enumerate(context.get('certifications',[])):
        if item.get('verified') is False or not item.get('name'):continue
        entry=' - '.join(str(item[k]) for k in ('name','issuer','issued_at') if item.get(k))
        certificates.append(entry);sources.append({'id':f'certifications.{i}','text':entry})
    sections=[('ESPERIENZA PROFESSIONALE' if it else 'PROFESSIONAL EXPERIENCE',experience),
              ('FORMAZIONE' if it else 'EDUCATION',education),('CERTIFICAZIONI' if it else 'CERTIFICATIONS',certificates),
              ('COMPETENZE' if it else 'SKILLS',[', '.join(skills)] if skills else [])]
    for heading,entries in sections:
        if entries:lines+=['',heading]+entries
    languages=context.get('languages',{})
    if languages:
        names={'Italian':'Italiano','English':'Inglese','French':'Francese','Arabic':'Arabo'}
        levels={'Beginner':'Principiante','Advanced':'Avanzato','Native':'Madrelingua','Fluent':'Fluente'}
        entries=[]
        for name,level in languages.items():
            if it:
                name=names.get(name,name)
                for en,translated in levels.items():level=level.replace(en,translated)
            entries.append(f'{name}: {level}')
        lines+=['','LINGUE' if it else 'LANGUAGES']+entries
        sources.append({'id':'languages','text':str(languages)})
    if not sources:return None
    return {'value':'\n'.join(lines),'language':language,'kind':'cv','source':'verified_fact_template',
            'facts_used':sources,'needs_review':True}
