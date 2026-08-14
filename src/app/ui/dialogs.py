# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from typing import Callable, List, Optional

from gi.repository import Adw, Gdk, Gio, Gtk

from app.i18n import _, translations
from app.models import AirQuality, Location, WeatherAlert
from app.paths import custom_translations_dir
from app.services.diagnostics import (
    build_issue_body,
    collect_diagnostics,
    github_issue_url,
)
from app.services.location import LocationService
from app.settings import SettingsManager
from app.storage import atomic_write_text, ensure_private_directory
from app.utils.async_helpers import run_async


REPOSITORY_URL = "https://github.com/sylith-technologies/Meteo"


def _alert_message(alert: WeatherAlert, value: str) -> str:
    """Keeps authority text verbatim while translating Meteo-authored signals."""

    return value if alert.official else _(value)


def _alert_kind_label(alert: WeatherAlert) -> str:
    if alert.official:
        return _("Official warning")
    if alert.kind == "service-notice":
        return _("Alert-service status — not a warning")
    return _("Forecast signal — not an official warning")


def _toolbar_window(parent: Gtk.Window, title: str, width: int, height: int):
    window = Adw.Window(transient_for=parent, modal=True)
    window.set_title(title)
    window.set_default_size(width, height)
    toolbar = Adw.ToolbarView()
    header = Adw.HeaderBar()
    header.set_title_widget(Adw.WindowTitle(title=title, subtitle="Meteo"))
    toolbar.add_top_bar(header)
    window.set_content(toolbar)
    return window, toolbar, header


class SearchLocationWindow:
    def __init__(
        self,
        parent: Gtk.Window,
        service: LocationService,
        language: str,
        on_selected: Callable[[Location], bool],
    ):
        self.window, toolbar, _header = _toolbar_window(parent, _("Add location"), 540, 620)
        self.service = service
        self.language = language
        self.on_selected = on_selected
        self._search_generation = 0

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)
        search_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.entry = Gtk.SearchEntry()
        self.entry.set_placeholder_text(_("Search for a city or town"))
        self.entry.set_hexpand(True)
        self.entry.connect("activate", self._search)
        button = Gtk.Button(icon_name="system-search-symbolic")
        button.set_tooltip_text(_("Search"))
        button.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [_("Search")],
        )
        button.connect("clicked", self._search)
        search_row.append(self.entry)
        search_row.append(button)
        content.append(search_row)

        self.status = Gtk.Label(label=_("Enter at least two characters."), xalign=0)
        self.status.set_wrap(True)
        self.status.set_css_classes(["dim-label"])
        content.append(self.status)
        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        self.results = Gtk.ListBox()
        self.results.set_css_classes(["boxed-list"])
        self.results.set_selection_mode(Gtk.SelectionMode.NONE)
        self.results.set_activate_on_single_click(True)
        self.results.connect("row-activated", self._row_activated)
        scroller.set_child(self.results)
        content.append(scroller)
        toolbar.set_content(content)

    def present(self) -> None:
        self.window.present()
        self.entry.grab_focus()

    def _search(self, *_args) -> None:
        query = self.entry.get_text().strip()
        if len(query) < 2:
            self.status.set_text(_("Enter at least two characters."))
            return
        self._search_generation += 1
        generation = self._search_generation
        self.status.set_text(_("Searching…"))
        run_async(
            lambda: self.service.search(query, self.language),
            lambda locations, error: self._on_results(
                locations,
                error,
                generation,
            ),
        )

    def _on_results(
        self,
        locations: Optional[List[Location]],
        error: Optional[Exception],
        generation: int,
    ) -> None:
        if generation != self._search_generation:
            return
        child = self.results.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.results.remove(child)
            child = next_child
        if error:
            self.status.set_text(_("The location service could not be reached."))
            return
        if not locations:
            self.status.set_text(_("No matching locations were found."))
            return
        self.status.set_text(_("Select a location."))
        for location in locations:
            row = Adw.ActionRow()
            row.set_activatable(True)
            row.set_title(location.name)
            row.set_subtitle(f"{location.latitude:.4f}, {location.longitude:.4f}")
            row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
            row.location = location
            self.results.append(row)

    def _row_activated(self, _listbox, row) -> None:
        location = getattr(row, "location", None)
        if location and self.on_selected(location):
            self.window.close()


