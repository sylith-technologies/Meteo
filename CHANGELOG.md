# Changelog

All material changes to Meteo are recorded here. Dates use ISO `YYYY-MM-DD`.

## 0.1.0-alpha — 2026-08-13

First public demonstration release. The unreleased `0.2.x` prototype labels were reset to `0.1.0-alpha` before public distribution so the project begins with one coherent version history.

### Product and interface

- Replaced the hard-coded Santiago prototype with first-run manual location search.
- Kept the first-run welcome and its explicit search button visible when the adaptive split view collapses on a narrow screen.
- Added one active location and a strict maximum of five saved locations; a sixth location is refused instead of silently deleting an existing one.
- Made saved locations and search results activate with one click and preserved correct active-location state.
- Added confirmation before removing one location, every location or the offline cache.
- Added current/forecast source labelling so provider forecast data is never presented as an observation, even when the first valid period is later than the next hour.
- Added current conditions, 48-hour hourly view, up-to-15-day daily view and a dependency-free temperature/precipitation graph.
- Combined sunrise and sunset in one compact card.
- Hid the combined sun-times card when a provider supplies neither value, avoiding an all-placeholder panel.
- Added air-quality summary/details, a haze icon, labelled U.S./European AQI categories and restrained semantic card colours.
- Added metric, imperial and locale-derived units plus system/light/dark appearance.
- Added responsive narrow-screen layout, system-theme integration, subtle transitions and high-contrast CSS treatment.
- Made provider credits stack vertically in narrow layouts instead of overflowing the application window.
- Replaced the GTK 4.20-only contrast media query with libadwaita high-contrast state and compatible CSS classes, preserving the declared GTK 4.14 minimum.
- Added accessible names to icon-only controls and an accessible description for the graph; the same graph data remains available as text.
- Localised daily weekday/month labels using Meteo's selected language rather than the operating-system locale.
- Added true singular/plural provider, source, hour and day messages.
- Replaced missing precipitation, apparent temperature and daily extrema with `—`/hidden fields instead of fabricated zeroes.
- Added visible provider credits and CC BY 4.0 data-licence link where applicable.
- Added a visible modification notice when Meteo normalises CC BY provider units/conditions, or combines multiple sources.

### Providers, forecasts and alerts

- Implemented Open-Meteo global weather, 48 hourly entries, 15 daily entries and optional CAMS air-quality retrieval.
- Made Open-Meteo weather and air-quality requests concurrent; an AQI outage no longer hides valid weather.
- Added numeric range/finite checks to reject impossible Open-Meteo values and preserved a missing apparent temperature as missing.
- Preserved a partial Open-Meteo daily maximum/minimum instead of discarding the whole day, and suppressed empty air-quality cards when the API supplies no usable index or pollutant value.
- Implemented MET Norway Locationforecast parsing, attribution and provider-required conditional caching using `Expires`, `Last-Modified`, `If-Modified-Since`, `304` and `Retry-After`.
- Prevented overlapping MET precipitation intervals from being counted repeatedly and split multi-hour accumulations proportionally when they cross local midnight.
- Implemented regional U.S. National Weather Service forecast and official active alerts.
- Marked the NWS first hourly period as a forecast, not an observation.
- Stopped missing NWS temperatures from becoming a false `−17.8 °C`; invalid periods are omitted and a response with no valid hourly temperature fails safely.
- Preserved partial NWS daily extrema as missing when only daytime or nighttime data exists.
- Isolated NWS alert failures so a temporary alert-feed outage does not discard a valid forecast, while showing a distinct non-warning service-status notice instead of implying verified absence of alerts.
- Restricted NWS forecast endpoints to `https://api.weather.gov` and sanitised alert links to trusted `weather.gov` hosts.
- Bounded untrusted alert text and skipped malformed alerts without titles.
- Deduplicated seen official alerts by both authority and alert identifier.
- Kept official alerts outside numerical consensus; forecast-derived storm/rain/wind signals remain clearly non-official and Meteo never infers tornado warnings.
- Kept official authority titles/descriptions verbatim by bypassing gettext for those fields while retaining translation for Meteo-authored forecast signals.
- Removed non-functional Google Weather, Red Meteo Chile and FreeWeatherAPI provider stubs.

### Consensus and data correctness

- Added explicit opt-in weighted consensus over normalised provider models.
- Prevented a single successful source from being labelled consensus.
- Preserved optional/missing values through consensus rather than converting them to zero.
- Corrected zero-MAD outlier handling so a reasonable third forecast is not discarded merely because two values match exactly, while extreme outliers remain filtered.
- Normalised hourly grouping to UTC using each provider timezone, including daylight-saving transitions.
- Used retrieval order to select the observation timestamp and labelled the result as a normalised Meteo combination.
- Kept provider weighting and agreement scores documented as experimental indicators, not scientific accuracy or probability claims.

### Offline storage, privacy and concurrency

