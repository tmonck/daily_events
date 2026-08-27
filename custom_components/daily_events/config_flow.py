"""Config flow for Daily Events."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.const import ATTR_ENTITY_ID, CONF_NAME, CONF_TIME_ZONE
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_DATE_FORMAT,
    ATTR_EXCLUDED_CALS,
    ATTR_NAME,
    ATTR_NOTIFY_SERVICES,
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
    NOTIFY_DOMAIN,
    NOTIFY_SEND_MESSAGE,
    CalendarMode,
)

CONF_DESTINATION = "destination"
CONF_DESTINATION_INDEX = "destination_index"
YAML_IMPORT_ID = "yaml_import"

TEXT_SELECTOR = selector.TextSelector(selector.TextSelectorConfig())
DAYS_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=1,
        max=365,
        mode=selector.NumberSelectorMode.BOX,
    )
)
CALENDAR_MODE_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[mode.value for mode in CalendarMode],
        mode=selector.SelectSelectorMode.DROPDOWN,
        translation_key="calendar_mode",
    )
)
CALENDAR_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="calendar", multiple=True)
)
NOTIFY_ENTITY_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=NOTIFY_DOMAIN, multiple=True)
)


class _ProfileFlowMixin:
    """Shared profile flow steps."""

    _profile_name: str
    _profile: dict[str, Any]
    _destinations: list[dict[str, Any]]
    _pending_action: str | None
    _editing_destination: int | None
    _profile_step_id: str

    def _profile_schema(self) -> vol.Schema:
        """Return the profile settings schema with current values."""
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): TEXT_SELECTOR,
                vol.Required(CONF_DAYS): DAYS_SELECTOR,
                vol.Required(CONF_CALENDAR_MODE): CALENDAR_MODE_SELECTOR,
                vol.Optional(CONF_TIME_ZONE): TEXT_SELECTOR,
                vol.Required(CONF_DATE_FORMAT): TEXT_SELECTOR,
                vol.Required(CONF_TIME_FORMAT): TEXT_SELECTOR,
            }
        )
        values = {
            CONF_NAME: self._profile_name,
            CONF_DAYS: self._profile.get(CONF_DAYS, DEFAULT_NUM),
            CONF_CALENDAR_MODE: self._profile.get(
                CONF_CALENDAR_MODE, CalendarMode.ALL.value
            ),
            CONF_DATE_FORMAT: self._profile.get(CONF_DATE_FORMAT, DEFAULT_DATE_FORMAT),
            CONF_TIME_FORMAT: self._profile.get(CONF_TIME_FORMAT, DEFAULT_TIME_FORMAT),
        }
        if time_zone := self._profile.get(CONF_TIME_ZONE):
            values[CONF_TIME_ZONE] = time_zone
        return self.add_suggested_values_to_schema(schema, values)

    async def async_step_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure profile defaults and formatting."""
        errors: dict[str, str] = {}
        if user_input is not None:
            profile_name = user_input[CONF_NAME].strip()
            if not profile_name:
                errors[CONF_NAME] = "required"
            time_zone = user_input.get(CONF_TIME_ZONE)
            if time_zone and dt_util.get_time_zone(time_zone) is None:
                errors[CONF_TIME_ZONE] = "invalid_time_zone"
            if not errors:
                self._profile_name = profile_name
                self._profile[CONF_DAYS] = int(user_input[CONF_DAYS])
                self._profile[CONF_DATE_FORMAT] = user_input[CONF_DATE_FORMAT]
                self._profile[CONF_TIME_FORMAT] = user_input[CONF_TIME_FORMAT]
                mode = CalendarMode(user_input[CONF_CALENDAR_MODE])
                self._profile[CONF_CALENDAR_MODE] = mode.value
                if time_zone:
                    self._profile[CONF_TIME_ZONE] = time_zone
                else:
                    self._profile.pop(CONF_TIME_ZONE, None)
                if mode is CalendarMode.ALL:
                    self._profile[CONF_CALENDARS] = []
                    return await self._async_after_calendars()
                return await self.async_step_calendars()

        return self.async_show_form(
            step_id=self._profile_step_id,
            data_schema=self._profile_schema(),
            errors=errors,
        )

    async def async_step_calendar_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select how calendars are filtered."""
        if user_input is not None:
            mode = CalendarMode(user_input[CONF_CALENDAR_MODE])
            self._profile[CONF_CALENDAR_MODE] = mode.value
            if mode is CalendarMode.ALL:
                self._profile[CONF_CALENDARS] = []
                return await self._async_after_calendars()
            return await self.async_step_calendars()

        schema = vol.Schema({vol.Required(CONF_CALENDAR_MODE): CALENDAR_MODE_SELECTOR})
        return self.async_show_form(
            step_id="calendar_mode",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    CONF_CALENDAR_MODE: self._profile.get(
                        CONF_CALENDAR_MODE, CalendarMode.ALL
                    )
                },
            ),
        )

    async def async_step_calendars(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select calendars for include or exclude mode."""
        errors: dict[str, str] = {}
        if user_input is not None:
            calendars = user_input[CONF_CALENDARS]
            if not calendars:
                errors[CONF_CALENDARS] = "at_least_one_calendar"
            else:
                self._profile[CONF_CALENDARS] = calendars
                return await self._async_after_calendars()

        schema = vol.Schema({vol.Required(CONF_CALENDARS): CALENDAR_SELECTOR})
        return self.async_show_form(
            step_id="calendars",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {CONF_CALENDARS: self._profile.get(CONF_CALENDARS, [])},
            ),
            errors=errors,
            description_placeholders={"mode": self._profile[CONF_CALENDAR_MODE]},
        )

    async def _async_after_calendars(self) -> ConfigFlowResult:
        """Continue to destination setup or management."""
        if self._destinations:
            return await self.async_step_destination_menu()
        return await self.async_step_destination()

    def _notify_actions(self) -> list[str]:
        """Return currently registered notification actions."""
        services = self.hass.services.async_services().get(NOTIFY_DOMAIN, {})
        return [f"{NOTIFY_DOMAIN}.{service}" for service in sorted(services)]

    async def async_step_destination(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select a notification action."""
        actions = self._notify_actions()
        if not actions:
            return self.async_abort(reason="no_notification_actions")

        if user_input is not None:
            self._pending_action = user_input[CONF_ACTION]
            if self._pending_action == NOTIFY_SEND_MESSAGE:
                return await self.async_step_destination_target()
            self._save_destination({CONF_ACTION: self._pending_action})
            return await self.async_step_destination_menu()

        action_selector = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=actions,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )
        suggested_action = None
        if self._editing_destination is not None:
            suggested_action = self._destinations[self._editing_destination][
                CONF_ACTION
            ]
        schema = vol.Schema({vol.Required(CONF_ACTION): action_selector})
        return self.async_show_form(
            step_id="destination",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {CONF_ACTION: suggested_action} if suggested_action else {},
            ),
        )

    async def async_step_destination_target(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select entities targeted by a notification action."""
        errors: dict[str, str] = {}
        if user_input is not None:
            entities = user_input[ATTR_ENTITY_ID]
            if not entities:
                errors[ATTR_ENTITY_ID] = "at_least_one_notify_entity"
            else:
                self._save_destination(
                    {
                        CONF_ACTION: self._pending_action,
                        CONF_TARGET: {ATTR_ENTITY_ID: entities},
                    }
                )
                return await self.async_step_destination_menu()

        current_entities: list[str] = []
        if self._editing_destination is not None:
            current_entities = (
                self._destinations[self._editing_destination]
                .get(CONF_TARGET, {})
                .get(ATTR_ENTITY_ID, [])
            )
        schema = vol.Schema({vol.Required(ATTR_ENTITY_ID): NOTIFY_ENTITY_SELECTOR})
        return self.async_show_form(
            step_id="destination_target",
            data_schema=self.add_suggested_values_to_schema(
                schema, {ATTR_ENTITY_ID: current_entities}
            ),
            errors=errors,
        )

    def _save_destination(self, destination: dict[str, Any]) -> None:
        """Add or replace a notification destination."""
        if self._editing_destination is None:
            self._destinations.append(destination)
        else:
            self._destinations[self._editing_destination] = destination
        self._editing_destination = None
        self._pending_action = None

    def _destination_options(self) -> list[dict[str, str]]:
        """Return destination choices for edit and removal forms."""
        options = []
        for index, destination in enumerate(self._destinations):
            label = destination[CONF_ACTION]
            entities = destination.get(CONF_TARGET, {}).get(ATTR_ENTITY_ID, [])
            if entities:
                label = f"{label}: {', '.join(entities)}"
            options.append({"value": str(index), "label": label})
        return options

    async def async_step_destination_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage notification destinations."""
        destination_summary = ", ".join(
            destination[CONF_ACTION] for destination in self._destinations
        )
        return self.async_show_menu(
            step_id="destination_menu",
            menu_options={
                "add_destination": "Add destination",
                "edit_destination": f"Edit destinations ({destination_summary})",
                "remove_destination": f"Remove destinations ({destination_summary})",
                "finish": "Finish",
            },
        )

    async def async_step_add_destination(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add another destination."""
        self._editing_destination = None
        return await self.async_step_destination()

    async def async_step_edit_destination(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a destination to edit."""
        if user_input is not None:
            self._editing_destination = int(user_input[CONF_DESTINATION_INDEX])
            return await self.async_step_destination()
        return self._destination_choice_form("edit_destination")

    async def async_step_remove_destination(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove a notification destination."""
        if user_input is not None:
            self._destinations.pop(int(user_input[CONF_DESTINATION_INDEX]))
            if not self._destinations:
                return await self.async_step_destination()
            return await self.async_step_destination_menu()
        return self._destination_choice_form("remove_destination")

    def _destination_choice_form(self, step_id: str) -> ConfigFlowResult:
        """Return a form for selecting a configured destination."""
        destination_selector = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=self._destination_options(),
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {vol.Required(CONF_DESTINATION_INDEX): destination_selector}
            ),
        )

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Save the completed profile."""
        self._profile[CONF_NOTIFICATION_DESTINATIONS] = deepcopy(self._destinations)
        return self._finish_profile()

    def _finish_profile(self) -> ConfigFlowResult:
        """Persist the profile in the concrete flow."""
        raise NotImplementedError


class DailyEventsConfigFlow(
    _ProfileFlowMixin, config_entries.ConfigFlow, domain=DOMAIN
):
    """Handle a Daily Events config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._profile_name = "Daily Events"
        self._profile = {}
        self._destinations = []
        self._pending_action = None
        self._editing_destination = None
        self._profile_step_id = "user"

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> DailyEventsOptionsFlow:
        """Return the options flow handler."""
        return DailyEventsOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a user-created profile."""
        return await self.async_step_profile(user_input)

    async def async_step_import(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Import the legacy YAML configuration."""
        assert user_input is not None
        await self.async_set_unique_id(YAML_IMPORT_ID)
        self._abort_if_unique_id_configured()

        excluded_calendars = user_input.get(ATTR_EXCLUDED_CALS, [])
        notify_services = user_input.get(ATTR_NOTIFY_SERVICES, DEFAULT_NOTIFY_SERVICES)
        destinations = []
        for service in notify_services:
            action = service if service.startswith("notify.") else f"notify.{service}"
            destinations.append({CONF_ACTION: action})

        options = {
            CONF_CALENDAR_MODE: (
                CalendarMode.EXCLUDE.value
                if excluded_calendars
                else CalendarMode.ALL.value
            ),
            CONF_CALENDARS: excluded_calendars,
            CONF_NOTIFICATION_DESTINATIONS: destinations,
            CONF_DAYS: user_input.get(ATTR_NAME, DEFAULT_NUM),
            CONF_DATE_FORMAT: user_input.get(ATTR_DATE_FORMAT, DEFAULT_DATE_FORMAT),
            CONF_TIME_FORMAT: user_input.get(ATTR_TIME_FORMAT, DEFAULT_TIME_FORMAT),
        }
        if time_zone := user_input.get(CONF_TIME_ZONE):
            options[CONF_TIME_ZONE] = time_zone
        return self.async_create_entry(
            title="Imported Daily Events", data={}, options=options
        )

    def _finish_profile(self) -> ConfigFlowResult:
        """Create the profile config entry."""
        return self.async_create_entry(
            title=self._profile_name,
            data={},
            options=self._profile,
        )


class DailyEventsOptionsFlow(_ProfileFlowMixin, config_entries.OptionsFlow):
    """Edit a Daily Events profile."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Initialize profile editing."""
        self._profile_step_id = "profile"
        self._profile_name = self.config_entry.title
        self._profile = dict(self.config_entry.options)
        self._destinations = deepcopy(
            self._profile.get(CONF_NOTIFICATION_DESTINATIONS, [])
        )
        self._pending_action = None
        self._editing_destination = None
        return await self.async_step_profile(user_input)

    def _finish_profile(self) -> ConfigFlowResult:
        """Update the profile options and title."""
        self.hass.config_entries.async_update_entry(
            self.config_entry, title=self._profile_name
        )
        return self.async_create_entry(data=self._profile)
