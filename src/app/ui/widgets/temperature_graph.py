# Copyright (C) 2026 Vicente José Leiva Escárate
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import List

from gi.repository import Gtk

from app.i18n import _
from app.models import HourlyForecast


class TemperatureGraph(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self._hours: List[HourlyForecast] = []
        self.set_content_height(170)
        self.set_hexpand(True)
        self.set_tooltip_text(
            _("Temperature curve and precipitation probability for the next 24 hours")
        )
        self.update_property(
            [Gtk.AccessibleProperty.LABEL, Gtk.AccessibleProperty.DESCRIPTION],
            [
                _("Temperature and precipitation graph"),
                _("The same values are available in the hourly forecast directly above."),
            ],
        )
        self.set_draw_func(self._draw)

    def set_forecast(self, hours: List[HourlyForecast]) -> None:
        self._hours = hours[:24]
        self.queue_draw()

    def _draw(self, _area, context, width: int, height: int) -> None:
        if len(self._hours) < 2 or width <= 40 or height <= 40:
            return

        margin_x = 24.0
        margin_y = 22.0
        graph_width = width - margin_x * 2
        graph_height = height - margin_y * 2
        temperatures = [hour.temperature_c for hour in self._hours]
        low = min(temperatures)
        high = max(temperatures)
        spread = max(1.0, high - low)

        # Precipitation bars.
        bar_width = graph_width / len(self._hours)
        context.set_source_rgba(0.20, 0.60, 0.95, 0.22)
        for index, hour in enumerate(self._hours):
            probability = max(0.0, min(100.0, float(hour.precipitation_probability or 0.0)))
            bar_height = graph_height * 0.38 * probability / 100.0
            x = margin_x + index * bar_width
            context.rectangle(x, height - margin_y - bar_height, max(2.0, bar_width - 2.0), bar_height)
            context.fill()

        # Temperature curve.
        context.set_line_width(3.0)
        context.set_line_cap(1)
        context.set_line_join(1)
        context.set_source_rgb(0.98, 0.67, 0.18)
        for index, value in enumerate(temperatures):
            x = margin_x + graph_width * index / (len(temperatures) - 1)
            y = margin_y + graph_height * (high - value) / spread * 0.72
            if index == 0:
                context.move_to(x, y)
            else:
                context.line_to(x, y)
        context.stroke()

        context.set_source_rgb(0.98, 0.76, 0.33)
        for index, value in enumerate(temperatures):
            x = margin_x + graph_width * index / (len(temperatures) - 1)
            y = margin_y + graph_height * (high - value) / spread * 0.72
            context.arc(x, y, 3.5, 0.0, 6.28318)
            context.fill()
