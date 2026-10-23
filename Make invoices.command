#!/bin/zsh
# Double-click in Finder to make this month's invoices.
# Keep this file next to make_invoices.py: it runs the copy beside itself.

# A window opened from Finder may not have Homebrew on its PATH yet.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

cd "${0:A:h}" || exit 1

while true; do
  if ! command -v uv >/dev/null; then
    echo "uv is not installed. Install it once with:  brew install uv pango"
  else
    uv run make_invoices.py
  fi

  # Wait for r, so a fix in Notion can be pasted and tried again without
  # going back to Finder. Other keys do nothing; closing the window ends it.
  # If there is no keyboard to read from, read fails and the loop ends.
  print -n "\nPress r to run again, or close this window. "
  while read -s -k 1 key; do
    [[ $key == [rR] ]] && { clear; continue 2; }
  done
  exit
done
