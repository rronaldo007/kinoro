#!/bin/bash
# Dev-mode handler for kinoro:// URLs on Linux.
#
# When the user clicks an "Ouvrir dans l'éditeur" link in the browser,
# xdg-open resolves the MimeType via the .desktop file installed at
# ~/.local/share/applications/kinoro-dev.desktop, which Exec's this script
# with the URL as $1. We forward it to the kinoro/app Electron instance.
#
# Because kinoro/app/src/main.ts calls requestSingleInstanceLock(), if
# Kinoro is already running the second launch hits the lock and fires
# 'second-instance' on the running process, which dispatches the URL to
# the renderer. If nothing is running, this launches a fresh Kinoro.

set -e

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"

# electron is installed per-project; use the local binary without npx to
# keep startup under ~1s.
exec ./node_modules/.bin/electron . --no-sandbox "$@"
