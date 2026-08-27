"""Tests for the Daily Events integration."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.calendar.const import DATA_COMPONENT
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import Context, ServiceCall

from custom_components.daily_events import DailyEventsNotifier, _async_handle_notify
from custom_components.daily_events.const import (
    CONF_ACTION,
    CONF_CALENDAR_MODE,
    CONF_CALENDARS,
    CONF_DATE_FORMAT,
    CONF_DAYS,
    CONF_NOTIFICATION_DESTINATIONS,
    CONF_TARGET,
    CONF_TIME_FORMAT,
    DOMAIN,
    CalendarMode,
)


def _calendar_entity(entity_id: str, available: bool = True):
    """Create the minimal calendar entity used by the notifier."""
    return SimpleNamespace(entity_id=entity_id, available=available)


def _notifier(hass, **options):
    """Create a notifier with deterministic profile settings."""
    defaults = {
        CONF_DAYS: 1,
        CONF_DATE_FORMAT: "%Y-%m-%d",
        CONF_TIME_FORMAT: "%H:%M",
        CONF_NOTIFICATION_DESTINATIONS: [],
    }
    defaults.update(options)
    return DailyEventsNotifier(hass, "profile-id", "Test profile", defaults)


def test_get_calendars_filters_mode_and_unavailable(hass):
    """Only available calendars matching the profile are selected."""
    hass.data[DATA_COMPONENT] = SimpleNamespace(
        entities=[
            _calendar_entity("calendar.family"),
            _calendar_entity("calendar.work"),
            _calendar_entity("calendar.unavailable", available=False),
        ]
    )
    hass.states.async_set("calendar.family", "off")
    hass.states.async_set("calendar.work", "off")

    notifier = _notifier(
        hass,
        **{
            CONF_CALENDAR_MODE: CalendarMode.INCLUDE,
            CONF_CALENDARS: ["calendar.family", "calendar.unavailable"],
        },
    )

    assert notifier.get_calendars("run-id") == [
        {"entity_id": "calendar.family", "name": "family"}
    ]


@pytest.mark.asyncio
async def test_get_events_formats_timed_and_all_day_events(hass, freezer):
    """Calendar action responses are formatted into the notification text."""
    freezer.move_to("2026-08-26 08:00:00+00:00")
    response = {
        "calendar.family": {
            "events": [
                {"summary": "Breakfast", "start": "2026-08-26"},
                {
                    "summary": "Meeting",
                    "start": "2026-08-26T09:30:00+00:00",
                },
            ]
        }
    }
    with patch.object(
        type(hass.services), "async_call", new=AsyncMock(return_value=response)
    ):
        notifier = _notifier(hass, **{CONF_DAYS: 2, "time_zone": "UTC"})
        message = await notifier.async_get_events(
            [{"entity_id": "calendar.family", "name": "Family"}],
            2,
            "run-id",
            Context(),
        )

    assert "Family:\n" in message
    assert "- Breakfast on 2026-08-26\n" in message
    assert "- Meeting on 2026-08-26 at 09:30\n" in message


@pytest.mark.asyncio
async def test_selected_profile_sends_configured_destination(hass):
    """The selected profile sends its generated message to its action."""
    hass.data[DOMAIN] = {}
    notifier = _notifier(
        hass,
        **{
            CONF_NOTIFICATION_DESTINATIONS: [
                {
                    CONF_ACTION: "notify.send_message",
                    CONF_TARGET: {ATTR_ENTITY_ID: ["notify.phone"]},
                }
            ]
        },
    )
    notifier.get_calendars = lambda run_id: []
    notifier.async_get_events = AsyncMock(return_value="No Activities")
    hass.data[DOMAIN]["profile-id"] = notifier
    with patch.object(type(hass.services), "async_call", new=AsyncMock()) as mock_call:
        call = ServiceCall(hass, DOMAIN, "notify", {}, context=Context())
        await _async_handle_notify(hass, call)

    assert any(
        invocation.args[:2] == ("notify", "send_message")
        and invocation.kwargs["target"] == {ATTR_ENTITY_ID: ["notify.phone"]}
        for invocation in mock_call.await_args_list
    )
