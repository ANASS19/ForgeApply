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
