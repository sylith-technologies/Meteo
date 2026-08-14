# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import hashlib
import logging
from typing import Callable, Optional

from gi.repository import Adw, Gio, GLib, Gtk

from app import config
from app.i18n import _, ngettext
from app.models import AirQuality, Location, WeatherAlert, WeatherReport
from app.providers.registry import ProviderRegistry
from app.services.cache import WeatherCache
from app.services.location import LocationService
from app.services.weather import WeatherService
from app.settings import SettingsManager
from app.ui.dialogs import (
    AirQualityWindow,
    AlertDetailsWindow,
    BugReportWindow,
    PreferencesWindow,
    SearchLocationWindow,
)
from app.ui.weather_page import WeatherPage
from app.utils.async_helpers import run_async


logger = logging.getLogger(__name__)


def _accessible_label(widget: Gtk.Widget, label: str) -> None:
    widget.update_property([Gtk.AccessibleProperty.LABEL], [label])


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title(_("Meteo"))
        self.set_default_size(1120, 760)
        self.set_size_request(360, 480)

        self.settings = SettingsManager()
        self.cache = WeatherCache(fresh_seconds=self.settings.update_interval_minutes * 60)
        self.registry = ProviderRegistry()
        self.weather_service = WeatherService(self.registry, self.cache)
        self.location_service = LocationService()
        self.current_report: Optional[WeatherReport] = None
        self._request_generation = 0
        self._style_manager = Adw.StyleManager.get_default()
        self._style_signal_id = 0

        self._apply_colour_scheme()
        self._build_ui()
        self._style_signal_id = self._style_manager.connect(
            "notify::high-contrast",
            self._sync_high_contrast,
        )
        self._sync_high_contrast()
        self._install_breakpoints()
        if self.settings.active_location():
            self._ensure_provider_mode(self.settings.active_location())
        self._rebuild_locations()
        self._rebuild_provider_popover()

        if self.settings.active_location():
            self.split.set_show_content(True)
            self.refresh_weather(force=False)
        else:
            self._show_welcome()

        self._refresh_source_id = GLib.timeout_add_seconds(
            self.settings.update_interval_minutes * 60,
            self._automatic_refresh,
        )
        self.connect("close-request", self._close_requested)

    def _build_ui(self) -> None:
        self.split = Adw.NavigationSplitView()

        sidebar_toolbar = Adw.ToolbarView()
        sidebar_header = Adw.HeaderBar()
        sidebar_header.set_show_end_title_buttons(False)
        sidebar_title = Adw.WindowTitle(title=_("Locations"), subtitle=_("Up to five saved places"))
        sidebar_header.set_title_widget(sidebar_title)
        self.add_button = Gtk.Button(icon_name="list-add-symbolic")
        self.add_button.set_tooltip_text(_("Add location"))
        _accessible_label(self.add_button, _("Add location"))
        self.add_button.connect("clicked", lambda _button: self.open_location_search())
        sidebar_header.pack_end(self.add_button)
        sidebar_toolbar.add_top_bar(sidebar_header)

        sidebar_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.location_list = Gtk.ListBox()
        self.location_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.location_list.set_activate_on_single_click(True)
        self.location_list.set_css_classes(["navigation-sidebar"])
        self.location_list.connect("row-activated", self._location_activated)
        locations_scroller = Gtk.ScrolledWindow()
        locations_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        locations_scroller.set_vexpand(True)
        locations_scroller.set_child(self.location_list)
        sidebar_content.append(locations_scroller)

        sidebar_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sidebar_actions.set_margin_start(8)
        sidebar_actions.set_margin_end(8)
        sidebar_actions.set_margin_bottom(8)
        bug_button = Gtk.Button(icon_name="tools-report-bug-symbolic")
        bug_button.set_tooltip_text(_("Report a problem"))
        _accessible_label(bug_button, _("Report a problem"))
        bug_button.connect("clicked", lambda _button: BugReportWindow(self, config.VERSION).present())
        preferences_button = Gtk.Button(icon_name="emblem-system-symbolic")
        preferences_button.set_tooltip_text(_("Preferences"))
        _accessible_label(preferences_button, _("Preferences"))
        preferences_button.connect("clicked", lambda _button: self.open_preferences())
        about_button = Gtk.Button(icon_name="help-about-symbolic")
        about_button.set_tooltip_text(_("About Meteo"))
        _accessible_label(about_button, _("About Meteo"))
        about_button.connect("clicked", lambda _button: self.show_about())
        sidebar_actions.append(bug_button)
        sidebar_actions.append(preferences_button)
        sidebar_actions.append(about_button)
        sidebar_content.append(sidebar_actions)
        sidebar_toolbar.set_content(sidebar_content)

        content_toolbar = Adw.ToolbarView()
        content_header = Adw.HeaderBar()
        content_header.set_show_start_title_buttons(False)
        self.window_title = Adw.WindowTitle(title=_("Meteo"), subtitle=_("Weather by Sylith Technologies"))
        content_header.set_title_widget(self.window_title)
        self.refresh_button = Gtk.Button(icon_name="view-refresh-symbolic")
        self.refresh_button.set_tooltip_text(_("Refresh"))
        _accessible_label(self.refresh_button, _("Refresh"))
        self.refresh_button.connect("clicked", lambda _button: self.refresh_weather(force=True))
        content_header.pack_end(self.refresh_button)
        self.provider_button = Gtk.MenuButton(icon_name="network-server-symbolic")
        self.provider_button.set_tooltip_text(_("Providers and consensus"))
        _accessible_label(self.provider_button, _("Providers and consensus"))
        content_header.pack_end(self.provider_button)
        content_toolbar.add_top_bar(content_header)

        self.state_stack = Gtk.Stack()
        self.state_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.state_stack.set_transition_duration(220)
        self.weather_page = WeatherPage(self._open_alert, self._open_air_quality)
        self.state_stack.add_named(self.weather_page, "weather")

        loading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        loading.set_halign(Gtk.Align.CENTER)
        loading.set_valign(Gtk.Align.CENTER)
        spinner = Gtk.Spinner(spinning=True)
        spinner.set_size_request(42, 42)
        loading.append(spinner)
        loading.append(Gtk.Label(label=_("Contacting weather providers…")))
        self.state_stack.add_named(loading, "loading")

        self.welcome_page = Adw.StatusPage(
            icon_name="weather-clear-symbolic",
            title=_("Choose your first location"),
            description=_("Meteo stores up to five locations locally. No default city is assumed."),
        )
        welcome_button = Gtk.Button(label=_("Search for a location"))
        welcome_button.add_css_class("suggested-action")
        welcome_button.set_halign(Gtk.Align.CENTER)
        welcome_button.connect("clicked", lambda _button: self.open_location_search())
        self.welcome_page.set_child(welcome_button)
        self.state_stack.add_named(self.welcome_page, "welcome")

        self.error_page = Adw.StatusPage(
            icon_name="network-error-symbolic",
            title=_("Weather is unavailable"),
            description=_("No provider responded and there is no cached forecast for this location."),
        )
        retry_button = Gtk.Button(label=_("Try again"))
        retry_button.add_css_class("suggested-action")
        retry_button.set_halign(Gtk.Align.CENTER)
        retry_button.connect("clicked", lambda _button: self.refresh_weather(force=True))
        self.error_page.set_child(retry_button)
        self.state_stack.add_named(self.error_page, "error")

        content_toolbar.set_content(self.state_stack)
        sidebar_page = Adw.NavigationPage.new(sidebar_toolbar, _("Locations"))
        content_page = Adw.NavigationPage.new(content_toolbar, _("Weather"))
        self.split.set_sidebar(sidebar_page)
        self.split.set_content(content_page)
        self.set_content(self.split)

    def _install_breakpoints(self) -> None:
        narrow = Adw.Breakpoint.new(
            Adw.BreakpointCondition.parse("max-width: 700px")
        )
        narrow.connect("apply", lambda _breakpoint: self._set_narrow_layout(True))
        narrow.connect("unapply", lambda _breakpoint: self._set_narrow_layout(False))
        self.add_breakpoint(narrow)

    def _set_narrow_layout(self, narrow: bool) -> None:
        self.split.set_collapsed(narrow)
        self.weather_page.body.set_orientation(
            Gtk.Orientation.VERTICAL if narrow else Gtk.Orientation.HORIZONTAL
        )
        self.weather_page.body.set_homogeneous(not narrow)
        self.weather_page.credits_box.set_orientation(
            Gtk.Orientation.VERTICAL if narrow else Gtk.Orientation.HORIZONTAL
        )

    def _show_welcome(self) -> None:
        self.state_stack.set_visible_child_name("welcome")
        self.split.set_show_content(True)
        self.window_title.set_title(_("Meteo"))
        self.window_title.set_subtitle(_("No location selected"))
        self.refresh_button.set_sensitive(False)

    def _rebuild_locations(self) -> None:
        child = self.location_list.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.location_list.remove(child)
            child = next_child
        active = self.settings.active_location()
        for location in self.settings.locations():
            row = Adw.ActionRow()
            row.location = location
            row.set_activatable(True)
            row.set_title(location.name)
            row.set_subtitle(
                _("Selected") if active and location.key == active.key else location.country
            )
            if active and location.key == active.key:
                row.add_prefix(Gtk.Image.new_from_icon_name("emblem-ok-symbolic"))
            remove = Gtk.Button(icon_name="edit-delete-symbolic")
            remove.set_valign(Gtk.Align.CENTER)
            remove.set_tooltip_text(_("Remove location"))
            _accessible_label(remove, _("Remove location"))
            remove.add_css_class("flat")
            remove.connect(
                "clicked",
                lambda _button, key=location.key: self._confirm_remove_location(key),
            )
            row.add_suffix(remove)
            self.location_list.append(row)
        self.add_button.set_sensitive(len(self.settings.locations()) < 5)

    def _location_activated(self, _listbox, row) -> None:
        location = getattr(row, "location", None)
        if not location:
            return
        self.settings.set_active_location(location.key)
        self._ensure_provider_mode(location)
        self._rebuild_locations()
        self._rebuild_provider_popover()
        self.refresh_weather(force=False)
        self.split.set_show_content(True)

    def _confirm(
        self,
        heading: str,
        body: str,
        action_label: str,
        action: Callable[[], None],
    ) -> None:
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("confirm", action_label)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect(
            "response",
            lambda _dialog, response: action() if response == "confirm" else None,
        )
        dialog.present(self)

    def _confirm_remove_location(self, key: str) -> None:
        location = next(
            (item for item in self.settings.locations() if item.key == key),
            None,
        )
        if not location:
            return
        self._confirm(
            _("Remove location?"),
            _("{location} and its cached weather data will be removed.").format(
                location=location.name
            ),
            _("Remove"),
            lambda: self._remove_location(key),
        )

    def _remove_location(self, key: str) -> None:
        self._request_generation += 1
        location = next(
            (item for item in self.settings.locations() if item.key == key),
            None,
        )
        self.settings.remove_location(key)
        if location:
            self.cache.clear_location(location)
            self.registry.clear_persistent_cache(location)
        self.current_report = None
        if self.settings.active_location():
            self._ensure_provider_mode(self.settings.active_location())
        self._rebuild_locations()
        self._rebuild_provider_popover()
        if self.settings.active_location():
            self.refresh_weather(force=False)
        else:
            self._show_welcome()

    def open_location_search(self) -> None:
        if len(self.settings.locations()) >= 5:
            dialog = Adw.AlertDialog(
                heading=_("Location limit reached"),
                body=_("Remove one saved location before adding another."),
            )
            dialog.add_response("ok", _("OK"))
            dialog.present(self)
            return
        SearchLocationWindow(
            self,
            self.location_service,
            self.settings.resolved_language(),
            self._location_selected,
        ).present()

    def _location_selected(self, location: Location) -> bool:
        if not self.settings.save_location(location):
            return False
        self._ensure_provider_mode(location)
        self._rebuild_locations()
        self._rebuild_provider_popover()
        self.split.set_show_content(True)
        self.refresh_weather(force=True)
        return True

    def refresh_weather(self, force: bool = False) -> None:
        location = self.settings.active_location()
        if not location:
            self._show_welcome()
            return
        self._ensure_provider_mode(location)
        self._request_generation += 1
        generation = self._request_generation
        self.refresh_button.set_sensitive(False)
        self.state_stack.set_visible_child_name("loading")
        self.window_title.set_title(location.name)
        self.window_title.set_subtitle(_("Updating…"))

        def callback(result, error):
            if generation != self._request_generation:
                return
            self.refresh_button.set_sensitive(True)
            if error:
                logger.warning("Weather refresh failed: %s", error)
                self.error_page.set_description(
                    _("No provider responded and there is no cached forecast for this location.")
                )
                self.state_stack.set_visible_child_name("error")
                self.window_title.set_subtitle(_("Unavailable"))
                return
            self.current_report = result
            self._notify_official_alerts(result)
            self.weather_page.update(
                result,
                self.settings.resolved_unit_system(),
                self.settings.show_forecast_signals,
            )
            self.state_stack.set_visible_child_name("weather")
            source_count = len(result.sources)
            self.window_title.set_subtitle(
                ngettext(
                    "{count} provider",
                    "{count} providers",
                    source_count,
                ).format(count=source_count)
                if result.display.is_consensus
                else result.display.provider_name
            )

        run_async(
            lambda: self.weather_service.load(
                location,
                self.settings.enabled_providers(),
                self.settings.provider_mode,
                force_refresh=force,
                is_cancelled=lambda: generation != self._request_generation,
            ),
            callback,
        )

    def _notify_official_alerts(self, report: WeatherReport) -> None:
        if report.display.stale:
            return
        seen = set(self.settings.seen_alert_ids())
        newly_seen = []
        for alert in report.display.alerts:
            seen_key = f"{alert.source_name}|{alert.alert_id}"
            if not alert.official or seen_key in seen:
                continue
            notification = Gio.Notification.new(alert.title)
            notification.set_body(alert.description[:360] or alert.source_name)
            notification.set_priority(Gio.NotificationPriority.HIGH)
            notification_id = hashlib.sha256(
                f"{alert.source_name}|{alert.alert_id}".encode("utf-8")
            ).hexdigest()[:32]
            self.get_application().send_notification(notification_id, notification)
            newly_seen.append(seen_key)
        if newly_seen:
            self.settings.mark_alerts_seen(newly_seen)

    def _automatic_refresh(self) -> bool:
        if self.settings.active_location():
            self.refresh_weather(force=True)
        return GLib.SOURCE_CONTINUE

    def _ensure_provider_mode(self, location: Location) -> None:
        mode = self.settings.provider_mode
        if mode != "consensus":
            provider = self.registry.get(mode)
            if provider is not None and provider.supports(location):
                return
            self.settings.provider_mode = "consensus"
        enabled = self.settings.enabled_providers()
        has_supported = any(
            (provider := self.registry.get(provider_id)) is not None
            and provider.supports(location)
            for provider_id in enabled
        )
        if not has_supported:
            self.settings.set_enabled_providers(enabled + ["open-meteo"])

    def shutdown(self) -> None:
        """Stops callbacks owned by a window that is being replaced or closed."""

        self._request_generation += 1
        if self._style_signal_id:
            self._style_manager.disconnect(self._style_signal_id)
            self._style_signal_id = 0
        if self._refresh_source_id:
            GLib.source_remove(self._refresh_source_id)
            self._refresh_source_id = 0

    def _close_requested(self, _window) -> bool:
        self.shutdown()
        return False

    def _rebuild_provider_popover(self) -> None:
        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        title = Gtk.Label(label=_("Display source"), xalign=0)
        title.set_css_classes(["heading"])
        box.append(title)
        location = self.settings.active_location()
        available = self.registry.all()

        first_radio = None
        mode = self.settings.provider_mode
        choices = [("consensus", _("Weighted consensus (experimental)"))]
        choices.extend((provider.metadata.provider_id, provider.metadata.name) for provider in available)
        for provider_id, label in choices:
            radio = Gtk.CheckButton(label=label)
            if first_radio is None:
                first_radio = radio
            else:
                radio.set_group(first_radio)
            supported = provider_id == "consensus" or not location or bool(
                self.registry.get(provider_id) and self.registry.get(provider_id).supports(location)
            )
            radio.set_sensitive(supported)
            radio.set_active(mode == provider_id)
            radio.connect("toggled", self._provider_mode_toggled, provider_id)
            box.append(radio)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(4)
        separator.set_margin_bottom(4)
        box.append(separator)
        included = Gtk.Label(label=_("Included in consensus"), xalign=0)
        included.set_css_classes(["heading"])
        box.append(included)
        enabled = self.settings.enabled_providers()
        for provider in available:
            check = Gtk.CheckButton(label=provider.metadata.name)
            check.set_active(provider.metadata.provider_id in enabled)
            check.set_sensitive(not location or provider.supports(location))
            check.connect("toggled", self._provider_enabled_toggled, provider.metadata.provider_id)
            box.append(check)

        popover.set_child(box)
        self.provider_button.set_popover(popover)

    def _provider_mode_toggled(self, button, provider_id: str) -> None:
        if not button.get_active() or self.settings.provider_mode == provider_id:
            return
        self.settings.provider_mode = provider_id
        self.refresh_weather(force=True)

    def _provider_enabled_toggled(self, button, provider_id: str) -> None:
        enabled = self.settings.enabled_providers()
        if button.get_active() and provider_id not in enabled:
            enabled.append(provider_id)
        elif not button.get_active() and provider_id in enabled:
            candidate = [item for item in enabled if item != provider_id]
            location = self.settings.active_location()
            if location and not any(
                (provider := self.registry.get(item)) is not None
                and provider.supports(location)
                for item in candidate
            ):
                button.set_active(True)
                return
            enabled = candidate
        self.settings.set_enabled_providers(enabled)
        if self.settings.provider_mode == "consensus":
            self.refresh_weather(force=True)

    def _open_alert(self, alert: WeatherAlert) -> None:
        AlertDetailsWindow(self, alert).present()

    def _open_air_quality(self, air_quality: AirQuality) -> None:
        AirQualityWindow(self, air_quality).present()

    def open_preferences(self) -> None:
        PreferencesWindow(
            self,
            self.settings,
            self._clear_cache,
            self._clear_locations,
            self._reset_preferences,
            self._preferences_changed,
        ).present()

    def _clear_cache(self) -> None:
        self._confirm(
            _("Clear offline cache?"),
            _("Downloaded forecasts and air-quality data will be removed from disk."),
            _("Clear"),
            self._clear_cache_now,
        )

    def _clear_cache_now(self) -> None:
        self._request_generation += 1
        self.cache.clear()
        self.registry.clear_persistent_cache()

    def _clear_locations(self) -> None:
        self._confirm(
            _("Remove all locations?"),
            _("Every saved location and all cached weather data will be removed."),
            _("Remove all"),
            self._clear_locations_now,
        )

    def _clear_locations_now(self) -> None:
        self._request_generation += 1
        self.settings.clear_locations()
        self.cache.clear()
        self.registry.clear_persistent_cache()
        self.current_report = None
        self._rebuild_locations()
        self._rebuild_provider_popover()
        self._show_welcome()

    def _reset_preferences(self) -> None:
        self.settings.reset_preferences()
        self.get_application().recreate_window()

    def _preferences_changed(self, rebuild_language: bool) -> None:
        self._apply_colour_scheme()
        if rebuild_language:
            self.get_application().recreate_window()
            return
        if self.current_report:
            self.weather_page.update(
                self.current_report,
                self.settings.resolved_unit_system(),
                self.settings.show_forecast_signals,
            )

    def _apply_colour_scheme(self) -> None:
        schemes = {
            "system": Adw.ColorScheme.DEFAULT,
            "light": Adw.ColorScheme.FORCE_LIGHT,
            "dark": Adw.ColorScheme.FORCE_DARK,
        }
        self._style_manager.set_color_scheme(
            schemes.get(self.settings.color_scheme, Adw.ColorScheme.DEFAULT)
        )

    def _sync_high_contrast(self, *_args) -> None:
        if self._style_manager.get_high_contrast():
            self.add_css_class("high-contrast")
        else:
            self.remove_css_class("high-contrast")

    def show_about(self) -> None:
        about = Adw.AboutDialog(
            application_name="Meteo",
            application_icon=config.APP_ID,
            developer_name="Sylith Technologies",
            version=config.VERSION,
            website="https://sylith-technologies.github.io/",
            issue_url="https://github.com/sylith-technologies/Meteo/issues",
            copyright=(
                "© 2026 Vicente José Leiva Escárate — "
                "Sylith Technologies project"
            ),
            comments=_("A clear, privacy-conscious weather application for Linux."),
            license_type=Gtk.License.CUSTOM,
            license=(
                "GNU General Public License version 3 or later "
                "(GPL-3.0-or-later).\n\n"
                "See the LICENSE file distributed with Meteo for the complete text."
            ),
        )
        about.add_link(_("Weather data by Open-Meteo"), "https://open-meteo.com/")
        about.add_link(_("Weather data by MET Norway"), "https://api.met.no/")
        about.add_link(_("US alerts by the National Weather Service"), "https://www.weather.gov/")
        about.add_link(_("Weather-data licence: CC BY 4.0"), "https://creativecommons.org/licenses/by/4.0/")
        about.present(self)
