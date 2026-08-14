# Security policy

## Supported version

Only the newest 0.1.x alpha receives fixes. This alpha is not suitable for safety-critical or emergency use.

## Report a vulnerability

Do not publish credentials, precise private locations or exploit details in a public issue. Send security reports privately to `sylithtech.contact@gmail.com` with the subject `Meteo security report`. Include reproduction steps, affected version and impact, but remove personal weather locations unless strictly necessary.

## Current controls

- HTTPS-only provider transport.
- Same-origin HTTPS-only redirects; HTTP downgrades and cross-origin redirects are rejected.
- Timeouts and a 5 MB JSON response limit enforced again after HTTP decompression.
- No automatic telemetry.
- No account or authentication service.
- No storage of API keys.
- Custom-provider network activation is disabled in the public alpha; its inactive parser uses restricted, non-executable mappings and rejects non-public DNS results.
- NWS-derived forecast URLs are pinned to `api.weather.gov`; alert links are limited to trusted `weather.gov` hosts.
- Private, atomic application-data writes and bounded offline-cache lifetime.
- Numeric finite/range validation for provider values and stored coordinates.
- Flatpak sandbox with only network, display and graphics permissions.
- Diagnostics omit stable device identifiers and require review/consent.
- Rust coordinate validation and weighted arithmetic in official builds, with a safe Python fallback.

## Known limits

- Weather coordinates are necessarily disclosed to selected providers.
- Public provider uptime and response integrity are outside Sylith’s control.
- Custom-provider activation remains blocked until the validated DNS address can be pinned to the TLS connection without weakening hostname verification.
- There is no signed release or reproducible-build attestation yet.