class AlertDetailsWindow:
    def __init__(self, parent: Gtk.Window, alert: WeatherAlert):
        self.window, toolbar, _header = _toolbar_window(
            parent,
            _alert_message(alert, alert.title),
            600,
            620,
        )
        scroller = Gtk.ScrolledWindow()
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        content.set_margin_top(18)
        content.set_margin_bottom(24)
        content.set_margin_start(18)
        content.set_margin_end(18)
        badge = Gtk.Label(label=_alert_kind_label(alert), xalign=0)
        badge.set_css_classes(
            [
                "heading",
                "official-alert"
                if alert.official
                else "service-notice"
                if alert.kind == "service-notice"
                else "forecast-signal",
            ]
        )
        title = Gtk.Label(label=_alert_message(alert, alert.title), xalign=0)
        title.set_css_classes(["title-1"])
        title.set_wrap(True)
        description = Gtk.Label(
            label=_alert_message(alert, alert.description),
            xalign=0,
        )
        description.set_wrap(True)
        content.append(badge)
        content.append(title)
        content.append(description)
        if alert.instruction:
            instruction_title = Gtk.Label(label=_("Instructions"), xalign=0)
            instruction_title.set_css_classes(["heading"])
            instruction = Gtk.Label(label=alert.instruction, xalign=0)
            instruction.set_wrap(True)
            content.append(instruction_title)
            content.append(instruction)
        timing = Gtk.Label(
            label=_("Starts: {onset}\nExpires: {expires}").format(
                onset=alert.onset or "—", expires=alert.expires or "—"
            ),
            xalign=0,
        )
        timing.set_css_classes(["dim-label"])
        content.append(timing)
        if alert.source_url:
            content.append(Gtk.LinkButton.new_with_label(alert.source_url, alert.source_name))
        note = Gtk.Label(
            label=_("Meteo is not an emergency service. Follow instructions from local authorities."),
            xalign=0,
        )
        note.set_wrap(True)
        note.set_css_classes(["warning", "status-banner"])
        content.append(note)
        scroller.set_child(content)
        toolbar.set_content(scroller)

    def present(self) -> None:
        self.window.present()


class AirQualityWindow:
    def __init__(self, parent: Gtk.Window, air: AirQuality):
        self.window, toolbar, _header = _toolbar_window(parent, _("Air quality"), 520, 560)
        page = Adw.PreferencesPage()
        index_group = Adw.PreferencesGroup(title=_("Air quality indices"))
        values = [
            (_("US AQI"), air.us_aqi, ""),
            (_("European AQI"), air.european_aqi, ""),
            ("PM2.5", air.pm2_5, "μg/m³"),
            ("PM10", air.pm10, "μg/m³"),
            (_("Ozone"), air.ozone, "μg/m³"),
            (_("Nitrogen dioxide"), air.nitrogen_dioxide, "μg/m³"),
        ]
        for title, value, suffix in values:
            row = Adw.ActionRow(title=title)
            row.set_subtitle(f"{value:.1f} {suffix}" if value is not None else _("Unavailable"))
            index_group.add(row)
        page.add(index_group)
        source_group = Adw.PreferencesGroup(title=_("Provider"))
        source_row = Adw.ActionRow(title=air.provider_name or _("Unknown"))
        if air.attribution_url:
            source_row.add_suffix(
                Gtk.LinkButton.new_with_label(
                    air.attribution_url,
                    _("Provider information"),
                )
            )
        source_group.add(source_row)
        note = Adw.ActionRow(
            title=_("Modelled data"),
            subtitle=_("Air quality values are model estimates and may differ from nearby sensors."),
        )
        source_group.add(note)
        page.add(source_group)
        toolbar.set_content(page)

    def present(self) -> None:
        self.window.present()


