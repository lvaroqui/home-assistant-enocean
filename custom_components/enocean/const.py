"""Constants for the EnOcean integration."""

import logging

from homeassistant.const import Platform

DOMAIN = "enocean"

MANUFACTURER = "EnOcean"

ERROR_INVALID_DONGLE_PATH = "invalid_dongle_path"

SIGNAL_ADD_DEVICE = "enocean.add_device"
SIGNAL_ADDED_TO_GATEWAY = "enocean.added_to_gateway"
SIGNAL_RECEIVE_ERP1_TELEGRAM = "enocean.receive_erp1_telegram"
SIGNAL_RECEIVE_EEP_MESSAGE = "enocean.receive_eep_message"
SIGNAL_RECEIVE_OBSERVATION = "enocean.receive_observation"
SIGNAL_REMOVE_DEVICE = "enocean.remove_device"
SIGNAL_SEND_ESP3_PACKET = "enocean.send_esp3_packet"
SIGNAL_SEND_COMMAND = "enocean.send_command"

CONF_CHANNEL_COUNT = "channel_count"
CONF_SENDER_ID = "sender_id"
CONF_BASE_ID = "base_id"

LOGGER = logging.getLogger(__package__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.SWITCH,
]
