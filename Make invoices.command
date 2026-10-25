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
  # going back to Finder, or Enter to end the script. Ending it here means the
  # window then closes without Terminal asking to terminate a running process.
  # Other keys do nothing. If there is no keyboard to read from, read fails
  # and the loop ends.
  print -n "\nPress r to run again, or Enter to exit the script. "
  while read -s -k 1 key; do
    [[ $key == [rR] ]] && { clear; continue 2; }
    [[ $key == $'\n' || $key == $'\r' ]] && { echo; exit 0; }
  done
  exit
done
