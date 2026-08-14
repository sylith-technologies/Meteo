# Meteo

Meteo is a privacy-conscious weather application for Linux, developed under the **Sylith Technologies project** and maintained from Chile by **Vicente José Leiva Escárate**. Sylith Technologies is a project name, not an incorporated company.

This repository is the source for **Meteo 0.1.0-alpha**, the first public demonstration release. It is suitable for testing and evaluation, not for emergency or safety-critical use.

> **Weather warning:** Meteo is not an emergency service. Only alerts explicitly identified as official and attributed to the U.S. National Weather Service are official, and only inside that service's jurisdiction. Always follow local authorities.

## Release scope

- Manual city search with no hard-coded first location.
- One active location and up to five saved locations, stored locally.
- Open-Meteo as the safe default: current conditions, 48 hourly entries, up to 15 daily entries and modelled air quality.
- Optional MET Norway forecast and regional U.S. National Weather Service forecast/alerts.
- Explicit provider selection and opt-in experimental weighted consensus.
- Offline fallback to a recent successful response, with retrieval time and expired forecast entries removed.
- Metric, imperial or region-based units; system, light or dark appearance.
- English source plus Spanish, Portuguese and French catalogues.
- Optional JSON translation packs with placeholder validation.
- Voluntary bug-report composer: preview/copy first, then an explicit browser hand-off to GitHub.
- Optional dependency-free Rust core for coordinate validation and weighted arithmetic.

Meteo does not run a hidden daemon, create accounts, display ads, sell features, process payments or send passive telemetry.

## Data sources

| Provider | Coverage | Forecast | Alerts | Status in 0.1.0-alpha |
| --- | --- | --- | --- | --- |
| [Open-Meteo](https://open-meteo.com/) | Global | Current, 48 hours, up to 15 days; modelled AQI | Forecast signals only, never official | Default |
| [MET Norway](https://api.met.no/) | Global forecast | Up to approximately 9 days | Not integrated | Optional |
| [U.S. NWS](https://www.weather.gov/) | U.S. and territories | First-hour outlook, hourly and daily | Official NWS feed | Optional and regional |

Provider output remains visibly attributed. Consensus requires at least two successful sources to be labelled as consensus; it measures agreement, not forecast certainty. The custom-provider backend is retained as reviewed source code but **network activation is disabled in this public alpha** until connection pinning closes the DNS-rebinding window.

See [provider policy](DOCS/PROVIDERS.md) and the [feature matrix](DOCS/FEATURE_MATRIX.md).

## Application identity

The permanent application, Flatpak and D-Bus identifier is:

```text
io.github.sylith_technologies.Meteo
```

The GitHub organisation contains a hyphen, which is represented by an underscore because a reverse-DNS application-ID component cannot contain that hyphen.

## Requirements

- Python 3.11 or newer
- GLib 2.76 or newer
- GTK 4.14 or newer
- libadwaita 1.5 or newer
- Meson 0.63 or newer, Ninja and gettext for a source build
- Rust compiler only when building the optional native core

On Ubuntu 24.04 or newer, or Debian 13 or newer, install the complete native development set with the following command. Older releases do not provide every declared GTK/libadwaita/Python minimum without an alternative packaging source.

```bash
sudo apt update
sudo apt install python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \
  libgtk-4-1 libadwaita-1-0 meson ninja-build gettext \
  libglib2.0-dev libgtk-4-dev libadwaita-1-dev desktop-file-utils
```

To compile the optional native core on Ubuntu/Debian:

```bash
sudo apt install rustc cargo
```

On Fedora:

```bash
sudo dnf install python3-gobject gtk4 libadwaita meson ninja-build gettext \
  glib2-devel gtk4-devel libadwaita-devel desktop-file-utils rust cargo
```

Rust and Cargo are build-time tools. An installed Meteo package contains `libmeteo_core.so`; users do not need a Rust compiler to run that library. Meteo also has a tested Python fallback if the optional library was not built.

## Run from the source tree

For a quick development run:

```bash
PYTHONPATH=src python3 -m app.main
```

For the same layout used by an installation, choose a private prefix:

```bash
meson setup build --prefix="$PWD/.local-test" -Dnative_core=auto
meson compile -C build
meson install -C build
"$PWD/.local-test/bin/meteo"
```

If `build` was configured with incompatible options, recreate only that build directory:

```bash
meson setup --wipe build --prefix="$PWD/.local-test" -Dnative_core=auto
```

The launcher sets `PYTHONPATH` and `GSETTINGS_SCHEMA_DIR` for custom prefixes. Built-in translations are compiled by Meson; a direct uninstalled run can remain in English.

## Test and validate

```bash
python3 -m compileall -q src tests scripts
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 scripts/check_project.py
cargo test --manifest-path core-rs/Cargo.toml --all-targets
```

The final command is needed only on a machine with Rust/Cargo. The full release procedure is in [DOCS/BUILD_AND_TEST.md](DOCS/BUILD_AND_TEST.md).

## Flatpak development build

The local manifest is `io.github.sylith_technologies.Meteo.json` and targets the GNOME 50 SDK/runtime:

```bash
flatpak-builder --user --install --force-clean build-flatpak \
  io.github.sylith_technologies.Meteo.json
flatpak run io.github.sylith_technologies.Meteo
```

The manifest intentionally uses the local source directory. A public repository submission must use an immutable tag/archive and a verified SHA-256; see [DOCS/FLATHUB_SUBMISSION.md](DOCS/FLATHUB_SUBMISSION.md).

## Privacy and offline behaviour

Locations, settings and weather cache are stored in private application-specific XDG directories. Provider and geocoding requests necessarily disclose the query/coordinates and connection IP to those independent services. Meteo does not send bug reports automatically.

On a failed refresh, Meteo may display the newest usable cache for the location even if provider preferences changed. Cached data older than 48 hours is rejected and removed; stale hourly/daily entries whose forecast time has passed are not shown. The interface states when the last successful response was retrieved.

Read [DOCS/PRIVACY.md](DOCS/PRIVACY.md) and [SECURITY.md](SECURITY.md).

## Licence, copyright and project status

Meteo is free software under **GNU GPL-3.0-or-later**. The complete licence text is deliberately included in the root [`LICENSE`](LICENSE) file because every redistributed source archive must carry it.

```text
Copyright © 2026 Vicente José Leiva Escárate
Developed under the Sylith Technologies project.
```

Contributors retain copyright and submit changes under the same licence using Developer Certificate of Origin sign-off. Project names and visual identity are addressed separately in [DOCS/TRADEMARKS.md](DOCS/TRADEMARKS.md). Draft legal texts in [`DOCS/legal/`](DOCS/legal/) are working material, not legal advice, and cannot reduce GPL rights.

## Funding policy

Meteo contains no advertising, subscriptions, paid functionality, paid early access or in-app donation prompts. Any future voluntary support must remain external to the application and cannot buy features, access or priority. See [DOCS/FUNDING.md](DOCS/FUNDING.md).

## Documentation

The documentation index is [DOCS/README.md](DOCS/README.md). Release changes are recorded in [CHANGELOG.md](CHANGELOG.md).

Public support: `sylithtech.contact@gmail.com`

Issues: <https://github.com/sylith-technologies/Meteo/issues>
