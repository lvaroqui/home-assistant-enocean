"""Config flows for the EnOcean integration."""

import glob
from typing import Any

from enocean_async import Gateway
import voluptuous as vol

from homeassistant.components import usb
from homeassistant.components.usb import (
    human_readable_device_name,
    usb_unique_id_from_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import (
    ATTR_MANUFACTURER,
    CONF_DEVICE,
    CONF_ID,
    CONF_NAME,
    Platform,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers.service_info.usb import UsbServiceInfo

from .const import (
    CONF_BASE_ID,
    CONF_CHANNEL_COUNT,
    CONF_SENDER_ID,
    DOMAIN,
    ERROR_INVALID_DONGLE_PATH,
    LOGGER,
    MANUFACTURER,
)

MANUAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEVICE): cv.string,
    }
)


def _detect_usb_dongle() -> list[str]:
    """Return a list of candidate paths for USB EnOcean dongles.

    This method is currently a bit simplistic, it may need to be
    improved to support more configurations and OS.
    """
    globs_to_test = [
        "/dev/tty*FTOA2PV*",
        "/dev/serial/by-id/*EnOcean*",
        "/dev/tty.usbserial-*",
        "/dev/serial/by-id/*",
    ]
    found_paths = []
    for current_glob in globs_to_test:
        found_paths.extend(glob.glob(current_glob))

    return found_paths


class EnOceanFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle the enOcean config flows."""

    VERSION = 1
    MANUAL_PATH_VALUE = "manual"

    def __init__(self) -> None:
        """Initialize the EnOcean config flow."""
        self.data: dict[str, Any] = {}

    async def async_step_usb(self, discovery_info: UsbServiceInfo) -> ConfigFlowResult:
        """Handle usb discovery."""
        unique_id = usb_unique_id_from_service_info(discovery_info)

        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured(
            updates={CONF_DEVICE: discovery_info.device}
        )

        discovery_info.device = await self.hass.async_add_executor_job(
            usb.get_serial_by_id, discovery_info.device
        )

        self.data[CONF_DEVICE] = discovery_info.device
        self.context["title_placeholders"] = {
            CONF_NAME: human_readable_device_name(
                discovery_info.device,
                discovery_info.serial_number,
                discovery_info.manufacturer,
                discovery_info.description,
                discovery_info.vid,
                discovery_info.pid,
            )
        }
        return await self.async_step_usb_confirm()

    async def async_step_usb_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle USB Discovery confirmation."""
        if user_input is not None:
            return await self.async_step_manual({CONF_DEVICE: self.data[CONF_DEVICE]})
        self._set_confirm_only()
        return self.async_show_form(
            step_id="usb_confirm",
            description_placeholders={
                ATTR_MANUFACTURER: MANUFACTURER,
                CONF_DEVICE: self.data.get(CONF_DEVICE, ""),
            },
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Import a yaml configuration."""

        if not await self._validate_enocean_conf(import_data):
            LOGGER.warning(
                "Cannot import yaml configuration: %s is not a valid dongle path",
                import_data[CONF_DEVICE],
            )
            return self.async_abort(reason="invalid_dongle_path")

        return self._create_enocean_entry(import_data)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle an EnOcean config flow start."""
        return await self.async_step_detect()

    async def async_step_detect(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Propose a list of detected dongles."""
        if user_input is not None:
            if user_input[CONF_DEVICE] == self.MANUAL_PATH_VALUE:
                return await self.async_step_manual()
            return await self.async_step_manual(user_input)

        devices = await self.hass.async_add_executor_job(_detect_usb_dongle)
        if len(devices) == 0:
            return await self.async_step_manual()
        devices.append(self.MANUAL_PATH_VALUE)

        return self.async_show_form(
            step_id="detect",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE): SelectSelector(
                        SelectSelectorConfig(
                            options=devices,
                            translation_key="devices",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Request manual USB dongle path."""
        errors = {}
        if user_input is not None:
            if await self._validate_enocean_conf(user_input):
                return self._create_enocean_entry(user_input)
            errors = {CONF_DEVICE: ERROR_INVALID_DONGLE_PATH}

        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(MANUAL_SCHEMA, user_input),
            errors=errors,
        )

    async def _validate_enocean_conf(self, user_input) -> bool:
        """Return True if the user_input contains a valid dongle path."""
        dongle_path = user_input[CONF_DEVICE]
        try:
            # Starting the gateway will raise an exception if it can't connect
            gateway = Gateway(port=dongle_path)
            await gateway.start()
            user_input[CONF_BASE_ID] = _parse_device_address(
                (await gateway.base_id).to_string()
            )
        except ConnectionError as exception:
            LOGGER.warning("Dongle path %s is invalid: %s", dongle_path, str(exception))
            return False
        finally:
            gateway.stop()

        return True

    def _create_enocean_entry(self, user_input):
        """Create an entry for the provided configuration."""
        return self.async_create_entry(title=MANUFACTURER, data=user_input)

    @classmethod
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {"cover": CoverSubentryFlowHandler, "switch": SwitchSubentryFlowHandler}


def _parse_device_address(device_address: str) -> list[int]:
    """Parse a device address from a string to a list of integers."""
    try:
        # Remove any common separators and whitespace, then parse as 4 hex bytes
        device_address = device_address.replace(" ", "")
        device_address = device_address.replace("-", "")
        device_address = device_address.replace(":", "")

        if len(device_address) == 8 and all(
            c in "0123456789abcdefABCDEF" for c in device_address
        ):
            return [
                int(device_address[i : i + 2], 16)
                for i in range(0, len(device_address), 2)
            ]

    except ValueError as err:
        raise ValueError(f"Invalid device address format: {device_address}") from err

    raise ValueError(f"Invalid device address format: {device_address}")


class CoverSubentryFlowHandler(ConfigSubentryFlow):
    """Handle subentry flow for adding and modifying a cover."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """User flow to add a new cover."""

        errors = {}
        if user_input is not None:
            for field in (CONF_ID,):
                try:
                    user_input[field] = _parse_device_address(user_input[field])
                except ValueError:
                    errors[field] = "invalid_device_address"

            user_input["type"] = Platform.COVER
            user_input[CONF_SENDER_ID] = self._get_entry().data[CONF_BASE_ID]

            if len(errors) == 0:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data=user_input,
                    unique_id=str(user_input[CONF_ID]),
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ID): str,
                    vol.Required(CONF_NAME): str,
                }
            ),
            errors=errors,
        )


class SwitchSubentryFlowHandler(ConfigSubentryFlow):
    """Handle subentry flow for adding and modifying a location."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """User flow to add a new switch."""

        errors = {}
        if user_input is not None:
            for field in (CONF_ID,):
                try:
                    user_input[field] = _parse_device_address(user_input[field])
                except ValueError:
                    errors[field] = "invalid_device_address"

            if user_input[CONF_CHANNEL_COUNT] < 1:
                errors[CONF_CHANNEL_COUNT] = "invalid_channel_counte"

            user_input["type"] = Platform.SWITCH
            user_input[CONF_SENDER_ID] = self._get_entry().data[CONF_BASE_ID]

            if len(errors) == 0:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data=user_input,
                    unique_id=str(user_input[CONF_ID]),
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Required(CONF_ID): str,
                    vol.Optional(CONF_CHANNEL_COUNT, default=1): cv.positive_int,
                }
            ),
            errors=errors,
        )
