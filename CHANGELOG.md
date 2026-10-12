# Changelog

## 0.1.3 - 2026-10-12

- Synchronize the CLI version with package metadata and the v0.1.3 release.
- Correct the installation pin and add regression tests for version metadata.
- Run the Python test matrix on both Ubuntu and Windows.

## 0.1.2 - 2026-10-11

- Fix the CI smoke step on Windows: write the JSON report to a workspace file instead of `/tmp`, which does not exist on Windows runners.


## 0.1.1 - 2026-10-11

- CI now also runs the test suite on Windows (windows-latest), not only Ubuntu.


## 0.1.0 - 2026-10-11

- Initial read-only Git history hotspot report for non-merge commits.
- Aggregate added/deleted lines and file-touch counts; omit binary files.
- Add JSON and Markdown output, date windows, path excludes, bounded history, and tests.
