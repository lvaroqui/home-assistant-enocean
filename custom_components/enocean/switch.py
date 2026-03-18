"""Support for EnOcean switches."""

from __future__ import annotations

from typing import Any

from enocean_async import (
    EEP,
    Observable,
    Observation,
    QueryActuatorStatus,
    SetSwitchOutput,
)
from enocean_async.eep.message import EEPMessage

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ID, CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_CHANNEL_COUNT, CONF_SENDER_ID, DOMAIN, MANUFACTURER
from .entity import EnOceanEntity, combine_hex

DEFAULT_NAME = "EnOcean Switch"


def generate_unique_id(dev_id: list[int], channel: int) -> str:
    """Generate a valid unique id."""
    return f"{combine_hex(dev_id)}-{channel}"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the EnOcean switch entities."""

    for subentry in config_entry.subentries.values():
        if subentry.data["type"] == Platform.SWITCH:
            device_id: list[int] = subentry.data[CONF_ID]
            sender_id: list[int] = subentry.data[CONF_SENDER_ID]
            channel_count = subentry.data[CONF_CHANNEL_COUNT]

            entities = []
            for channel in range(channel_count):
                if channel_count == 1:
                    entity_name: str = subentry.data[CONF_NAME]
                else:
                    entity_name = f"{subentry.data[CONF_NAME]} Switch {channel}"

                entities.append(
                    EnOceanSwitch(
                        device_id,
                        entity_name,
                        channel,
                        sender_id,
                        subentry.data[CONF_NAME],
                    )
                )

            if channel_count > 1:
                entities.append(
                    EnOceanSwitch(
                        device_id,
                        f"{subentry.data[CONF_NAME]} All Switches",
                        channel=0x1E,  # special channel for all switches
                        sender_id=sender_id,
                        device_name=subentry.data[CONF_NAME],
                        channel_count=channel_count,
                    )
                )

            async_add_entities(entities, config_subentry_id=subentry.subentry_id)


class EnOceanSwitch(EnOceanEntity, SwitchEntity):
    """Representation of an EnOcean switch device."""

    _attr_is_on = False

    def __init__(
        self,
        dev_id: list[int],
        entity_name: str,
        channel: int,
        sender_id: list[int],
        device_name: str,
        channel_count: int = 1,
    ) -> None:
        """Initialize the EnOcean switch device."""
        super().__init__(dev_id, EEP(0xD2, 0x01, 0x01), sender_id)
        self.channel: int = channel
        self.channel_count: int = channel_count

        if self.channel == 0x1E:
            self.channel_states = [False] * channel_count

        self._attr_unique_id = generate_unique_id(dev_id, channel)
        self._attr_name = entity_name

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(combine_hex(dev_id)))},
            name=device_name,
            manufacturer=MANUFACTURER,
        )

    def added_to_gateway(self):
        """Handle being added to the gateway."""
        if self.channel != 0x1E:  # Don't query status for the "all switches" channel
            self.send_command(QueryActuatorStatus(entity_id=str(self.channel)))

    def _set_state(self, on: bool):
        """Send a telegram to turn the switch on or off."""
        self.send_command(
            SetSwitchOutput(output_value=100 if on else 0, entity_id=str(self.channel))
        )
        self._attr_is_on = on

    def turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        self._set_state(on=True)

    def turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        self._set_state(on=False)

    def observation_received(self, observation: Observation):
        """Update the internal state of the switch based on an observation."""
        if Observable.SWITCH_STATE in observation.values:
            if observation.entity == str(self.channel):
                self._attr_is_on = observation.values[Observable.SWITCH_STATE]
                self.schedule_update_ha_state()

    def eep_message_received(self, message: EEPMessage):
        """Update the internal state of the switch based on an EEP message."""
        # Only process messages for the special "all switches" channel
        if (
            self.channel == 0x1E
            and "I/O" in message.raw
            and Observable.SWITCH_STATE in message.values
        ):
            channel = int(message.raw["I/O"])
            self.channel_states[channel] = message.values[Observable.SWITCH_STATE].value
            self._attr_is_on = any(self.channel_states)
            self.schedule_update_ha_state()