- Added persistent offline weather cache with retrieval time, stale state and fallback after provider preference changes.
- Rendered the offline retrieval timestamp in the user's local timezone instead of truncating away its UTC offset.
- Limited reusable offline responses to 48 hours and deleted expired cache files.
- Removed hourly and daily forecast entries whose valid time has passed; Meteo never extends a prediction.
- Stored settings, weather cache, MET HTTP cache and generated translation examples using atomic replacement, private `0700` directories and `0600` files where supported.
- Treated malformed numeric metadata in the conditional MET cache as a cache miss, allowing a clean provider refresh instead of an application error.
- Added generation-based request cancellation and atomic cache-generation guards so a completed background request cannot recreate cache after the user removes data or changes location.
- Added cache removal for a single location and separate controls for cache, locations and non-location preferences.
- Sanitised malformed JSON-fallback provider, unit, theme, refresh, signal and seen-alert preferences so manual edits or partial corruption fall back safely instead of breaking startup.
- Included MET Norway's conditional HTTP files in per-location and global cache deletion, with generation guards against late recreation.
- Added voluntary diagnostics with preview/copy, optional CPU/memory fields and explicit GitHub browser hand-off; precise location and stable device identifiers are excluded.
- Made hardware diagnostics opt-in at both the interface and service-function boundaries.
- Sent the exact diagnostics snapshot shown in the preview and reset consent whenever the optional hardware fields change.
- Retained no passive telemetry, account system, API-secret storage or hidden background daemon.

### Extensibility and security

- Added an optional dependency-free Rust `cdylib` for coordinate validation and weighted arithmetic, with a tested Python fallback.
- Renamed the Meson feature option from reserved `rust_core` to `native_core`, restoring compatibility with current Meson.
- Kept custom-provider parsing as inactive, reviewed scaffolding but disabled custom network activation in the public alpha until DNS-to-connection pinning eliminates the rebinding window.
- Hardened the inactive custom-provider parser with HTTPS/credential checks, public-address validation, same-origin redirects, bounded JSON, restricted non-executable paths, finite/ranged numeric fields, ISO country codes and safe attribution links.
- Added a 5 MB network response ceiling, timeout, HTTPS-only transport and same-origin HTTPS-only redirects for JSON clients.
- Added bounded `gzip`/`deflate` HTTP decoding and HTTP 203 deprecation logging, satisfying MET Norway client requirements without allowing compressed responses to bypass the 5 MB decoded-size ceiling.
- Validated stored coordinates, translation pack size/type/name and `.format()` placeholders before use.
- Required custom translations to preserve placeholder multiplicity, format specifications and conversions, preventing a translation pack from introducing render-time formatting errors.
- Rejected overlong or non-string custom-language display names consistently with the documented pack contract.
- Preserved a missing apparent temperature in the inactive custom-provider parser rather than copying the measured temperature into a different field.

### Packaging, localisation and documentation

- Standardised application, Meson, Rust, HTTP User-Agent and AppStream versions as `0.1.0-alpha`.
- Corrected the application ID, launcher, GSettings schema discovery, desktop metadata, AppStream metadata and Flatpak manifest.
- Made source execution fall back to JSON settings when no installed GSettings schema exists and made private-prefix launchers locate their compiled schema.
- Excluded nested `__pycache__` directories and bytecode from Meson installations.
- Disabled unsupported desktop-file D-Bus activation; the installed `Exec=meteo` launcher remains authoritative.
- Set Open-Meteo as the initial provider and left consensus explicitly opt-in.
- Added English source text plus complete Spanish, Portuguese and French gettext catalogues and selectable safe JSON translation packs.
- Completed Spanish, Portuguese and French translations for desktop launcher and AppStream release metadata, and made the project validator require them.
- Added CI for Python tests/metadata, Rust tests and a Flatpak build.
- Updated the official GitHub checkout and Python setup actions to their current v7 release lines.
- Removed unused Matplotlib, Requests and JSONPath dependencies.
- Adopted GPL-3.0-or-later consistently in source headers, Rust metadata, AppStream and contribution rules.
- Made the About dialog state `GPL-3.0-or-later` explicitly instead of using GTK's version-only GPL preset.
- Identified Vicente José Leiva Escárate as copyright holder and Sylith Technologies as the unincorporated project name.
- Preserved the complete root `LICENSE` required for GPL redistribution and removed the redundant internal licence-decision document.
- Moved secondary architecture, provider, privacy, design, funding, release and legal drafts into `DOCS/`, with a documentation index.
- Added build/dependency instructions, delivery report, release notes, feature matrix, release checklist, funding boundaries and provider/legal limitations.
- Replaced publish-blocking placeholders in the product-specific legal drafts with explicit unresolved-review notices; the drafts remain non-final.
- Expanded automated regression coverage for providers, cache expiry/permissions, cancellation, consensus, localisation, metadata, GPL consistency and HTTP conditional caching.

### Known alpha limits

- Only NWS supplies official warnings, only for its documented U.S. jurisdiction; no official Chilean alert API is integrated.
- Notifications work while Meteo is open; there is no always-on service.
- Consensus compares outputs and may include scientifically correlated models.
- Custom providers are not user-activatable in this release.
- The local Flatpak manifest is for development and still needs an immutable release source, final screenshots and hardware/distro smoke tests before a Flathub submission.
- Open-Meteo terms must be resolved independently before using Meteo for business promotion or commercial activity.
