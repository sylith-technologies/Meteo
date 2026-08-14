# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

import threading
from gi.repository import GLib

def run_async(func, callback, *args, **kwargs):
    """Ejecuta una función pesada en un hilo secundario y entrega el resultado a GTK."""
    def worker():
        try:
            result = func(*args, **kwargs)
            GLib.idle_add(callback, result, None)
        except Exception as e:
            GLib.idle_add(callback, None, e)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
