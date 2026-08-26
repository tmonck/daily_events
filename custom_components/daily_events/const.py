from typing import Final

DOMAIN: Final = "daily_events"
NAME: Final = "Daily Events"

SERVICE_NOTIFY: Final = "notify"

ATTR_NAME: Final = "num_of_days"
ATTR_DATE_FORMAT: Final = "date_output_format"
ATTR_TIME_FORMAT: Final = "time_output_format"
ATTR_EXCLUDED_CALS: Final = "excluded_calendars"
ATTR_NOTIFY_SERVICES: Final = "notify_services"

DEFAULT_DATE_FORMAT: Final = "%a, %b %d %Y"
DEFAULT_TIME_FORMAT: Final = "%I:%M %p"
DEFAULT_NUM: Final = 1
DEFAULT_NOTIFY_SERVICES: Final = ["html5"]
DEFAULT_TIME_ZONE: Final = "UTC"
