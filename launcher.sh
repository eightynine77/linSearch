#!/bin/bash

VENV_DIR="venv"

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Install requirements (pip skips if already satisfied)
python -m pip install -q -r requirements.txt

# Run the Python GUI app
python linSearch.py

deactivate

return 0 2>/dev/null || exit 0