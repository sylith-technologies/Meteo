# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

project(
  'meteo',
  version: '0.1.0-alpha',
  meson_version: '>= 0.63.0',
  default_options: ['warning_level=2'],
)

i18n = import('i18n')
gnome = import('gnome')
python_module = import('python')
python = python_module.find_installation('python3')

app_id = 'io.github.sylith_technologies.Meteo'
prefix = get_option('prefix')
bindir = prefix / get_option('bindir')
datadir = prefix / get_option('datadir')
libdir = prefix / get_option('libdir')
localedir = prefix / get_option('localedir')
pkgdatadir = datadir / app_id

dependency('glib-2.0', version: '>= 2.76')
dependency('gtk4', version: '>= 4.14')
dependency('libadwaita-1', version: '>= 1.5')

core_lib_path = ''
subdir('core-rs')
subdir('data')
subdir('src')
subdir('po')

install_data(
  ['LICENSE', 'COPYRIGHT'],
  install_dir: datadir / 'licenses' / app_id,
)

gnome.post_install(
  glib_compile_schemas: true,
  gtk_update_icon_cache: true,
  update_desktop_database: true,
)
