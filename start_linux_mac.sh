#!/bin/sh
# SPDX-FileCopyrightText: 2026 Anass Nassiri and contributors
# SPDX-License-Identifier: Apache-2.0
set -eu
cd "$(dirname "$0")"
if [ ! -f .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -U pip
  .venv/bin/python -m pip install -r requirements.txt
  .venv/bin/python -m playwright install chromium
fi
.venv/bin/python -m forgeapply