class BugReportWindow:
    def __init__(self, parent: Gtk.Window, app_version: str):
        self.window, toolbar, header = _toolbar_window(parent, _("Report a problem"), 650, 680)
        self.app_version = app_version
        self.include_hardware = False
        self._diagnostics = {}
        self.open_button = Gtk.Button(label=_("Open GitHub report"))
        self.open_button.add_css_class("suggested-action")
        self.open_button.set_sensitive(False)
        self.open_button.connect("clicked", self._open_report)
        header.pack_end(self.open_button)
        copy_button = Gtk.Button(label=_("Copy report"))
        copy_button.set_tooltip_text(
            _("Copy the report locally without contacting GitHub")
        )
        copy_button.connect("clicked", self._copy_report)
        header.pack_start(copy_button)

        scroller = Gtk.ScrolledWindow()
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(16)
        content.set_margin_bottom(20)
        content.set_margin_start(16)
        content.set_margin_end(16)
        explanation = Gtk.Label(
            label=_(
                "Meteo does not send a report automatically. Review the data below; the final GitHub page opens in your browser."
            ),
            xalign=0,
        )
        explanation.set_wrap(True)
        content.append(explanation)
        content.append(Gtk.Label(label=_("What happened?"), xalign=0, css_classes=["heading"]))
        self.description = Gtk.TextView()
        self.description.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.description.set_top_margin(8)
        self.description.set_bottom_margin(8)
        self.description.set_left_margin(8)
        self.description.set_right_margin(8)
        description_frame = Gtk.Frame(child=self.description)
        description_frame.set_size_request(-1, 130)
        content.append(description_frame)
        hardware_row = Gtk.CheckButton(label=_("Include basic CPU and memory information"))
        hardware_row.connect("toggled", self._toggle_hardware)
        content.append(hardware_row)
        content.append(Gtk.Label(label=_("Diagnostic preview"), xalign=0, css_classes=["heading"]))
        self.preview = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.preview.set_top_margin(8)
        self.preview.set_bottom_margin(8)
        self.preview.set_left_margin(8)
        self.preview.set_right_margin(8)
        preview_frame = Gtk.Frame(child=self.preview)
        preview_frame.set_size_request(-1, 210)
        content.append(preview_frame)
        self.consent = Gtk.CheckButton(
            label=_("I reviewed these diagnostics and agree to include them in the GitHub issue.")
        )
        self.consent.connect("toggled", lambda button: self.open_button.set_sensitive(button.get_active()))
        content.append(self.consent)
        scroller.set_child(content)
        toolbar.set_content(scroller)
        self._refresh_preview()

    def present(self) -> None:
        self.window.present()

    def _toggle_hardware(self, button) -> None:
        self.include_hardware = button.get_active()
        self.consent.set_active(False)
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        self._diagnostics = collect_diagnostics(
            self.app_version,
            self.include_hardware,
        )
        self.preview.get_buffer().set_text(
            "\n".join(f"{key}: {value}" for key, value in self._diagnostics.items())
        )

    def _open_report(self, _button) -> None:
        description, diagnostics = self._report_values()
        Gio.AppInfo.launch_default_for_uri(
            github_issue_url(REPOSITORY_URL, description, diagnostics),
            None,
        )

    def _copy_report(self, _button) -> None:
        description, diagnostics = self._report_values()
        display = Gdk.Display.get_default()
        if display:
            display.get_clipboard().set_text(
                build_issue_body(description, diagnostics)
            )

    def _report_values(self):
        buffer = self.description.get_buffer()
        description = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
        return description, dict(self._diagnostics)


