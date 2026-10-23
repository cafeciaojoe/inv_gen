#!/bin/zsh
# Double-click in Finder to make this month's invoices.
# Keep this file next to make_invoices.py: it runs the copy beside itself.

# A window opened from Finder may not have Homebrew on its PATH yet.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

cd "${0:A:h}" || exit 1

if ! command -v uv >/dev/null; then
  echo "uv is not installed. Install it once with:  brew install uv pango"
else
  uv run make_invoices.py
fi

echo
read -s -k 1 "?Press any key to close this window."
