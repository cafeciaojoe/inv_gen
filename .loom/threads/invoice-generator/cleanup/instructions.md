# Clean up everything

Last stitch. Leave nothing behind that the build or testing created. Look at each
target before deleting, and confirm with Joe before removing anything outside the
repo or the scratchpad.

- [ ] Scratchpad files (demo folders, rendered samples)
- [ ] Throwaway packages in uv's cache (as was done for PyMuPDF)
- [ ] `.pytest_cache`, `__pycache__`
- [ ] Any draft preview folders left in the system temp directory by test runs
- [ ] `git status` is clean; the brief and `resources/` are untouched
