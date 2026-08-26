# Daily Events Notification Service

Daily Events builds a notification containing events from your Home Assistant
calendar entities.

## Installation

1. Install HACS for Home Assistant.
2. Add this repository as a custom repository.
3. Install the integration.
4. Restart Home Assistant.
5. Add `daily_events` to `configuration.yaml`.

```yaml
daily_events:
  # Optional: Number of days to include. Defaults to 1.
  num_of_days: 1

  # Optional: Calendars to exclude.
  excluded_calendars:
    - calendar.holidays_in_united_states

  # Optional: Notification actions, without the "notify." prefix.
  # Defaults to html5.
  notify_services:
    - mobile_app_toms_phone

  # Optional: IANA timezone. Defaults to Home Assistant's configured timezone.
  time_zone: America/Los_Angeles

  # Optional: Python strftime formats.
  date_output_format: "%a, %b %d %Y"
  time_output_format: "%I:%M %p"
```

Restart Home Assistant after changing the YAML configuration. The
`daily_events.notify` action will then be available under Settings > Developer
Tools > Actions.

## Automation Example

```yaml
alias: Daily Events Notification
triggers:
  - trigger: time
    at: "03:00:00"
actions:
  - action: daily_events.notify
    data:
      # Overrides the configured number of days for this invocation.
      num_of_days: 2
```

[![HACS badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
