import re
from forgeapply.candidate import screening_answers


def test_answers_are_narrow_and_unknowns_absent():
    rows=screening_answers({'first_name':'Fixture','last_name':'Candidate','email':'fixture@example.org',
                           'years_ai':'2','years_python':'','city':'Milano','country':'Italy'},
                          {'education':[{'level':'masters','completed':True}],
                           'languages':{'Italian':'Beginner','English':'Advanced / C1'}})
    def answers(question):
        return [r['answer'] for r in rows if re.search(r['pattern'],question,re.I)]
    assert answers('Full name')==['Fixture Candidate']
    assert answers('How many years of AI experience?')==['2']
    assert answers('Highest completed education')==["Master's degree"]
    assert answers('Italian language proficiency')==['Beginner']
    for question in ('Years of Python experience','Visa sponsorship','Country of citizenship',
                     'Country you are authorized to work in','I certify my full name is correct',
                     'Expected salary','Disability status','Criminal history',
                     'Years of AI experience with TensorFlow','Professional Italian required: do you qualify?'):
        assert answers(question)==[]


def test_no_degree_answer_without_completed_degree():
    assert screening_answers({}, {'education':[{'level':'masters','completed':False}]})==[]
