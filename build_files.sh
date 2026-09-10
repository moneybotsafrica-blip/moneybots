#!/bin/bash
# Vercel static build step: install dependencies and collect Django static
# files into staticfiles/ (served via the /static/ route in vercel.json).
set -e

# Vercel's build Python is managed by uv (PEP 668), so allow installs into it.
export PIP_BREAK_SYSTEM_PACKAGES=1

python3 -m pip install --upgrade pip --break-system-packages
python3 -m pip install -r requirements.txt --break-system-packages

# SECRET_KEY is only needed so settings import cleanly during the build.
SECRET_KEY="${SECRET_KEY:-build-time-placeholder}" python3 manage.py collectstatic --noinput --clear
