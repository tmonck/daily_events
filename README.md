## Installation instructions:

1. Install HACS for Home Assistant
2. Add this repo as a custom repository
3. Install
4. Restart Home Assistant
5. Generate a Long Lived Token
    1. Navigate to your profile page.
    1. At the bottom of the page you will see a section called Long-Lived Access Tokens.
    1. Click create.
    1. In the pop up give your token a name.
    1. Copy the token from the following pop up **This will not be saved anywhere so put it somehwere you can find it again**
5. Copy resulting token input this in configuration.yaml:

```yaml
daily_events:
  host: {{the url to access your homeassistant instance}}
  token: {{Long-Lived Access token}}
  # Below items are optional
  # Number of days you want notifications for defaults to 1 and if you set to 0 it overrides to 1
  num_of_days: 1
  # Calendars you wish to exclude
  excluded_calendars:
    - calendar.holidays_in_united_states
  # The notification services you wish to use Defaults to html5
  notify_services:
    - html5
  # Time zone will take any ISO 3166 timezone string that is support by pytz
  time_zone: 'US/Pacific'
  # The date and time output formats take standard python strftime directives http://strftime.org/ defaults are the ones specified in this example
  date_output_format: "%a, %b %d %Y"
  time_output_format: "%I:%M %p"
```

7. Restart Home Assistant
8. Look for the new daily_event.notify Services in services.

## Consumption in automations
You can trigger this service in an automation similarly to the one below.
```yaml
alias: Daily Events Notification
initial_state: 'on'
trigger: 
  platform: time
  at: '03:00:00'
condition:
action:
  - service: daily_events.notify
    # Data is optional if you have defined the number of snapshots to keep in the configuration.yaml.
    data:
      # If this property is passed to the service it will be used regardless of what you have in the configuration.yaml
      num_of_days: 2
```
---
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)