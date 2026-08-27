"""Support for daily calendar event notifications."""

import logging
from datetime import datetime, time, timedelta
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.calendar import SERVICE_GET_EVENTS
from homeassistant.components.calendar.const import DATA_COMPONENT as CALENDAR_COMPONENT
from homeassistant.components.calendar.const import DOMAIN as CALENDAR_DOMAIN
from homeassistant.components.calendar.const import (
    EVENT_END_DATETIME,
    EVENT_START_DATETIME,
)
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, CONF_TIME_ZONE, CONF_TOKEN
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_DATE_FORMAT,
    ATTR_EXCLUDED_CALS,
    ATTR_NAME,
    ATTR_NOTIFY_SERVICES,
    ATTR_PROFILE,
    ATTR_TIME_FORMAT,
    CONF_ACTION,
    CONF_CALENDAR_MODE,
    CONF_CALENDARS,
    CONF_DATE_FORMAT,
    CONF_DAYS,
    CONF_NOTIFICATION_DESTINATIONS,
    CONF_TARGET,
    CONF_TIME_FORMAT,
    DEFAULT_DATE_FORMAT,
    DEFAULT_NOTIFY_SERVICES,
    DEFAULT_NUM,
    DEFAULT_TIME_FORMAT,
    DOMAIN,
    SERVICE_NOTIFY,
    CalendarMode,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(DOMAIN): vol.Schema(
            {
                vol.Optional(CONF_HOST): cv.string,
                vol.Optional(CONF_TOKEN): cv.string,
                vol.Optional(ATTR_NAME, default=DEFAULT_NUM): int,
                vol.Optional(CONF_TIME_ZONE): cv.time_zone,
                vol.Optional(ATTR_DATE_FORMAT, default=DEFAULT_DATE_FORMAT): cv.string,
                vol.Optional(ATTR_TIME_FORMAT, default=DEFAULT_TIME_FORMAT): cv.string,
                vol.Optional(ATTR_EXCLUDED_CALS, default=[]): [cv.entity_id],
                vol.Optional(ATTR_NOTIFY_SERVICES, default=DEFAULT_NOTIFY_SERVICES): [
                    cv.string
                ],
            }
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

SERVICE_NOTIFY_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_PROFILE): cv.string,
        vol.Optional(ATTR_NAME): vol.All(vol.Coerce(int), vol.Range(min=0)),
    }
)


