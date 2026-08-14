# Install Meteo 0.1.0-alpha from source

These instructions install Meteo directly from its source code, without Flatpak. This is an alpha release intended for testing, not for emergency or safety-critical use.

## Supported systems

The source installation is intended for:

- Ubuntu 24.04 or newer
- Debian 13 or newer
- Current Fedora releases
- Other Linux distributions providing Python 3.11+, GTK 4.14+ and libadwaita 1.5+

Older Ubuntu and Debian releases may not provide the required GTK and libadwaita versions in their standard repositories.

## 1. Install system dependencies

### Ubuntu or Debian

```bash
sudo apt update
sudo apt install git python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \
  libgtk-4-1 libadwaita-1-0 meson ninja-build gettext \
  libglib2.0-dev libgtk-4-dev libadwaita-1-dev desktop-file-utils
```

### Fedora

```bash
sudo dnf install git python3-gobject gtk4 libadwaita meson ninja-build \
  gettext glib2-devel gtk4-devel libadwaita-devel desktop-file-utils
```

Do not install a package named `gi` from PyPI. Meteo uses the PyGObject packages supplied by the Linux distribution.

## 2. Download Meteo

Clone the repository:

```bash
git clone https://github.com/sylith-technologies/Meteo.git
cd Meteo
```

Alternatively, download a source archive from the repository's **Releases** page, extract it and open a terminal in the directory containing `meson.build`.

## 3. Choose how to run Meteo

### Quick test without installation

```bash
PYTHONPATH=src python3 -m app.main
```

This is the fastest way to test the application. The uninstalled run uses a local settings fallback and may remain in English because the translation catalogues have not been installed.

### Recommended per-user installation

This installs Meteo under `~/.local` and does not require `sudo`:

```bash
meson setup build --prefix="$HOME/.local" -Dnative_core=auto
meson compile -C build
meson install -C build
"$HOME/.local/bin/meteo"
```

Log out and back in if Meteo does not immediately appear in the desktop application menu. You can always launch it with:

```bash
"$HOME/.local/bin/meteo"
```

Do not run the per-user installation with `sudo`.

## Optional Rust core

Meteo works without Rust by using its Python fallback. To build the optional native core, install Rust before configuring the build:

### Ubuntu or Debian

```bash
sudo apt install rustc cargo
```

### Fedora

```bash
sudo dnf install rust cargo
```

The Meson option controls the native core as follows:

```bash
-Dnative_core=auto      # Build it when rustc is available
-Dnative_core=enabled   # Require it; configuration fails if rustc is missing
-Dnative_core=disabled  # Always use the Python fallback
```

Rust and Cargo are build-time tools. Users do not need Rust installed after `libmeteo_core.so` has been built and installed.

## Updating an existing source installation

From the repository directory:

```bash
git pull --ff-only
meson setup --reconfigure build --prefix="$HOME/.local" -Dnative_core=auto
meson compile -C build
meson install -C build
```

If Meson reports that the build directory was created with incompatible or obsolete options, recreate only the generated build directory:

```bash
meson setup --wipe build --prefix="$HOME/.local" -Dnative_core=auto
meson compile -C build
meson install -C build
```

## Uninstalling

Keep the source and configured `build` directory, then run:

```bash
meson compile -C build uninstall
```

Uninstalling the program does not automatically delete saved locations, preferences or cached weather data. Remove that information from Meteo's preferences before uninstalling if desired.

## Troubleshooting

### `Option name rust_core is reserved`

The valid option is `native_core`, not `rust_core`. Remove or recreate the old build directory with the `--wipe` command shown above.

### `Settings schema 'io.github.sylith_technologies.Meteo' is not installed`

Run the generated launcher instead of invoking the installed Python module directly:

```bash
"$HOME/.local/bin/meteo"
```

The launcher sets the application module and GSettings schema paths.

### `module 'gi' has no attribute 'require_version'`

Confirm that the distribution's PyGObject module is being imported:

```bash
/usr/bin/python3 -c 'import gi; print(gi.__file__); print(hasattr(gi, "require_version"))'
```

The final value must be `True`. Remove any unrelated PyPI package named `gi` from the active Python environment and reinstall the distribution package (`python3-gi` on Ubuntu/Debian or `python3-gobject` on Fedora).

### Meteo cannot retrieve weather data

Meteo requires internet access for searches and fresh forecasts. It can show only previously cached data while offline. Provider outages, regional coverage and rate limits may also affect individual sources.

## Report a problem

Before reporting an issue, include the terminal output, Linux distribution, desktop environment and the exact installation command used:

<https://github.com/sylith-technologies/Meteo/issues>
