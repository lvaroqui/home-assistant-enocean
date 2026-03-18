"""Support for EnOcean devices."""

from enocean_async import Gateway
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
    dispatcher_send,
)

from .const import (
    DOMAIN,
    SIGNAL_ADD_DEVICE,
    SIGNAL_ADDED_TO_GATEWAY,
    SIGNAL_RECEIVE_EEP_MESSAGE,
    SIGNAL_RECEIVE_ERP1_TELEGRAM,
    SIGNAL_RECEIVE_OBSERVATION,
    SIGNAL_REMOVE_DEVICE,
    SIGNAL_SEND_COMMAND,
    SIGNAL_SEND_ESP3_PACKET,
)

PLATFORMS = [Platform.COVER, Platform.SWITCH]


type EnOceanConfigEntry = ConfigEntry[Gateway]

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema({vol.Required(CONF_DEVICE): cv.string})}, extra=vol.ALLOW_EXTRA
)


async def async_setup_entry(
    hass: HomeAssistant, config_entry: EnOceanConfigEntry
) -> bool:
    """Set up an EnOcean gateway for the given entry."""

    gateway = Gateway(port=config_entry.data[CONF_DEVICE])

    gateway.add_erp1_received_callback(
        lambda packet: async_dispatcher_send(hass, SIGNAL_RECEIVE_ERP1_TELEGRAM, packet)
    )

    gateway.add_eep_message_received_callback(
        lambda message: async_dispatcher_send(hass, SIGNAL_RECEIVE_EEP_MESSAGE, message)
    )

    gateway.add_observation_callback(
        lambda message: async_dispatcher_send(hass, SIGNAL_RECEIVE_OBSERVATION, message)
    )

    try:
        await gateway.start()
    except ConnectionError as err:
        gateway.stop()
        raise ConfigEntryNotReady(f"Failed to start EnOcean gateway: {err}") from err

    config_entry.runtime_data = gateway

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_SEND_ESP3_PACKET, gateway.send_esp3_packet
        )
    )
    config_entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_SEND_COMMAND, gateway.send_command)
    )
    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_ADD_DEVICE,
            lambda address, eep, sender_id: (
                gateway.add_device(address, eep, sender_id),
                dispatcher_send(hass, SIGNAL_ADDED_TO_GATEWAY, address),
            ),
        )
    )
    config_entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_REMOVE_DEVICE, gateway.remove_device)
    )

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    config_entry.async_on_unload(
        config_entry.add_update_listener(_async_update_listener)
    )

    return True


async def _async_update_listener(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Reload config entry on update (e.g. subentry added/removed)."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, config_entry: EnOceanConfigEntry
) -> bool:
    """Unload EnOcean config entry: stop the gateway."""

    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )
    config_entry.runtime_data.stop()
    return unload_ok
