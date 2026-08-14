# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import datetime
from typing import Callable, Iterable, Optional

from gi.repository import Gtk

from app.domain.conditions import condition_icon, condition_label
from app.i18n import _, localized_date_label, ngettext
from app.models import AirQuality, DailyForecast, WeatherAlert, WeatherReport
from app.ui.widgets.temperature_graph import TemperatureGraph
from app.units import precipitation, speed, temperature, visibility


def _clear(container: Gtk.Widget) -> None:
    child = container.get_first_child()
    while child is not None:
        next_child = child.get_next_sibling()
        container.remove(child)
        child = next_child


def _time_label(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%H:%M")
    except (TypeError, ValueError):
        return value[11:16] if len(value) >= 16 else value


def _retrieval_time_label(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return parsed.strftime("%Y-%m-%d %H:%M %Z").strip()
    except (TypeError, ValueError):
        return value[:19]


def _alert_title(alert: WeatherAlert) -> str:
    return alert.title if alert.official else _(alert.title)


def _alert_kind_label(alert: WeatherAlert) -> str:
    if alert.official:
        return _("Official warning")
    if alert.kind == "service-notice":
        return _("Alert-service status — not a warning")
    return _("Forecast signal — not an official warning")


def _aqi_presentation(value: Optional[float], european: bool = False) -> tuple[str, str]:
    if value is None:
        return "aqi-unknown", _("Unavailable")
    if european:
        levels = (
            (20, "aqi-good", _("Good")),
            (40, "aqi-fair", _("Fair")),
            (60, "aqi-moderate", _("Moderate")),
            (80, "aqi-unhealthy", _("Poor")),
            (100, "aqi-very-unhealthy", _("Very poor")),
            (float("inf"), "aqi-hazardous", _("Extremely poor")),
        )
    else:
        levels = (
            (50, "aqi-good", _("Good")),
            (100, "aqi-moderate", _("Moderate")),
            (150, "aqi-sensitive", _("Unhealthy for sensitive groups")),
            (200, "aqi-unhealthy", _("Unhealthy")),
            (300, "aqi-very-unhealthy", _("Very unhealthy")),
            (float("inf"), "aqi-hazardous", _("Hazardous")),
        )
    return next((css, label) for limit, css, label in levels if value <= limit)


class MetricCard(Gtk.Box):
    def __init__(
        self,
        title: str,
        value: str,
        subtitle: str = "",
        icon_name: str = "",
        style_class: str = "",
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        classes = ["card", "metric-card", "flat"]
        if style_class:
            classes.append(style_class)
        self.set_css_classes(classes)
        self.set_halign(Gtk.Align.FILL)
        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        if icon_name:
            heading.append(Gtk.Image.new_from_icon_name(icon_name))
        title_label = Gtk.Label(label=title, xalign=0)
        title_label.set_css_classes(["dim-label", "caption"])
        heading.append(title_label)
        value_label = Gtk.Label(label=value, xalign=0)
        value_label.set_css_classes(["title-3"])
        value_label.set_wrap(True)
        self.append(heading)
        self.append(value_label)
        if subtitle:
            subtitle_label = Gtk.Label(label=subtitle, xalign=0)
            subtitle_label.set_wrap(True)
            subtitle_label.set_css_classes(["dim-label", "caption"])
            self.append(subtitle_label)


class SunTimesCard(Gtk.Box):
    def __init__(self, sunrise: str, sunset: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_css_classes(["card", "metric-card", "flat", "metric-sun"])
        title = Gtk.Label(label=_("Sunrise and sunset"), xalign=0)
        title.set_css_classes(["dim-label", "caption"])
        self.append(title)
        times = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        times.set_homogeneous(True)
        for label, value, icon_name in (
            (_("Sunrise"), sunrise, "weather-clear-symbolic"),
            (_("Sunset"), sunset, "weather-clear-night-symbolic"),
        ):
            item = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            heading.append(Gtk.Image.new_from_icon_name(icon_name))
            heading.append(Gtk.Label(label=label, xalign=0, css_classes=["caption"]))
            value_label = Gtk.Label(label=value, xalign=0, css_classes=["title-3"])
            item.append(heading)
            item.append(value_label)
            times.append(item)
        self.append(times)


class WeatherPage(Gtk.ScrolledWindow):
    def __init__(
        self,
        on_alert: Callable[[WeatherAlert], None],
        on_air_quality: Callable[[AirQuality], None],
    ):
        super().__init__()
        self._on_alert = on_alert
        self._on_air_quality = on_air_quality
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.content.set_margin_top(18)
        self.content.set_margin_bottom(24)
        self.content.set_margin_start(18)
        self.content.set_margin_end(18)
        self.content.set_size_request(320, -1)
        self.set_child(self.content)

        self.stale_revealer = Gtk.Revealer()
        self.stale_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        stale_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        stale_box.set_css_classes(["warning", "status-banner"])
        stale_box.append(Gtk.Image.new_from_icon_name("network-offline-symbolic"))
        self.stale_label = Gtk.Label(xalign=0)
        self.stale_label.set_wrap(True)
        stale_box.append(self.stale_label)
        self.stale_revealer.set_child(stale_box)
        self.content.append(self.stale_revealer)

        self.alerts_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.content.append(self.alerts_box)

        self.hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.hero.set_css_classes(["hero-card"])
        self.hero.set_margin_bottom(2)
        self.location_label = Gtk.Label(xalign=0)
        self.location_label.set_css_classes(["title-3"])
        self.data_kind_label = Gtk.Label(xalign=0)
        self.data_kind_label.set_css_classes(["dim-label", "caption"])
        self.temperature_label = Gtk.Label(xalign=0)
        self.temperature_label.set_css_classes(["hero-temperature"])
        condition_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.condition_icon = Gtk.Image()
        self.condition_icon.set_pixel_size(42)
        self.condition_label = Gtk.Label(xalign=0)
        self.condition_label.set_css_classes(["title-2"])
        condition_row.append(self.condition_icon)
        condition_row.append(self.condition_label)
        self.high_low_label = Gtk.Label(xalign=0)
        self.feels_label = Gtk.Label(xalign=0)
        self.provider_label = Gtk.Label(xalign=0)
        self.provider_label.set_wrap(True)
        self.provider_label.set_css_classes(["dim-label", "caption"])
        self.hero.append(self.location_label)
        self.hero.append(self.data_kind_label)
        self.hero.append(self.temperature_label)
        self.hero.append(condition_row)
        self.hero.append(self.high_low_label)
        self.hero.append(self.feels_label)
        self.hero.append(self.provider_label)
        self.content.append(self.hero)

        self.hourly_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.hourly_card.set_css_classes(["card", "section-card"])
        self.hourly_title = Gtk.Label(label=_("Next 48 hours"), xalign=0)
        self.hourly_title.set_css_classes(["heading"])
        self.hourly_card.append(self.hourly_title)
        self.hourly_scroll = Gtk.ScrolledWindow()
        self.hourly_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.hourly_scroll.set_min_content_height(122)
        self.hourly_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.hourly_scroll.set_child(self.hourly_box)
        self.hourly_card.append(self.hourly_scroll)
        self.graph = TemperatureGraph()
        self.hourly_card.append(self.graph)
        self.content.append(self.hourly_card)

        self.body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        self.body.set_homogeneous(True)
        self.daily_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.daily_card.set_css_classes(["card", "section-card"])
        self.daily_title = Gtk.Label(label=_("15-day forecast"), xalign=0)
        self.daily_title.set_css_classes(["heading"])
        self.daily_card.append(self.daily_title)
        self.daily_list = Gtk.ListBox()
        self.daily_list.set_css_classes(["boxed-list"])
        self.daily_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.daily_card.append(self.daily_list)
        self.body.append(self.daily_card)

        metrics_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        metrics_card.set_css_classes(["card", "section-card"])
        details_title = Gtk.Label(label=_("Details"), xalign=0)
        details_title.set_css_classes(["heading"])
        metrics_card.append(details_title)
        self.metrics_flow = Gtk.FlowBox()
        self.metrics_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self.metrics_flow.set_max_children_per_line(2)
        self.metrics_flow.set_min_children_per_line(1)
        self.metrics_flow.set_row_spacing(8)
        self.metrics_flow.set_column_spacing(8)
        metrics_card.append(self.metrics_flow)
        self.body.append(metrics_card)
        self.content.append(self.body)

        self.credits_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.credits_box.set_halign(Gtk.Align.CENTER)
        self.credits_box.set_margin_top(8)
        self.content.append(self.credits_box)

    def update(self, report: WeatherReport, unit_system: str, show_forecast_signals: bool = True) -> None:
        bundle = report.display
        current = bundle.current
        today = bundle.daily[0] if bundle.daily else None

        self.stale_revealer.set_reveal_child(bundle.stale)
        if bundle.stale:
            self.stale_label.set_text(
                _("Offline data — last successful update: {time}").format(
                    time=_retrieval_time_label(bundle.retrieved_at)
                )
            )

        self.location_label.set_text(bundle.location.name)
        self.data_kind_label.set_text(
            _("Forecast conditions") if current.is_forecast else _("Current conditions")
        )
        self.temperature_label.set_text(temperature(current.temperature_c, unit_system))
        self.condition_icon.set_from_icon_name(condition_icon(current.condition_code))
        self.condition_label.set_text(_(condition_label(current.condition_code)))
        if today:
            self.high_low_label.set_text(
                _("High {high} · Low {low}").format(
                    high=temperature(today.temperature_max_c, unit_system),
                    low=temperature(today.temperature_min_c, unit_system),
                )
            )
        else:
            self.high_low_label.set_text("")
        self.feels_label.set_visible(current.apparent_temperature_c is not None)
        self.feels_label.set_text(
            _("Feels like {value}").format(
                value=temperature(current.apparent_temperature_c, unit_system)
            )
            if current.apparent_temperature_c is not None
            else ""
        )
        source_text = bundle.provider_name
        if bundle.is_consensus and bundle.confidence_percent is not None:
            source_text += _(" · agreement {value}%").format(value=bundle.confidence_percent)
        if report.errors:
            count = len(report.errors)
            source_text += ngettext(
                " · {count} source unavailable",
                " · {count} sources unavailable",
                count,
            ).format(count=count)
        self.provider_label.set_text(source_text)

        self.hourly_card.set_visible(bool(bundle.hourly))
        hourly_count = len(bundle.hourly)
        self.hourly_title.set_text(
            ngettext(
                "Hourly forecast · {count} hour",
                "Hourly forecast · {count} hours",
                hourly_count,
            ).format(count=hourly_count)
        )
        self.daily_card.set_visible(bool(bundle.daily))
        daily_count = len(bundle.daily)
        self.daily_title.set_text(
            ngettext(
                "Daily forecast · {count} day",
                "Daily forecast · {count} days",
                daily_count,
            ).format(count=daily_count)
        )
        self._update_alerts(bundle.alerts, show_forecast_signals)
        self._update_hourly(bundle, unit_system)
        self._update_daily(bundle.daily, unit_system)
        self._update_metrics(bundle, unit_system)
        self._update_credits(report)

    def _update_alerts(self, alerts: Iterable[WeatherAlert], show_forecast_signals: bool) -> None:
        _clear(self.alerts_box)
        for alert in alerts:
            if alert.kind == "forecast-signal" and not show_forecast_signals:
                continue
            button = Gtk.Button()
            button.set_css_classes(
                [
                    "alert-card",
                    "official-alert"
                    if alert.official
                    else "service-notice"
                    if alert.kind == "service-notice"
                    else "forecast-signal",
                    "flat",
                ]
            )
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.append(
                Gtk.Image.new_from_icon_name(
                    "weather-severe-alert-symbolic"
                    if alert.official
                    else "network-error-symbolic"
                    if alert.kind == "service-notice"
                    else "dialog-warning-symbolic"
                )
            )
            text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            title = Gtk.Label(label=_alert_title(alert), xalign=0)
            title.set_css_classes(["heading"])
            title.set_wrap(True)
            kind = _alert_kind_label(alert)
            subtitle = Gtk.Label(label=f"{kind} · {alert.source_name}", xalign=0)
            subtitle.set_wrap(True)
            subtitle.set_css_classes(["dim-label", "caption"])
            text_box.append(title)
            text_box.append(subtitle)
            row.append(text_box)
            row.append(Gtk.Image.new_from_icon_name("go-next-symbolic"))
            button.set_child(row)
            button.connect("clicked", lambda _button, item=alert: self._on_alert(item))
            self.alerts_box.append(button)

    def _update_hourly(self, bundle, unit_system: str) -> None:
        _clear(self.hourly_box)
        for hour in bundle.hourly[:48]:
            cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            cell.set_css_classes(["hour-cell"])
            cell.append(Gtk.Label(label=_time_label(hour.time)))
            icon = Gtk.Image.new_from_icon_name(condition_icon(hour.condition_code))
            icon.set_pixel_size(28)
            cell.append(icon)
            value = Gtk.Label(label=temperature(hour.temperature_c, unit_system))
            value.set_css_classes(["heading"])
            cell.append(value)
            rain = Gtk.Label(
                label=(
                    f"{int(hour.precipitation_probability)}%"
                    if hour.precipitation_probability is not None
                    else "—"
                )
            )
            rain.set_css_classes(["dim-label", "caption"])
            cell.append(rain)
            self.hourly_box.append(cell)
        self.graph.set_forecast(bundle.hourly)

    def _update_daily(self, days: Iterable[DailyForecast], unit_system: str) -> None:
        _clear(self.daily_list)
        for day in days:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            box.set_margin_top(8)
            box.set_margin_bottom(8)
            box.set_margin_start(10)
            box.set_margin_end(10)
            date = Gtk.Label(label=localized_date_label(day.date), xalign=0)
            date.set_hexpand(True)
            box.append(date)
            rain = Gtk.Label(
                label=(
                    f"{int(day.precipitation_probability)}%"
                    if day.precipitation_probability is not None
                    else "—"
                )
            )
            rain.set_css_classes(["dim-label", "caption"])
            box.append(rain)
            icon = Gtk.Image.new_from_icon_name(condition_icon(day.condition_code))
            icon.set_tooltip_text(_(condition_label(day.condition_code)))
            box.append(icon)
            minimum = Gtk.Label(label=temperature(day.temperature_min_c, unit_system))
            minimum.set_css_classes(["dim-label"])
            maximum = Gtk.Label(label=temperature(day.temperature_max_c, unit_system))
            maximum.set_css_classes(["heading"])
            box.append(minimum)
            box.append(maximum)
            row.set_child(box)
            self.daily_list.append(row)

    def _update_metrics(self, bundle, unit_system: str) -> None:
        _clear(self.metrics_flow)
        current = bundle.current
        today = bundle.daily[0] if bundle.daily else None
        cards = [
            MetricCard(
                _("Wind"),
                speed(current.wind_speed_kmh, unit_system),
                _("Gusts {value}").format(value=speed(current.wind_gust_kmh, unit_system)),
                "weather-windy-symbolic",
                "metric-wind",
            ),
            MetricCard(
                _("Humidity"),
                f"{current.humidity_percent:.0f}%" if current.humidity_percent is not None else "—",
                icon_name="weather-showers-scattered-symbolic",
                style_class="metric-water",
            ),
            MetricCard(
                _("Pressure"),
                f"{current.pressure_hpa:.0f} hPa" if current.pressure_hpa is not None else "—",
                icon_name="speedometer-symbolic",
                style_class="metric-pressure",
            ),
            MetricCard(
                _("Visibility"),
                visibility(current.visibility_km, unit_system),
                icon_name="view-reveal-symbolic",
                style_class="metric-visibility",
            ),
            MetricCard(
                _("Precipitation"),
                precipitation(today.precipitation_sum_mm if today else None, unit_system),
                _("Today"),
                "weather-showers-symbolic",
                "metric-water",
            ),
            MetricCard(
                _("UV index"),
                f"{today.uv_index_max:.1f}" if today and today.uv_index_max is not None else "—",
                icon_name="weather-clear-symbolic",
                style_class="metric-sun",
            ),
        ]
        if today and (today.sunrise or today.sunset):
            cards.append(
                SunTimesCard(
                    _time_label(today.sunrise) if today.sunrise else "—",
                    _time_label(today.sunset) if today.sunset else "—",
                )
            )
        if bundle.air_quality:
            aqi = bundle.air_quality
            if aqi.us_aqi is not None:
                value = aqi.us_aqi
                value_label = _("US AQI")
                aqi_class, category = _aqi_presentation(value)
            else:
                value = aqi.european_aqi
                value_label = _("European AQI")
                aqi_class, category = _aqi_presentation(value, european=True)
            air_card = MetricCard(
                _("Air quality"),
                f"{value_label} {value:.0f}" if value is not None else _("Details"),
                f"{category} · {_('Open full report')}",
                "weather-fog-symbolic",
                aqi_class,
            )
            air_button = Gtk.Button()
            air_button.set_css_classes(["flat"])
            air_button.set_tooltip_text(_("Open full air-quality report"))
            air_button.set_child(air_card)
            air_button.connect("clicked", lambda _button: self._on_air_quality(aqi))
            cards.insert(0, air_button)
        for card in cards:
            self.metrics_flow.append(card)

    def _update_credits(self, report: WeatherReport) -> None:
        _clear(self.credits_box)
        label = Gtk.Label(label=_("Providers:"))
        label.set_css_classes(["dim-label", "caption"])
        self.credits_box.append(label)
        seen = set()
        for source in report.sources:
            if source.provider_id in seen:
                continue
            seen.add(source.provider_id)
            if source.attribution_url:
                link = Gtk.LinkButton.new_with_label(source.attribution_url, source.provider_name)
                link.set_css_classes(["flat", "caption"])
                self.credits_box.append(link)
            else:
                self.credits_box.append(Gtk.Label(label=source.provider_name))
        if any(source.provider_id in {"open-meteo", "met-norway"} for source in report.sources):
            licence = Gtk.LinkButton.new_with_label(
                "https://creativecommons.org/licenses/by/4.0/",
                "CC BY 4.0",
            )
            licence.set_css_classes(["flat", "caption"])
            self.credits_box.append(licence)
        if report.display.is_consensus:
            normalized = Gtk.Label(label=_("Normalized and combined by Meteo"))
            normalized.set_css_classes(["dim-label", "caption"])
            self.credits_box.append(normalized)
        elif any(
            source.provider_id in {"open-meteo", "met-norway"}
            for source in report.sources
        ):
            normalized = Gtk.Label(label=_("Units and conditions normalized by Meteo"))
            normalized.set_css_classes(["dim-label", "caption"])
            self.credits_box.append(normalized)
