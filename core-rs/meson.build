# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

rustc = find_program('rustc', required: get_option('native_core'))

if rustc.found()
  core_library = custom_target(
    'meteo-core',
    input: 'src/lib.rs',
    output: 'libmeteo_core.so',
    command: [
      rustc,
      '--crate-name', 'meteo_core',
      '--crate-type', 'cdylib',
      '--edition=2021',
      '-C', 'opt-level=2',
      '-C', 'debuginfo=1',
      '-o', '@OUTPUT@',
      '@INPUT@',
    ],
    install: true,
    install_dir: libdir / app_id,
  )
  core_lib_path = libdir / app_id / 'libmeteo_core.so'
endif