class DailyEventsNotifier:
    """Build and send notifications for one profile."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        title: str,
        options: dict[str, Any],
    ) -> None:
        """Initialize a notification profile."""
        self.hass = hass
        self.entry_id = entry_id
        self.title = title
        self.calendar_mode = CalendarMode(
            options.get(CONF_CALENDAR_MODE, CalendarMode.ALL)
        )
        self.calendars = set(options.get(CONF_CALENDARS, []))
        self.notification_destinations = options.get(CONF_NOTIFICATION_DESTINATIONS, [])
        self.num_of_days = options.get(CONF_DAYS, DEFAULT_NUM)
        self.user_defined_tz = options.get(CONF_TIME_ZONE, hass.config.time_zone)
        self.date_format = options.get(CONF_DATE_FORMAT, DEFAULT_DATE_FORMAT)
        self.time_format = options.get(CONF_TIME_FORMAT, DEFAULT_TIME_FORMAT)

    def get_calendars(self, run_id: str) -> list[dict[str, str]]:
        """Return the available calendar entities selected by the profile."""
        calendars: list[dict[str, str]] = []
        component = self.hass.data.get(CALENDAR_COMPONENT)
        if component is None:
            return calendars

        for entity in component.entities:
            entity_id = entity.entity_id
            if self.calendar_mode is CalendarMode.INCLUDE:
                if entity_id not in self.calendars:
                    continue
            elif (
                self.calendar_mode is CalendarMode.EXCLUDE
                and entity_id in self.calendars
            ):
                continue
            if not entity.available:
                _LOGGER.debug(
                    "Daily Events run %s profile %s: skipping unavailable calendar %s",
                    run_id,
                    self.entry_id,
                    entity_id,
                )
                continue
            state = self.hass.states.get(entity_id)
            if state is not None:
                calendars.append({"entity_id": entity_id, "name": state.name})
        return calendars

    async def async_get_events(
        self,
        calendars: list[dict[str, str]],
        days_to_add: int,
        run_id: str,
        context,
    ) -> str:
        """Retrieve and format events for the supplied calendars."""
        has_events = False
        notification_message = ""
        timezone = dt_util.get_time_zone(self.user_defined_tz) or dt_util.UTC
        today = dt_util.now(timezone).date()
        today_start = datetime.combine(today, time.min, tzinfo=timezone)
        end_date_time = today_start + timedelta(days=days_to_add)

        for calendar in calendars:
            entity_id = calendar["entity_id"]
            _LOGGER.debug(
                "Daily Events run %s profile %s: getting events for %s",
                run_id,
                self.entry_id,
                entity_id,
            )
            try:
                response = await self.hass.services.async_call(
                    CALENDAR_DOMAIN,
                    SERVICE_GET_EVENTS,
                    {
                        ATTR_ENTITY_ID: entity_id,
                        EVENT_START_DATETIME: today_start,
                        EVENT_END_DATETIME: end_date_time,
                    },
                    blocking=True,
                    context=context,
                    return_response=True,
                )
            except HomeAssistantError:
                _LOGGER.exception(
                    "Daily Events run %s profile %s: error getting events for %s",
                    run_id,
                    self.entry_id,
                    entity_id,
                )
                continue

            events = response.get(entity_id, {}).get("events", [])
            if not events:
                continue

            has_events = True
            notification_message += f'{calendar["name"]}:\n'
            for item in events:
                event_start = item["start"]
                if len(event_start) > 10:
                    parsed_date_time = dt_util.parse_datetime(event_start)
                    if parsed_date_time is None:
                        _LOGGER.warning(
                            "Daily Events run %s profile %s: skipping event with invalid start time: %s",
                            run_id,
                            self.entry_id,
                            event_start,
                        )
                        continue
                    parsed_date_time = parsed_date_time.astimezone(timezone)
                    if days_to_add > 1:
                        at_string = "on {} at {}".format(
                            parsed_date_time.strftime(self.date_format),
                            parsed_date_time.strftime(self.time_format),
                        )
                    else:
                        at_string = f"at {parsed_date_time.strftime(self.time_format)}"
                    notification_message += f'- {item["summary"]} {at_string}\n'
                else:
                    parsed_date = dt_util.parse_date(event_start)
                    if parsed_date is None:
                        _LOGGER.warning(
                            "Daily Events run %s profile %s: skipping event with invalid start date: %s",
                            run_id,
                            self.entry_id,
                            event_start,
                        )
                        continue
                    at_string = (
                        f" on {parsed_date.strftime(self.date_format)}"
                        if days_to_add > 1
                        else ""
                    )
                    notification_message += f'- {item["summary"]}{at_string}\n'

        if has_events:
            return notification_message
        if days_to_add > 1:
            future = today + timedelta(days=days_to_add - 1)
            return f"No Activities for {today.isoformat()} - {future.isoformat()}"
        return f"No Activities for Today {today.isoformat()}"

    async def async_notify(self, call: ServiceCall) -> None:
        """Build and send this profile's notification."""
        run_id = call.context.id
        days_to_add = call.data.get(ATTR_NAME, self.num_of_days) or DEFAULT_NUM
        _LOGGER.info(
            "Daily Events run %s profile %s (%s) started",
            run_id,
            self.entry_id,
            self.title,
        )
        calendars = self.get_calendars(run_id)
        _LOGGER.debug(
            "Daily Events run %s profile %s: selected calendars: %s",
            run_id,
            self.entry_id,
            [calendar["entity_id"] for calendar in calendars],
        )
        notification_message = await self.async_get_events(
            calendars, days_to_add, run_id, call.context
        )
        _LOGGER.debug(
            "Daily Events run %s profile %s: message to send: %s",
            run_id,
            self.entry_id,
            notification_message,
        )

        for destination in self.notification_destinations:
            action = destination[CONF_ACTION]
            domain, service = action.split(".", 1)
            await self.hass.services.async_call(
                domain,
                service,
                {"message": notification_message},
                target=destination.get(CONF_TARGET),
                blocking=True,
                context=call.context,
            )
            _LOGGER.debug(
                "Daily Events run %s profile %s: %s was called",
                run_id,
                self.entry_id,
                action,
            )
        _LOGGER.info("Daily Events run %s profile %s completed", run_id, self.entry_id)


def _get_profile(hass: HomeAssistant, entry_id: str) -> DailyEventsNotifier:
    """Return a loaded Daily Events profile."""
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(f"Daily Events profile {entry_id} was not found")
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            f"Daily Events profile {entry.title} is not loaded"
        )
    return hass.data[DOMAIN][entry_id]


async def _async_handle_notify(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the Daily Events notify action."""
    if entry_id := call.data.get(ATTR_PROFILE):
        profiles = [_get_profile(hass, entry_id)]
    else:
        profiles = list(hass.data[DOMAIN].values())
    if not profiles:
        raise ServiceValidationError("No Daily Events profiles are loaded")
    for profile in profiles:
        await profile.async_notify(call)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Daily Events and its global action."""
    hass.data.setdefault(DOMAIN, {})

    async def async_handle_notify(call: ServiceCall) -> None:
        """Handle the Daily Events notify action."""
        await _async_handle_notify(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_NOTIFY,
        async_handle_notify,
        schema=SERVICE_NOTIFY_SCHEMA,
    )

    if yaml_config := config.get(DOMAIN):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_IMPORT},
                data=yaml_config,
            )
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Daily Events profile."""
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = DailyEventsNotifier(
        hass, entry.entry_id, entry.title, dict(entry.options)
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Daily Events profile."""
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a profile after its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
