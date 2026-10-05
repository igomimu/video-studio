#!/bin/bash
# Wrapper script for text_generator.py
# Usage: ./gen_text.sh "Your Text" [color] [--font font_path]

DIR="$(cd "$(dirname "$0")" && pwd)"
PY_PATH="$DIR/.venv/bin/python"
[ -x "$PY_PATH" ] || PY_PATH=python3

"$PY_PATH" "$DIR/text_generator.py" "$@"
