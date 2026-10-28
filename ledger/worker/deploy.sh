#!/usr/bin/env bash
# 確認ページを Cloudflare に配る。ページの中身は telop_questions.py が ../page/site に書く。
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ~/.secrets/cloudflare-ai.env; set +a
export CLOUDFLARE_ACCOUNT_ID=8bbeac0e7a8c5b266888b1dcf5dc862d CLOUDFLARE_API_TOKEN="$CLOUDFLARE_AI_TOKEN"
npx --yes wrangler@4 deploy "$@"
