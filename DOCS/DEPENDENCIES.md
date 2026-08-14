# Dependency inventory — Meteo 0.1.0-alpha

Meteo deliberately uses the Linux desktop stack and Python standard library instead of vendoring general-purpose Python packages.

## Runtime dependencies

| Component | Minimum | Purpose | Installed with a native/Flatpak package? |
| --- | ---: | --- | --- |
| Python | 3.11 | Application and provider logic | Yes |
| PyGObject | Distribution version compatible with GTK 4 | Python GObject bindings | Yes |
| GLib/GIO | 2.76 | Settings, application lifecycle, notifications | Yes |
| GTK | 4.14 | Interface toolkit | Yes |
| libadwaita | 1.5 | GNOME adaptive widgets | Yes |
| CA certificates and system TLS | Distribution managed | HTTPS verification | Normally part of the OS/runtime |

The Python code uses only standard-library modules plus `gi.repository`. It does not require Requests, Matplotlib, JSONPath or a Python package download at runtime.

## Build-only dependencies

| Component | Required? | Purpose |
| --- | --- | --- |
| Meson 0.63+ | Yes for installation builds | Configuration |
| Ninja | Yes with the default Meson backend | Compilation/install driver |
| gettext | Yes | Translation extraction and `.mo` catalogues |
| GLib/GTK/libadwaita development files | Yes | Meson dependency checks and schemas |
| Rust compiler | Optional for source builds; enabled in official Flatpak manifest | Builds `libmeteo_core.so` |
| Cargo | Tests the Rust crate; Meson itself invokes `rustc` directly | Native-core tests |
| flatpak-builder | Flatpak builds only | Sandboxed package |

Rust is not a runtime dependency. A package distributes the compiled shared object, which uses the platform C ABI. If that object is absent, Meteo uses its equivalent Python implementation.

## Ubuntu/Debian installation command

Use Ubuntu 24.04 or newer, or Debian 13 or newer. Older repositories do not satisfy every minimum in the runtime table.

```bash
sudo apt update
sudo apt install python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \
  libgtk-4-1 libadwaita-1-0 meson ninja-build gettext \
  libglib2.0-dev libgtk-4-dev libadwaita-1-dev desktop-file-utils
```

Optional native-core toolchain:

```bash
sudo apt install rustc cargo
```

## Fedora installation command

```bash
sudo dnf install python3-gobject gtk4 libadwaita meson ninja-build gettext \
  glib2-devel gtk4-devel libadwaita-devel desktop-file-utils rust cargo
```

## Flatpak runtime

The development manifest uses `org.gnome.Platform//50`, `org.gnome.Sdk//50` and `org.freedesktop.Sdk.Extension.rust-stable`. The SDK and Rust extension are build inputs; installed users receive only the resulting app and its declared runtime.

## External network services

These are services, not installed software dependencies:

- Open-Meteo Forecast API and Geocoding API;
- Open-Meteo Air Quality API/CAMS model data;
- MET Norway Locationforecast API;
- U.S. National Weather Service API inside its jurisdiction;
- GitHub only when the user explicitly opens a bug-report page.

Availability, privacy, attribution and acceptable-use terms remain independent from GPL-3.0-or-later.
