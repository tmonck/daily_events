"""
Support for automating the deletion of snapshots.
"""
import logging
import asyncio
import aiohttp
import async_timeout
from urllib.parse import urlparse


from homeassistant.const import (CONF_HOST, CONF_TOKEN)
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'daily_events'
DEFAULT_NUM = 0

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_TOKEN): cv.string,
    }),
}, extra=vol.ALLOW_EXTRA)

async def async_setup(hass, config):
    _LOGGER.info('setting up daily_activities')
    conf = config[DOMAIN]
    hassio_url = '{}/api/hassio/'.format(conf.get(CONF_HOST))
    auth_token = conf.get(CONF_TOKEN)
    headers = {'authorization': "Bearer {}".format(auth_token)}
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
                _LOGGER.error("Client error on calling get snapshots", exc_info=True)
                await session.close()
            except asyncio.TimeoutError:
                _LOGGER.error("Client timeout error on get snapshots", exc_info=True)
                await session.close()
            except Exception: 
                _LOGGER.error("Unknown exception thrown", exc_info=True)
                await session.close()

    async def async_get_events(calendars):
        hasEvents = False
        notificationMessage = ''
        for calendar in calendars:
            async with aiohttp.ClientSession(raise_for_status=True) as session:
                _LOGGER.info('Attempting to get events for calendar: calendar=%s', calendar['entity_id'])
                # call hassio API deletion
                try:
                    with async_timeout.timeout(10, loop=hass.loop):
                        resp = await session.post(
                            hassio_url + 'calendars/' + calendar['entity_id'] + "?start=2019-08-23T00:00:00Z&end=2019-09-22T00:00:00Z",
                            headers=headers,
                            ssl=not isgoodipv4(urlparse(hassio_url).netloc)
                        )
                    res = await resp.json()
                    await session.close()
                    if res.len > 0:
                        hasEvents = True
                        _LOGGER.info("received {}".format(res.len))
                        notificationMessage += "{}\n".format(calendar['entity_id'])
                        for item in res:
                            notificationMessage += "- {} at {}\n".format(item['summary'], item['start']['dateTime'])
                    _LOGGER.debug("current notificationMessage {}".format(notificationMessage))
                except aiohttp.ClientError:
                    _LOGGER.error("Client error on calling delete snapshot", exc_info=True)
                    await session.close()
                except asyncio.TimeoutError:
                    _LOGGER.error("Client timeout error on delete snapshot", exc_info=True)
                    await session.close()
                except Exception: 
                    _LOGGER.error("Unknown exception thrown on calling delete snapshot", exc_info=True)
                    await session.close()
        if hasEvents:
            return notificationMessage
        else: 
            return 'No Activities Today'
    
    def isgoodipv4(s):
        if ':' in s: s = s.split(':')[0]
        pieces = s.split('.')
        if len(pieces) != 4: return False
        try: return all(0<=int(p)<256 for p in pieces)
        except ValueError: return False

    async def async_handle_notify(call):
        # Allow the service call override the configuration.
        calendars = await async_get_calendars()
        _LOGGER.info('Calendars: %s', calendars) 
        # remove holidays calendar
        calendars.remove()
        _LOGGER.info('Calendars: %s', calendars) 
        notificationMessage = await async_get_events(calendars)
        _LOGGER.info("Message to send: {}".format(notificationMessage))

    hass.services.async_register(DOMAIN, 'notify', async_handle_notify)

    return True