# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gdk, Gtk

from app import config
from app.i18n import translations
from app.paths import custom_translations_dir
from app.settings import SettingsManager
from app.ui.window import MainWindow


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


class MeteoApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id=config.APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.window = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        settings = SettingsManager()
        translations.configure(config.LOCALEDIR, custom_translations_dir(), settings.language)
        self._load_css()
        self._install_actions()

    def _load_css(self) -> None:
        provider = Gtk.CssProvider()
        try:
            provider.load_from_path(config.STYLESHEET_PATH)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
        except Exception as error:
            logging.getLogger(__name__).warning("Could not load application stylesheet: %s", error)

    def _install_actions(self) -> None:
        actions = {
            "refresh": lambda *_args: self.window and self.window.refresh_weather(force=True),
            "search": lambda *_args: self.window and self.window.open_location_search(),
            "preferences": lambda *_args: self.window and self.window.open_preferences(),
            "about": lambda *_args: self.window and self.window.show_about(),
            "quit": lambda *_args: self.quit(),
        }
        for name, callback in actions.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
        self.set_accels_for_action("app.refresh", ["<Primary>r"])
        self.set_accels_for_action("app.search", ["<Primary>l"])
        self.set_accels_for_action("app.preferences", ["<Primary>comma"])
        self.set_accels_for_action("app.quit", ["<Primary>q"])

    def do_activate(self):
        if not self.window:
            self.window = MainWindow(application=self)
        self.window.present()

    def recreate_window(self) -> None:
        settings = SettingsManager()
        translations.configure(config.LOCALEDIR, custom_translations_dir(), settings.language)
        old_window = self.window
        self.window = MainWindow(application=self)
        self.window.present()
        if old_window:
            old_window.shutdown()
            old_window.destroy()


def main() -> int:
    return MeteoApplication().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
