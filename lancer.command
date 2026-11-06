#!/bin/bash
# Construit la carte depuis les sources (src/ + data/) puis l'ouvre dans le navigateur.
# Double-clic dans le Finder, ou : ./lancer.command
set -e
cd "$(dirname "$0")"
python3 build.py
open docs/index.html
