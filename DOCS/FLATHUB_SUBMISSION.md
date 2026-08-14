# Flathub submission proposal

The repository contains a development Flatpak manifest for:

    io.github.sylith_technologies.Meteo

It targets the GNOME 50 runtime and builds the optional Rust core with the official Rust SDK extension. Runtime permissions are limited to network, Wayland/X11 fallback, IPC needed by the display stack and graphics acceleration.

## Submission blockers

Do not submit the current archive to Flathub until all of these are resolved:

1. Obtain written confirmation or another compliant arrangement for Open-Meteo before a Sylith promotional or commercial use. Meteo itself must remain free of ads, subscriptions and paid features under the current policy.
2. Replace the manifest’s local directory source with an immutable release tag/archive and verified SHA-256.
3. Add the final app icon and real screenshots produced by the built application.
4. Validate and run the Flatpak on Fedora and Ubuntu, on x86-64 and ARM64 where available.
5. Review the governing-law placeholder in the draft terms; the copyright holder, GPL licence and private contact are already recorded.

## Release manifest shape

The release manifest should replace the local source with an immutable source similar to:

    {
      "type": "archive",
      "url": "https://github.com/sylith-technologies/Meteo/archive/refs/tags/v0.1.0-alpha.tar.gz",
      "sha256": "761756111ea1b2c829433673f9b2834d15f6adf5966514786a290212198ceceb"
    }

Never copy that placeholder into a submission without creating the tag and computing the real digest. The declared repository at https://github.com/sylith-technologies/Meteo exists and uses `main`.

## Validation sequence

    PYTHONPATH=src python3 -m unittest discover -s tests -v
    PYTHONPATH=src python3 scripts/check_project.py
    cargo test --manifest-path core-rs/Cargo.toml --all-targets
    flatpak-builder --force-clean build-flatpak io.github.sylith_technologies.Meteo.json
    flatpak-builder --run build-flatpak io.github.sylith_technologies.Meteo.json meteo

Then validate the installed AppStream, desktop and GSettings files with the tools shipped by the target runtime and complete Flathub’s current quality guidelines.

Official references:

- App ID and submission requirements: https://docs.flathub.org/docs/for-app-authors/requirements
- Runtime policy: https://docs.flathub.org/docs/for-app-authors/runtimes
