# SPDX-FileCopyrightText: 2026 Anass Nassiri and contributors
# SPDX-License-Identifier: Apache-2.0
"""Bounded local document extraction. Extracted text is unverified source material."""
import hashlib
from pathlib import Path
import zipfile
from xml.etree import ElementTree


def extract_text(path:Path) -> dict:
    if not path.is_file(): raise ValueError('Document is not available locally')
    if path.stat().st_size>8_000_000: raise ValueError('Document exceeds the 8 MB extraction limit')
    pages=None
    if path.suffix.lower()=='.pdf':
        from pypdf import PdfReader
        try:
            reader=PdfReader(path,strict=True)
            if reader.is_encrypted: raise ValueError('Unlock the PDF locally before importing it')
            pages=len(reader.pages)
            if pages>20: raise ValueError('Preview supports up to 20 PDF pages')
            text='\n'.join(page.extract_text() or '' for page in reader.pages)
        except ValueError: raise
        except Exception as exc: raise ValueError('PDF text could not be extracted; verify the file locally') from exc
    elif path.suffix.lower()=='.docx':
        try:
            with zipfile.ZipFile(path) as archive:
                if sum(info.file_size for info in archive.infolist())>20_000_000: raise ValueError('DOCX decompressed size exceeds the preview limit')
                xml=archive.read('word/document.xml')
                if len(xml)>3_000_000: raise ValueError('DOCX document XML exceeds the preview limit')
            root=ElementTree.fromstring(xml)
            ns='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
            text='\n'.join(''.join(t.text or '' for t in p.iter(ns+'t')) for p in root.iter(ns+'p'))
        except (zipfile.BadZipFile,KeyError,ElementTree.ParseError) as exc:
            raise ValueError('DOCX text could not be extracted; verify the file locally') from exc
    else: raise ValueError('Only PDF and DOCX preview is supported')
    return {'filename':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'pages':pages,
            'text':text[:50000],'truncated':len(text)>50000,'verified_facts':False,
            'note':'Extraction does not verify qualifications, dates, languages or legal status. Review source conflicts manually.'}


def render_reviewed_pdf(text:str,kind:str='cv') -> bytes:
    """Render already reviewed plain text locally. Text is escaped, never interpreted as HTML."""
    from io import BytesIO
    from xml.sax.saxutils import escape
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
    if not text.strip() or len(text)>30000:raise ValueError('Provide 1-30000 characters of reviewed text')
    font_dir=Path(reportlab.__file__).parent/'fonts'
    # Font registration is idempotent; bundled fonts keep Windows/Linux output consistent.
    pdfmetrics.registerFont(TTFont('ForgeSans',str(font_dir/'Vera.ttf')))
    pdfmetrics.registerFont(TTFont('ForgeSansBold',str(font_dir/'VeraBd.ttf')))
    body=ParagraphStyle('body',fontName='ForgeSans',fontSize=10,leading=15,spaceAfter=3,splitLongWords=True)
    heading=ParagraphStyle('heading',parent=body,fontName='ForgeSansBold',fontSize=11,spaceBefore=9,spaceAfter=5,keepWithNext=True,textColor='#193b62')
    title=ParagraphStyle('title',parent=body,fontName='ForgeSansBold',fontSize=19,leading=24,spaceAfter=8)
    buffer=BytesIO();story=[];first=True
    for line in text.replace('\r\n','\n').split('\n'):
        if not line.strip():story.append(Spacer(1,6));continue
        section=kind=='cv' and line.isupper() and len(line)<70
        style=title if first and kind=='cv' else heading if section else body
        story.append(Paragraph(escape(line),style));first=False
    document=SimpleDocTemplate(buffer,pagesize=A4,leftMargin=43,rightMargin=43,topMargin=40,bottomMargin=40,
                               title='Curriculum Vitae' if kind=='cv' else 'Motivation letter',author='ForgeApply')
    document.build(story)
    return buffer.getvalue()
