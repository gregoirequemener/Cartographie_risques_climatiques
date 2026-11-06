#!/bin/bash
# Construit la carte depuis les sources (src/ + data/) puis l'ouvre dans le navigateur.
# Double-clic dans le Finder, ou : ./lancer.command
cd "$(dirname "$0")" || exit 1

stop() { # garde la fenêtre ouverte pour laisser lire le message
  echo
  echo "$1"
  read -r -p "Appuyez sur Entrée pour fermer cette fenêtre… " _
  exit 1
}

command -v python3 >/dev/null 2>&1 || stop "Python 3 est introuvable : installez-le (https://www.python.org/downloads/) puis relancez."
python3 build.py || stop "La construction de la carte a échoué : voir le message ci-dessus."
open docs/index.html
