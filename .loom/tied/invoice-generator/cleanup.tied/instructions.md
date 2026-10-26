# Clean up everything

Last stitch. Leave nothing behind that the build or testing created. Look at each
target before deleting, and confirm with Joe before removing anything outside the
repo or the scratchpad.

- [x] Scratchpad files (demo folders, rendered samples)
- [x] `resources/style-options/` and `resources/samples/` (sample PDFs; ask Joe first). Joe chose to delete everything in `resources/` but the latest brief.
- [x] Throwaway packages in uv's cache (as was done for PyMuPDF)
- [x] `.pytest_cache`, `__pycache__`
- [x] Any draft preview folders left in the system temp directory by test runs
- [x] `git status` is clean; the latest brief is kept
