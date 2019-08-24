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


from homeassistant.const import (CONF_HOST, CONF_TOKEN)
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'daily_events'
ATTR_NAME = 'num_of_days'
DEFAULT_NUM = 1

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_TOKEN): cv.string,
        vol.Optional(ATTR_NAME, default=DEFAULT_NUM): int
    }),
}, extra=vol.ALLOW_EXTRA)

async def async_setup(hass, config):
    _LOGGER.info('setting up daily_activities')
    conf = config[DOMAIN]
    hassio_url = '{}/api/'.format(conf.get(CONF_HOST))
    auth_token = conf.get(CONF_TOKEN)
    headers = {'authorization': "Bearer {}".format(auth_token)}
    num_of_days = conf.get(ATTR_NAME, DEFAULT_NUM)
    hasEvents = False

    async def async_get_calendars():
        _LOGGER.info('Calling get calendars')
        async with aiohttp.ClientSession(raise_for_status=True) as session:
            try:
                with async_timeout.timeout(10, loop=hass.loop):
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
        todayStart = datetime.combine(date.today(), time())
        endDateTime = todayStart + timedelta(days=days_to_add)
        for calendar in calendars:
            async with aiohttp.ClientSession(raise_for_status=True) as session:
                _LOGGER.info('Attempting to get events for calendar: calendar=%s', calendar['entity_id'])
                # call hassio API deletion
                try:
                    with async_timeout.timeout(10, loop=hass.loop):
                        resp = await session.get(
                            "{}calendars/{}?start={}Z&end={}Z".format(
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
                                notificationMessage += "- {} at {}\n".format(
                                    item['summary'],
                                    parse(item['start']['dateTime']).strftime("%I:%M %p")
                                )
                            else:
                                notificationMessage += "- {}\n".format(item['summary'])
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
            return "No Activities Today {}".format(date.today().isoformat())
    
    def isgoodipv4(s):
        if ':' in s: s = s.split(':')[0]
        pieces = s.split('.')
        if len(pieces) != 4: return False
        try: return all(0<=int(p)<256 for p in pieces)
        except ValueError: return False

    async def async_handle_notify(call):
        # Allow the service call override the configuration.
        days_to_add = call.data.get(ATTR_NAME, num_of_days)
        calendars = await async_get_calendars()
        _LOGGER.info('Calendars: %s', calendars) 
        # remove holidays calendar
        for calendar in calendars:
            if calendar['entity_id'] == 'calendar.holidays_in_united_states':
                calendars.remove(calendar)
        
        _LOGGER.info('Calendars: %s', calendars) 
        
        notificationMessage = await async_get_events(calendars, days_to_add)
        _LOGGER.info("Message to send: {}".format(notificationMessage))

        await hass.services.async_call('notify', 'html5', {"message": notificationMessage})
        _LOGGER.info("Notify was called")

    hass.services.async_register(DOMAIN, 'notify', async_handle_notify)

    return True