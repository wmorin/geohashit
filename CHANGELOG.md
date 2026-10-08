# Changelog

## v0.2.0 - 2026-10-08

- Added a browser-only coverage playground with presets, polygon drawing,
  GeoJSON import, precision and inclusion controls, area tradeoffs, exports,
  reproducible code examples, and shareable preset links.
- Exposed inside, center, and intersect coverage modes through the API while
  preserving legacy behavior when the mode is omitted.
- Added coverage-engine tests and stricter validation and computation budgets.
- Added an MIT license and usage guidance for compact, mixed-length geohashes.

## v0.1.3 - 2026-07-05

- Added app-level Nominatim factory injection so route behavior can be tested
  without monkeypatching module globals.
- Separated Nominatim cache locking from outbound rate-limit locking so waiting
  on upstream requests does not block cache access.
- Hardened Nominatim search response parsing for malformed upstream place rows.
- Simplified geohash coverage traversal so budget accounting happens at one
  emission point.
- Added ruff linting to the GitHub Actions test workflow.

## v0.1.2 - 2026-07-05

- Refactored geohash coverage traversal into explicit coverage-mode handlers.
- Split Nominatim cache and rate-limit responsibilities from lookup behavior.
- Centralized service metadata used by the Flask index and OpenAPI response.

## v0.1.1 - 2026-07-05

- Added a 50,000-cell geohash coverage cap so oversized high-precision requests
  fail before producing very large responses.
- Bounded the in-memory Nominatim cache to 512 entries with a one-hour TTL.
- Hardened GitHub Actions by pinning action SHAs, separating Docker build and
  publish permissions, and adding CODEOWNERS for workflow changes.

## v0.1.0 - 2026-07-03

- Initial release.
