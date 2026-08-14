# Contributing to Meteo

Issue reports, translations, design discussion and code contributions are welcome. Meteo is licensed under **GPL-3.0-or-later** and every contribution is accepted under that same licence.

## Before opening a pull request

- Keep the application usable without an account, advertising or paid features.
- Do not add passive telemetry, secrets, scraped alert sources or undisclosed network services.
- Preserve provider attribution and distinguish official alerts from forecast-derived signals.
- Add or update tests for behavior changes.
- Run `PYTHONPATH=src python3 -m unittest discover -s tests -v` and `PYTHONPATH=src python3 scripts/check_project.py`.
- Keep commits focused and explain user-facing tradeoffs.

## Developer Certificate of Origin

Every commit must include a `Signed-off-by` line certifying the [Developer Certificate of Origin 1.1](https://developercertificate.org/):

```sh
git commit --signoff
```

The sign-off records that the contributor has the right to submit the work under GPL-3.0-or-later. It does not transfer copyright to Vicente José Leiva Escárate or Sylith Technologies.

## Review and ownership

Contributors retain copyright in their contributions. The project does not currently require a Contributor Licence Agreement and does not claim an automatic copyright assignment through pull requests. Any future relicensing would require permission from every affected copyright holder or a valid prior agreement.

The maintainer may reject changes that weaken privacy, accessibility, provider legality, reliability or the stated product scope.

## Security

Do not disclose vulnerabilities or private location data in a public issue. Follow [SECURITY.md](SECURITY.md) and contact `sylithtech.contact@gmail.com` privately.

## Conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
