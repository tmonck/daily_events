"""Support for daily calendar event notifications."""

import logging
from datetime import datetime, time, timedelta

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.calendar import SERVICE_GET_EVENTS
from homeassistant.components.calendar.const import DATA_COMPONENT as CALENDAR_COMPONENT
from homeassistant.components.calendar.const import DOMAIN as CALENDAR_DOMAIN
from homeassistant.components.calendar.const import (
    EVENT_END_DATETIME,
    EVENT_START_DATETIME,
)
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, CONF_TIME_ZONE, CONF_TOKEN
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_DATE_FORMAT,
    ATTR_EXCLUDED_CALS,
    ATTR_NAME,
    ATTR_NOTIFY_SERVICES,
    ATTR_TIME_FORMAT,
    DEFAULT_DATE_FORMAT,
    DEFAULT_NOTIFY_SERVICES,
    DEFAULT_NUM,
    DEFAULT_TIME_FORMAT,
    DOMAIN,
    SERVICE_NOTIFY,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
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


class DailyEventsNotifier:
    """Build and send notifications for configured calendars."""

    def __init__(self, hass, config):
        """Initialize the notifier from the YAML configuration."""
        self.hass = hass
        self.user_defined_tz = config.get(CONF_TIME_ZONE, hass.config.time_zone)
        self.num_of_days = config.get(ATTR_NAME, DEFAULT_NUM)
        self.date_format = config.get(ATTR_DATE_FORMAT, DEFAULT_DATE_FORMAT)
        self.time_format = config.get(ATTR_TIME_FORMAT, DEFAULT_TIME_FORMAT)
        self.excluded_calendars = config.get(ATTR_EXCLUDED_CALS, [])
        self.notify_services = config.get(ATTR_NOTIFY_SERVICES, DEFAULT_NOTIFY_SERVICES)

    def get_calendars(self, run_id):
        """Return the configured, available calendar entities."""
        calendars = []
        component = self.hass.data.get(CALENDAR_COMPONENT)
        if component is None:
            return calendars

        for entity in component.entities:
            entity_id = entity.entity_id
            if entity_id in self.excluded_calendars:
                continue
            if not entity.available:
                _LOGGER.debug(
                    "Daily Events run %s: skipping unavailable calendar %s",
                    run_id,
                    entity_id,
                )
                continue
            state = self.hass.states.get(entity_id)
            if state is not None:
                calendars.append({"entity_id": entity_id, "name": state.name})
        return calendars

    async def async_get_events(self, calendars, days_to_add, run_id):
        """Retrieve and format events for the supplied calendars."""
        has_events = False
        notification_message = ""
        timezone = dt_util.get_time_zone(self.user_defined_tz) or dt_util.UTC
        today = dt_util.now(timezone).date()
        today_start = datetime.combine(
            today,
            time.min,
            tzinfo=timezone,
        )
        end_date_time = today_start + timedelta(days=days_to_add)

        for calendar in calendars:
            entity_id = calendar["entity_id"]
            _LOGGER.debug(
                "Daily Events run %s: getting events for %s", run_id, entity_id
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
                    return_response=True,
                )
            except HomeAssistantError:
                _LOGGER.exception(
                    "Daily Events run %s: error getting events for %s",
                    run_id,
                    entity_id,
                )
                continue

            events = response.get(entity_id, {}).get("events", [])
            if not events:
                continue

            has_events = True
            notification_message += "{}:\n".format(calendar["name"])
            for item in events:
                event_start = item["start"]
                if len(event_start) > 10:
                    parsed_date_time = dt_util.parse_datetime(event_start)
                    if parsed_date_time is None:
                        _LOGGER.warning(
                            "Daily Events run %s: skipping event with invalid start time: %s",
                            run_id,
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
                        at_string = "at {}".format(
                            parsed_date_time.strftime(self.time_format)
                        )
                    notification_message += "- {} {}\n".format(
                        item["summary"], at_string
                    )
                else:
                    parsed_date = dt_util.parse_date(event_start)
                    if parsed_date is None:
                        _LOGGER.warning(
                            "Daily Events run %s: skipping event with invalid start date: %s",
                            run_id,
                            event_start,
                        )
                        continue
                    if days_to_add > 1:
                        at_string = " on {}".format(
                            parsed_date.strftime(self.date_format)
                        )
                    else:
                        at_string = ""
                    notification_message += "- {}{}\n".format(
                        item["summary"], at_string
                    )

        if has_events:
            return notification_message
        if days_to_add > 1:
            future = today + timedelta(days=days_to_add - 1)
            return "No Activities for {} - {}".format(
                today.isoformat(), future.isoformat()
            )
        return "No Activities for Today {}".format(today.isoformat())

    async def async_handle_notify(self, call):
        """Handle the daily events notify action."""
        run_id = call.context.id
        days_to_add = call.data.get(ATTR_NAME, self.num_of_days)
        if days_to_add == 0:
            days_to_add = DEFAULT_NUM

        _LOGGER.info("Daily Events run %s started", run_id)
        calendars = self.get_calendars(run_id)
        _LOGGER.debug(
            "Daily Events run %s: selected calendars: %s",
            run_id,
            [calendar["entity_id"] for calendar in calendars],
        )
        notification_message = await self.async_get_events(
            calendars, days_to_add, run_id
        )
        _LOGGER.debug(
            "Daily Events run %s: message to send: %s",
            run_id,
            notification_message,
        )

        for service in self.notify_services:
            await self.hass.services.async_call(
                "notify", service, {"message": notification_message}
            )
            _LOGGER.debug("Daily Events run %s: notify.%s was called", run_id, service)
        _LOGGER.info("Daily Events run %s completed", run_id)


async def async_setup(hass, config):
    """Set up Daily Events from YAML."""
    _LOGGER.info("Setting up daily_events")
    notifier = DailyEventsNotifier(hass, config[DOMAIN])
    hass.services.async_register(DOMAIN, SERVICE_NOTIFY, notifier.async_handle_notify)
    return True
