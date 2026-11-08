"""Sensor platform for the Maxi-Cosi Baby Monitor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, DOMAIN, DP_HUMIDITY, DP_TEMPERATURE
from .coordinator import MaxiCosiConfigEntry, MaxiCosiCoordinator


@dataclass(frozen=True, kw_only=True)
class MaxiCosiSensorDescription(SensorEntityDescription):
    """Describes a Maxi-Cosi sensor backed by a Tuya datapoint."""

    dp: str
    convert: Callable[[object], float | None] = float


SENSORS: tuple[MaxiCosiSensorDescription, ...] = (
    MaxiCosiSensorDescription(
        key="temperature",
        dp=DP_TEMPERATURE,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    MaxiCosiSensorDescription(
        key="humidity",
        dp=DP_HUMIDITY,
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MaxiCosiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Maxi-Cosi sensors from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        MaxiCosiSensor(coordinator, entry, description) for description in SENSORS
    )


class MaxiCosiSensor(CoordinatorEntity[MaxiCosiCoordinator], SensorEntity):
    """A single datapoint of the Maxi-Cosi monitor."""

    entity_description: MaxiCosiSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MaxiCosiCoordinator,
        entry: MaxiCosiConfigEntry,
        description: MaxiCosiSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        device_id = entry.data[CONF_DEVICE_ID]
        self._attr_unique_id = f"{device_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=entry.title,
            manufacturer="Maxi-Cosi",
            model="See Pro Baby Monitor",
        )

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.data is not None
            and self.entity_description.dp in self.coordinator.data
        )

    @property
    def native_value(self) -> float | None:
        raw = (self.coordinator.data or {}).get(self.entity_description.dp)
        if raw is None:
            return None
        try:
            return self.entity_description.convert(raw)
        except (TypeError, ValueError):
            return None
