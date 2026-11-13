from types import SimpleNamespace
import pytest
from forgeapply import ocr


def test_missing_local_ocr_has_install_instructions(monkeypatch,tmp_path):
    monkeypatch.setattr(ocr.shutil,'which',lambda name:None)
    with pytest.raises(RuntimeError,match='Install Tesseract'):
        ocr.local_ocr(tmp_path/'image.png')


def test_ocr_uses_argument_list_and_never_shell(monkeypatch,tmp_path):
    monkeypatch.setattr(ocr.shutil,'which',lambda name:'tesseract')
    requests=[]
    def run(args,**kwargs):
        requests.append((args,kwargs))
        return SimpleNamespace(returncode=0,stdout='Fixture text')
    monkeypatch.setattr(ocr.subprocess,'run',run)
    assert ocr.local_ocr(tmp_path/'with spaces.png')['text']=='Fixture text'
    assert requests[0][0][1]==str(tmp_path/'with spaces.png')
    assert not requests[0][1].get('shell')
