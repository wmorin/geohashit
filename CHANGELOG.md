# Changelog

## v0.1.1 - 2026-07-05

- Added a 50,000-cell geohash coverage cap so oversized high-precision requests
  fail before producing very large responses.
- Bounded the in-memory Nominatim cache to 512 entries with a one-hour TTL.
- Hardened GitHub Actions by pinning action SHAs, separating Docker build and
  publish permissions, and adding CODEOWNERS for workflow changes.

## v0.1.0 - 2026-07-03

- Initial release.
