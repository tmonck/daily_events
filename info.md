# Daily Events Notification Service

Daily Events builds a notification containing events from your Home Assistant
calendar entities.

## Installation

1. Install HACS for Home Assistant.
2. Add this repository as a custom repository.
3. Install the integration.
4. Restart Home Assistant.
5. Add a Daily Events profile through **Settings > Devices & services > Add integration**.

Configure profiles through their config-entry options. The
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
