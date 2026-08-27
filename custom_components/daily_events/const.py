"""Constants for Daily Events."""

from enum import StrEnum
from typing import Final

DOMAIN: Final = "daily_events"
NAME: Final = "Daily Events"

SERVICE_NOTIFY: Final = "notify"

ATTR_PROFILE: Final = "profile"

ATTR_NAME: Final = "num_of_days"
ATTR_DATE_FORMAT: Final = "date_output_format"
ATTR_TIME_FORMAT: Final = "time_output_format"
ATTR_EXCLUDED_CALS: Final = "excluded_calendars"
ATTR_NOTIFY_SERVICES: Final = "notify_services"

CONF_CALENDAR_MODE: Final = "calendar_mode"
CONF_CALENDARS: Final = "calendars"
CONF_DAYS: Final = "days"
CONF_NOTIFICATION_DESTINATIONS: Final = "notification_destinations"
CONF_ACTION: Final = "action"
CONF_TARGET: Final = "target"
CONF_DATE_FORMAT: Final = "date_format"
CONF_TIME_FORMAT: Final = "time_format"

NOTIFY_DOMAIN: Final = "notify"
NOTIFY_SEND_MESSAGE: Final = "notify.send_message"

DEFAULT_DATE_FORMAT: Final = "%a, %b %d %Y"
DEFAULT_TIME_FORMAT: Final = "%I:%M %p"
DEFAULT_NUM: Final = 1
DEFAULT_NOTIFY_SERVICES: Final = ["html5"]
DEFAULT_TIME_ZONE: Final = "UTC"


class CalendarMode(StrEnum):
    """Calendar selection modes."""

    ALL = "all"
    INCLUDE = "include"
    EXCLUDE = "exclude"
