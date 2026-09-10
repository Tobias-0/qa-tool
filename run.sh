#!/bin/bash
set -e

cd "$(dirname "$0")"

# Create virtualenv on first run
if [ ! -d "venv" ]; then
  echo "Setting up for the first time..."
  python3 -m venv venv
  source venv/bin/activate
  pip install -q -r requirements.txt
  echo "Done."
else
  source venv/bin/activate
fi

# Open browser after a short delay
(sleep 1.5 && open http://127.0.0.1:8080) &

python3 app.py
