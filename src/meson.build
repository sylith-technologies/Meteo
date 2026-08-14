# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

configuration = configuration_data()
configuration.set('APP_ID', app_id)
configuration.set('VERSION', meson.project_version())
configuration.set('PREFIX', prefix)
configuration.set('PKGDATADIR', pkgdatadir)
configuration.set('LOCALEDIR', localedir)
configuration.set('STYLESHEET_PATH', pkgdatadir / 'style.css')
configuration.set('CORE_LIB_PATH', core_lib_path)

configured_app_config = configure_file(
  input: 'app/config.py.in',
  output: 'config-installed.py',
  configuration: configuration,
)

launcher_configuration = configuration_data()
launcher_configuration.set('PYTHON', python.full_path())
launcher_configuration.set('PKGDATADIR', pkgdatadir)
launcher_configuration.set(
  'GSETTINGS_SCHEMA_DIR',
  datadir / 'glib-2.0' / 'schemas',
)
configure_file(
  input: 'meteo.in',
  output: 'meteo',
  configuration: launcher_configuration,
  install: true,
  install_dir: bindir,
  install_mode: 'rwxr-xr-x',
)

install_subdir(
  'app',
  install_dir: pkgdatadir,
  exclude_files: ['config.py', 'config.py.in'],
  exclude_directories: [
    '__pycache__',
    'domain/__pycache__',
    'providers/__pycache__',
    'services/__pycache__',
    'ui/__pycache__',
    'ui/widgets/__pycache__',
    'utils/__pycache__',
  ],
)
install_data(
  configured_app_config,
  install_dir: pkgdatadir / 'app',
  rename: 'config.py',
)
