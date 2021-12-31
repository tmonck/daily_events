"""
Support for automating the deletion of snapshots.
"""
import logging
import asyncio
import aiohttp
import async_timeout
import json
from urllib.parse import urlparse
from datetime import datetime, date, time, timedelta
from dateutil.parser import parse
import pytz


from homeassistant.const import (CONF_HOST, CONF_TOKEN, CONF_ENTITY_ID, CONF_TIME_ZONE )
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'daily_events'
ATTR_NAME = 'num_of_days'
ATTR_DATE_FORMAT = 'date_output_format'
ATTR_TIME_FORMAT = 'time_output_format'
ATTR_EXCLUDED_CALS = 'excluded_calendars'
ATTR_NOTIFY_SERVICES = 'notify_services'
DEFAULT_DATE_FORMAT = "%a, %b %d %Y"
DEFAULT_TIME_FORMAT = "%I:%M %p"
DEFAULT_NUM = 1
DEFAULT_NOTIFY_SERVICES = ['html5']
DEFAULT_TIME_ZONE = 'UTC'

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_TOKEN): cv.string,
        vol.Optional(ATTR_NAME, default=DEFAULT_NUM): int,
        vol.Optional(CONF_TIME_ZONE, default=DEFAULT_TIME_ZONE): vol.In(pytz.all_timezones),
        vol.Optional(ATTR_DATE_FORMAT, default=DEFAULT_DATE_FORMAT): cv.string,
        vol.Optional(ATTR_TIME_FORMAT, default=DEFAULT_TIME_FORMAT): cv.string,
        vol.Optional(ATTR_EXCLUDED_CALS, default=[]): [cv.entity_id],
        vol.Optional(ATTR_NOTIFY_SERVICES, default=DEFAULT_NOTIFY_SERVICES): [cv.string],
    }),
}, extra=vol.ALLOW_EXTRA)