class PreferencesWindow:
    def __init__(
        self,
        parent: Gtk.Window,
        settings: SettingsManager,
        clear_cache: Callable[[], None],
        clear_locations: Callable[[], None],
        reset_preferences: Callable[[], None],
        on_changed: Callable[[bool], None],
    ):
        self.settings = settings
        self.on_changed = on_changed
        self.parent = parent
        self.window = Adw.PreferencesDialog()
        self.window.set_title(_("Preferences"))
        self.window.set_content_width(560)
        self.window.set_content_height(680)
        page = Adw.PreferencesPage()

        appearance = Adw.PreferencesGroup(title=_("Appearance and language"))
        self.unit_values = ["auto", "metric", "imperial"]
        units = Adw.ComboRow(title=_("Units"), model=Gtk.StringList.new([_("Automatic"), _("Metric"), _("Imperial")]))
        units.set_selected(self.unit_values.index(settings.unit_system))
        units.connect("notify::selected", self._units_changed)
        appearance.add(units)

        self.theme_values = ["system", "light", "dark"]
        theme = Adw.ComboRow(title=_("Colour scheme"), model=Gtk.StringList.new([_("System"), _("Light"), _("Dark")]))
        theme.set_selected(self.theme_values.index(settings.color_scheme))
        theme.connect("notify::selected", self._theme_changed)
        appearance.add(theme)

        self.language_values = [code for code, _name in translations.languages()]
        language = Adw.ComboRow(
            title=_("Language"),
            model=Gtk.StringList.new([name for _code, name in translations.languages()]),
        )
        language.set_selected(
            self.language_values.index(settings.language) if settings.language in self.language_values else 0
        )
        language.connect("notify::selected", self._language_changed)
        appearance.add(language)

        translations_row = Adw.ActionRow(
            title=_("Custom translations"),
            subtitle=_("Load a selectable JSON translation pack."),
        )
        translations_button = Gtk.Button(label=_("Open folder"))
        translations_button.set_valign(Gtk.Align.CENTER)
        translations_button.connect("clicked", self._open_translations_folder)
        translations_row.add_suffix(translations_button)
        appearance.add(translations_row)
        page.add(appearance)

        data_group = Adw.PreferencesGroup(title=_("Data and providers"))
        signals = Adw.SwitchRow(
            title=_("Forecast signals"),
            subtitle=_("Show model-derived storm, rain and wind signals separately from official warnings."),
        )
        signals.set_active(settings.show_forecast_signals)
        signals.connect("notify::active", self._signals_changed)
        data_group.add(signals)

        provider_row = Adw.ActionRow(
            title=_("Custom providers"),
            subtitle=_("Disabled in this alpha while connection pinning is completed."),
        )
        data_group.add(provider_row)

        cache_row = Adw.ActionRow(
            title=_("Offline cache"),
            subtitle=_("Delete all downloaded forecasts and air quality data."),
        )
        clear_button = Gtk.Button(label=_("Clear"))
        clear_button.set_valign(Gtk.Align.CENTER)
        clear_button.add_css_class("destructive-action")
        clear_button.connect(
            "clicked",
            lambda _button: self._run_and_close(clear_cache),
        )
        cache_row.add_suffix(clear_button)
        data_group.add(cache_row)

        locations_row = Adw.ActionRow(
            title=_("Saved locations"),
            subtitle=_("Remove every saved location and its cached weather data."),
        )
        locations_button = Gtk.Button(label=_("Remove all"))
        locations_button.set_valign(Gtk.Align.CENTER)
        locations_button.add_css_class("destructive-action")
        locations_button.connect(
            "clicked",
            lambda _button: self._run_and_close(clear_locations),
        )
        locations_row.add_suffix(locations_button)
        data_group.add(locations_row)

        reset_row = Adw.ActionRow(
            title=_("Preferences"),
            subtitle=_("Restore unit, appearance, language and provider defaults."),
        )
        reset_button = Gtk.Button(label=_("Reset"))
        reset_button.set_valign(Gtk.Align.CENTER)
        reset_button.connect(
            "clicked",
            lambda _button: self._run_and_close(reset_preferences),
        )
        reset_row.add_suffix(reset_button)
        data_group.add(reset_row)
        page.add(data_group)
        self.window.add(page)

    def present(self) -> None:
        self.window.present(self.parent)

    def _units_changed(self, row, _param) -> None:
        self.settings.unit_system = self.unit_values[row.get_selected()]
        self.on_changed(False)

    def _theme_changed(self, row, _param) -> None:
        self.settings.color_scheme = self.theme_values[row.get_selected()]
        self.on_changed(False)

    def _language_changed(self, row, _param) -> None:
        self.settings.language = self.language_values[row.get_selected()]
        self.on_changed(True)

    def _signals_changed(self, row, _param) -> None:
        self.settings.show_forecast_signals = row.get_active()
        self.on_changed(False)

    def _open_translations_folder(self, _button) -> None:
        directory = custom_translations_dir()
        ensure_private_directory(directory)
        example = directory / "example.json"
        if not example.exists():
            atomic_write_text(
                example,
                json.dumps(
                    {
                        "code": "example",
                        "name": "Example language",
                        "messages": {"Weather": "Translated weather", "Preferences": "Translated preferences"},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
        Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(str(directory)).get_uri(), None)

    def _run_and_close(self, action: Callable[[], None]) -> None:
        self.window.close()
        action()
