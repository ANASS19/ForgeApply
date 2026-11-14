# SPDX-FileCopyrightText: 2026 Anass Nassiri and contributors
# SPDX-License-Identifier: Apache-2.0
"""Optional local OCR via an installed Tesseract executable, never a remote service."""
from pathlib import Path
import shutil
import subprocess


def local_ocr(path:Path) -> dict:
    executable=shutil.which('tesseract')
    if not executable:
        raise RuntimeError('Local OCR requires Tesseract on PATH. Install Tesseract OCR, restart ForgeApply, or explicitly choose vision OCR.')
    result=subprocess.run([executable,str(path),'stdout','--psm','11'],capture_output=True,
                          text=True,encoding='utf-8',timeout=30,check=False,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        raise RuntimeError('Tesseract OCR failed; check the local installation and language data')
    return {'text':result.stdout[:30000],'engine':'tesseract-local','needs_review':True}