async def async_setup(hass, config):
    _LOGGER.info('setting up daily_activities')
    conf = config[DOMAIN]
    hassio_url = '{}/api/'.format(conf.get(CONF_HOST))
    auth_token = conf.get(CONF_TOKEN)
    headers = {'authorization': "Bearer {}".format(auth_token)}
    user_defined_tz = conf.get(CONF_TIME_ZONE, DEFAULT_TIME_ZONE)
    num_of_days = conf.get(ATTR_NAME, DEFAULT_NUM)
    date_format = conf.get(ATTR_DATE_FORMAT, DEFAULT_DATE_FORMAT)
    time_format = conf.get(ATTR_TIME_FORMAT, DEFAULT_TIME_FORMAT)
    excluded_calendars = conf.get(ATTR_EXCLUDED_CALS, [])
    notify_services_to_call = conf.get(ATTR_NOTIFY_SERVICES, DEFAULT_NOTIFY_SERVICES)
    hasEvents = False

    async def async_get_calendars():
        _LOGGER.info('Calling get calendars')
        async with aiohttp.ClientSession(raise_for_status=True) as session:
            try:
                with async_timeout.timeout(10):
                    resp = await session.get(hassio_url + 'calendars', headers=headers, ssl=not isgoodipv4(urlparse(hassio_url).netloc))
                data = await resp.json()
                await session.close()
                return data
            except aiohttp.ClientError:
                _LOGGER.error("Client error on calling get calendars", exc_info=True)
                await session.close()
            except asyncio.TimeoutError:
                _LOGGER.error("Client timeout error on get calendars", exc_info=True)
                await session.close()
            except Exception: 
                _LOGGER.error("Unknown exception thrown", exc_info=True)
                await session.close()

    async def async_get_events(calendars, days_to_add):
        hasEvents = False
        notificationMessage = ''
        # Get current date by user defined timezone
        todayByTz = datetime.now(pytz.timezone(user_defined_tz))

        # Get current date with time of midnight and timezone offset
        todayStart = datetime.combine(todayByTz, time()).astimezone(todayByTz.tzinfo)
        # Get future date with time of midnight (timezone offset is included due to todayStart having astimezone)
        endDateTime = todayStart + timedelta(days=days_to_add)
        for calendar in calendars:
            async with aiohttp.ClientSession(raise_for_status=True) as session:
                _LOGGER.info('Attempting to get events for calendar: calendar=%s', calendar['entity_id'])
                # call hassio API deletion
                try:
                    with async_timeout.timeout(10):
                        resp = await session.get(
                            "{}calendars/{}?start={}&end={}".format(
                                hassio_url, calendar['entity_id'],
                                todayStart.isoformat(),
                                endDateTime.isoformat()
                            ),
                            headers=headers,
                            ssl=not isgoodipv4(urlparse(hassio_url).netloc)
                        )
                    res = await resp.json()
                    _LOGGER.info(res)
                    if len(res) > 0:
                        hasEvents = True
                        _LOGGER.info("received {}".format(len(res)))
                        notificationMessage += "{}:\n".format(calendar['name'])
                        for item in res:
                            if 'dateTime' in item['start'].keys():
                                parsedDateTime = parse(item['start']['dateTime']).astimezone(pytz.timezone(user_defined_tz))
                                if days_to_add > 1:
                                    atString = "on {} at {}".format(
                                        parsedDateTime.strftime("{}".format(date_format)),
                                        parsedDateTime.strftime("{}".format(time_format)))
                                else:
                                    atString = "at {}".format(parsedDateTime.strftime("{}".format(time_format)))
                                notificationMessage += "- {} {}\n".format(
                                    item['summary'],
                                    atString
                                )
                            else:
                                if days_to_add > 1:
                                    parsedDate = parse(item['start']['date'])
                                    atString = " on {}".format(parsedDate.strftime("{}".format(date_format)))
                                else:
                                    atString = ""
                                notificationMessage += "- {}{}\n".format(item['summary'], atString)
                    _LOGGER.debug("current notificationMessage {}".format(notificationMessage))
                    
                    await session.close()
                except aiohttp.ClientError:
                    _LOGGER.error("Client error on calling get events for calendar", exc_info=True)
                    await session.close()
                except asyncio.TimeoutError:
                    _LOGGER.error("Client timeout error on get events for calendar", exc_info=True)
                    await session.close()
                except Exception: 
                    _LOGGER.error("Unknown exception thrown on calling get events for calendar", exc_info=True)
                    await session.close()
        if hasEvents:
            return notificationMessage
        else:
            if days_to_add > 1:
                future = date.today() + timedelta(days=days_to_add-1)
                return "No Activities for {} - {}".format(date.today().isoformat(), future.isoformat())
            return "No Activities for Today {}".format(date.today().isoformat())
    
    def isgoodipv4(s):
        if ':' in s: s = s.split(':')[0]
        pieces = s.split('.')
        if len(pieces) != 4: return False
        try: return all(0<=int(p)<256 for p in pieces)
        except ValueError: return False

    async def async_handle_notify(call):
        # Allow the service call override the configuration.
        days_to_add = call.data.get(ATTR_NAME, num_of_days)
        
        # Set days to add to 1 if days_to_add is 0
        if days_to_add == 0:
            days_to_add = DEFAULT_NUM
        
        calendars = await async_get_calendars()
        _LOGGER.info('Calendars: %s', calendars) 
        # remove holidays calendar
        for calendar in calendars:
            _LOGGER.info("{}".format(excluded_calendars))
            if calendar['entity_id'] in excluded_calendars:
                calendars.remove(calendar)
        
        _LOGGER.info('Calendars: %s', calendars) 
        
        notificationMessage = await async_get_events(calendars, days_to_add)
        _LOGGER.info("Message to send: {}".format(notificationMessage))

        for service in notify_services_to_call:
            await hass.services.async_call('notify', service, {"message": notificationMessage})
            _LOGGER.info("notify.{} was called".format(service))
        _LOGGER.info("notify calls completed")

    hass.services.async_register(DOMAIN, 'notify', async_handle_notify)

    return True
