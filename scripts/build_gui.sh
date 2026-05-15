#!/usr/bin/env bash
# Build the GUI frontend bundle into src/instantdemo/server/web/.
# Output is gitignored; the pip wheel includes it via hatch force-include.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root/frontend"

echo "Installing frontend dependencies..."
npm install --silent

echo "Building frontend..."
npm run build

echo "Built → $repo_root/src/instantdemo/server/web/"
