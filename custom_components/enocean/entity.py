"""Representation of an EnOcean device."""

from enocean_async import (
    EEP,
    EURID,
    BaseAddress,
    Instruction,
    Observation,
    SenderAddress,
)
from enocean_async.address import Address
from enocean_async.eep.message import EEPMessage
from enocean_async.protocol.erp1.telegram import ERP1Telegram
from enocean_async.protocol.esp3.packet import ESP3Packet, ESP3PacketType

from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_send
from homeassistant.helpers.entity import Entity

from .const import (
    LOGGER,
    SIGNAL_ADD_DEVICE,
    SIGNAL_ADDED_TO_GATEWAY,
    SIGNAL_RECEIVE_EEP_MESSAGE,
    SIGNAL_RECEIVE_ERP1_TELEGRAM,
    SIGNAL_RECEIVE_OBSERVATION,
    SIGNAL_REMOVE_DEVICE,
    SIGNAL_SEND_COMMAND,
    SIGNAL_SEND_ESP3_PACKET,
)


def combine_hex(dev_id: list[int]) -> int:
    """Combine list of integer values to one big integer.

    This function replaces the previously used function from the enocean library and is considered tech debt that will have to be replaced.
    """
    value = 0
    for byte in dev_id:
        value = (value << 8) | (byte & 0xFF)
    return value


class EnOceanEntity(Entity):
    """Parent class for all entities associated with the EnOcean component."""

    def __init__(
        self, device_id: list[int], eep: EEP | None, sender_id: list[int] | None = None
    ) -> None:
        """Initialize the device."""
        self.address: Address | None = None
        self.sender_id: SenderAddress | None = None
        self.eep: EEP | None = eep

        try:
            self.address = Address.from_bytelist(device_id)
        except ValueError:
            LOGGER.warning("Invalid device_id provided, address will be None")
            self.address = None

        if sender_id is not None:
            try:
                sender_id_addr = Address.from_bytelist(sender_id)
                if sender_id_addr.is_eurid():
                    self.sender_id = EURID.from_number(sender_id_addr.to_number())
                elif sender_id_addr.is_base_address():
                    self.sender_id = BaseAddress.from_number(sender_id_addr.to_number())
            except ValueError:
                LOGGER.warning("Invalid sender_id provided, sender_id will be None")
                self.sender_id = None

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""

        # If the device has a valid address and EEP, register it with the gateway so it can receive messages.
        if self.eep is not None:
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass,
                    SIGNAL_ADDED_TO_GATEWAY,
                    self._added_to_gateway,
                )
            )

            dispatcher_send(
                self.hass, SIGNAL_ADD_DEVICE, self.address, self.eep, self.sender_id
            )

            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass,
                    SIGNAL_RECEIVE_OBSERVATION,
                    self._observation_received_callback,
                )
            )

            self.async_on_remove(
                lambda: dispatcher_send(self.hass, SIGNAL_REMOVE_DEVICE, self.address)
            )

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_RECEIVE_EEP_MESSAGE,
                self._eep_message_received_callback,
            )
        )

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_RECEIVE_ERP1_TELEGRAM,
                self._erp1_telegram_received_callback,
            )
        )

    def _observation_received_callback(self, observation: Observation) -> None:
        """Handle incoming observations."""
        if observation.device == self.address:
            self.observation_received(observation)

    def _eep_message_received_callback(self, message: EEPMessage) -> None:
        """Handle incoming EEP messages."""
        if message.sender == self.address:
            self.eep_message_received(message)

    def _erp1_telegram_received_callback(self, telegram: ERP1Telegram) -> None:
        """Handle incoming packets."""
        if not self.address:
            return

        if telegram.sender == self.address:
            self.erp1_telegram_received(telegram)

    def _added_to_gateway(self, address: Address) -> None:
        """Handle being added to the gateway."""
        if self.address == address:
            self.added_to_gateway()

    def added_to_gateway(self) -> None:
        """Handle being added to the gateway."""

    def eep_message_received(self, message: EEPMessage) -> None:
        """Update the internal state of the device when a message arrives."""

    def erp1_telegram_received(self, telegram: ERP1Telegram) -> None:
        """Update the internal state of the device when a packet arrives."""

    def observation_received(self, observation: Observation) -> None:
        """Update the internal state of the device when an observation arrives."""

    def send_esp3_packet(
        self, data: list[int], optional: list[int], packet_type: ESP3PacketType
    ) -> None:
        """Send a command via the EnOcean dongle, if data and optional are valid bytes; otherwise, ignore."""
        try:
            packet = ESP3Packet(packet_type, data=bytes(data), optional=bytes(optional))
            dispatcher_send(self.hass, SIGNAL_SEND_ESP3_PACKET, packet)
        except ValueError as err:
            LOGGER.warning(
                "Failed to send command: invalid data or optional bytes: %s", err
            )

    def send_command(self, action: Instruction) -> None:
        """Send an action via the EnOcean dongle."""
        if not self.address:
            LOGGER.warning("Cannot send command, address is None")
            return

        dispatcher_send(
            self.hass, SIGNAL_SEND_COMMAND, self.address, action, self.sender_id
        )
