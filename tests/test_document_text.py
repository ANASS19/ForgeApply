import zipfile
from pypdf import PdfWriter
import pytest
from forgeapply.document_text import extract_text


def test_local_pdf_metadata_never_promotes_extracted_facts(tmp_path):
    path=tmp_path/'synthetic.pdf'
    writer=PdfWriter();writer.add_blank_page(width=300,height=300)
    with path.open('wb') as stream: writer.write(stream)
    result=extract_text(path)
    assert result['pages']==1 and result['sha256']
    assert result['verified_facts'] is False


def test_docx_text_and_malformed_container(tmp_path):
    path=tmp_path/'synthetic.docx'
    with zipfile.ZipFile(path,'w') as archive:
        archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Synthetic candidate only</w:t></w:r></w:p></w:body></w:document>')
    assert extract_text(path)['text']=='Synthetic candidate only'
    path.write_bytes(b'not a zip')
    with pytest.raises(ValueError,match='DOCX'): extract_text(path)
