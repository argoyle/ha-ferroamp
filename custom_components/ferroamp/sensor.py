"""Platform for Ferroamp sensors integration."""
import json
import logging
from datetime import datetime

from homeassistant import config_entries, core
from homeassistant.components import mqtt
from homeassistant.const import (
    CONF_NAME,
    CONF_PREFIX,
    ELECTRICAL_CURRENT_AMPERE,
    ENERGY_WATT_HOUR,
    ENERGY_KILO_WATT_HOUR,
    POWER_KILO_WATT,
    TEMP_CELSIUS,
    POWER_WATT,
    VOLT,
    PERCENTAGE,
)
from homeassistant.core import callback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import slugify

from .const import CONF_INTERVAL, DATA_DEVICES, DATA_LISTENERS, DOMAIN, MANUFACTURER

_LOGGER = logging.getLogger(__name__)

EHUB_TOPIC = "data/ehub"
SSO_TOPIC = "data/sso"
ESO_TOPIC = "data/eso"
ESM_TOPIC = "data/esm"

EHUB = "ehub"
EHUB_NAME = "EnergyHub"


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
):
    """Setup sensors from a config entry created in the integrations UI."""
    hass.data[DOMAIN].setdefault(DATA_DEVICES, {})
    hass.data[DOMAIN].setdefault(DATA_LISTENERS, {})
    hass.data[DOMAIN][DATA_DEVICES].setdefault(config_entry.unique_id, {})
    hass.data[DOMAIN][DATA_LISTENERS].setdefault(config_entry.unique_id, [])
    listeners = hass.data[DOMAIN][DATA_LISTENERS].get(config_entry.unique_id)
    if listeners is None:
        listeners = hass.data[DOMAIN][DATA_LISTENERS][config_entry.unique_id] = []

    config = hass.data[DOMAIN][DATA_DEVICES][config_entry.unique_id]
    _LOGGER.debug(
        "Setting up ferroamp sensors for %(prefix)s",
        dict(prefix=config_entry.data[CONF_PREFIX]),
    )
    config_id = config_entry.unique_id
    name = config_entry.data[CONF_NAME]
    slug = slugify(name)

    interval = config_entry.options.get(CONF_INTERVAL)
    if interval is None or interval == 0:
        interval = 30

    listeners.append(config_entry.add_update_listener(options_update_listener))

    ehub = ehub_sensors(slug, name, interval, config_id)
    eso_sensors = {}
    esm_sensors = {}
    sso_sensors = {}

    def update_sensor_from_event(event, sensors, store):
        for sensor in sensors:
            if sensor.unique_id not in store:
                store[sensor.unique_id] = sensor
                _LOGGER.debug(
                    "Registering new sensor %(unique_id)s => %(event)s",
                    dict(unique_id=sensor.unique_id, event=event),
                )
                async_add_entities((sensor,), True)
            sensor.hass = hass
            sensor.add_event(event)

    @callback
    def ehub_event_received(msg):
        event = json.loads(msg.payload)
        store = config.get(f"{slug}_{EHUB}")
        if store is None:
            store = config[f"{slug}_{EHUB}"] = {}
        update_sensor_from_event(event, ehub, store)

    @callback
    def sso_event_received(msg):
        event = json.loads(msg.payload)
        sso_id = event["id"]["val"]
        device_id = f"{slug}_sso_{sso_id}"
        device_name = f"{name} SSO {sso_id}"
        store = config.get(device_id)
        sensors = sso_sensors.get(sso_id)
        if store is None:
            store = config[device_id] = {}
            sensors = sso_sensors[sso_id] = [
                IntValFerroampSensor(
                    f"{device_name} PV String Voltage",
                    "upv",
                    VOLT,
                    "mdi:current-dc",
                    device_id,
                    device_name,
                    interval,
                    config_id,
                ),
                FloatValFerroampSensor(
                    f"{device_name} PV String Current",
                    "ipv",
                    ELECTRICAL_CURRENT_AMPERE,
                    "mdi:current-dc",
                    device_id,
                    device_name,
                    interval,
                    config_id,
                ),
                PowerFerroampSensor(
                    f"{device_name} PV String Power",
                    "upv",
                    "ipv",
                    "mdi:solar-power",
                    device_id,
                    device_name,
                    interval,
                    config_id,
                ),
                EnergyFerroampSensor(
                    f"{device_name} Total Energy",
                    "wpv",
                    "mdi:solar-power",
                    device_id,
                    device_name,
                    interval,
                    config_id,
                ),
                StringValFerroampSensor(
                    f"{device_name} Faultcode",
                    "faultcode",
                    "",
                    "mdi:traffic-light",
                    device_id,
                    device_name,
                    interval,
                    config_id,
                ),
                RelayStatusFerroampSensor(
                    f"{device_name} Relay Status",
                    "relaystatus",
                    device_id,
                    device_name,
                    interval,
                    config_id,
                ),
                FloatValFerroampSensor(
                    f"{device_name} PCB Temperature",
                    "temp",
                    TEMP_CELSIUS,
                    "mdi:thermometer",
                    device_id,
                    device_name,
                    interval,
                    config_id,
                ),
            ]

        update_sensor_from_event(event, sensors, store)

    @callback
    def eso_event_received(msg):
        event = json.loads(msg.payload)
        eso_id = event["id"]["val"]
        if eso_id == "":
            return
        device_id = f"{slug}_eso_{eso_id}"
        device_name = f"{name} ESO {eso_id}"
        store = config.get(device_id)
        sensors = eso_sensors.get(eso_id)
        if store is None:
            store = config[device_id] = {}
            sensors = eso_sensors[eso_id] = [
                IntValFerroampSensor(
                    f"{device_name} Battery Voltage",
                    "ubat",
                    VOLT,
                    "mdi:battery",
                    device_id,
                    device_name,
                    interval,
                    config_id,
                ),
                FloatValFerroampSensor(
                    f"{device_name} Battery Current",
                    "ibat",
                    ELECTRICAL_CURRENT_AMPERE,
                    "mdi:battery",
                    device_id,
                    device_name,
                    interval,
                    config_id,
                ),
                PowerFerroampSensor(
                    f"{device_name} Battery Power",
                    "ubat",
                    "ibat",
                    "mdi:battery",
                    device_id,
                    device_name,
                    interval,
                    config_id,
                ),
                EnergyFerroampSensor(
                    f"{device_name} Total Energy Produced",
                    "wbatprod",
                    "mdi:battery",
                    device_id,
                    device_name,
                    interval,
                    config_id,
                ),
                EnergyFerroampSensor(
                    f"{device_name} Total Energy Consumed",
                    "wbatcons",
                    "mdi:battery",
                    device_id,
                    device_name,
                    interval,
                    config_id,
                ),
                BatteryFerroampSensor(
                    f"{device_name} State of Charge",
                    "soc",
                    device_id,
                    device_name,
                    interval,
                    config_id,
                ),
                StringValFerroampSensor(
                    f"{device_name} Faultcode",
                    "faultcode",
                    "",
                    "mdi:traffic-light",
                    device_id,
                    device_name,
                    interval,
                    config_id,
                ),
                RelayStatusFerroampSensor(
                    f"{device_name} Relay Status",
                    "relaystatus",
                    device_id,
                    device_name,
                    interval,
                    config_id,
                ),
                FloatValFerroampSensor(
                    f"{device_name} PCB Temperature",
                    "temp",
                    TEMP_CELSIUS,
                    "mdi:thermometer",
                    device_id,
                    device_name,
                    interval,
                    config_id,
                ),
            ]

        update_sensor_from_event(event, sensors, store)

    @callback
    def esm_event_received(msg):
        event = json.loads(msg.payload)
        esm_id = event["id"]["val"]
        device_id = f"{slug}_esm_{esm_id}"
        device_name = f"{name} ESM {esm_id}"
        store = config.get(device_id)
        sensors = esm_sensors.get(esm_id)
        if store is None:
            store = config[device_id] = {}
            sensors = esm_sensors[esm_id] = [
                BatteryFerroampSensor(
                    f"{device_name} State of Health",
                    "soh",
                    device_id,
                    device_name,
                    interval,
                    config_id,
                ),
                BatteryFerroampSensor(
                    f"{device_name} State of Charge",
                    "soc",
                    device_id,
                    device_name,
                    interval,
                    config_id,
                ),
                IntValFerroampSensor(
                    f"{device_name} Rated Capacity",
                    "ratedCapacity",
                    ENERGY_WATT_HOUR,
                    "mdi:battery",
                    device_id,
                    device_name,
                    interval,
                    config_id,
                ),
            ]

        update_sensor_from_event(event, sensors, store)

    listeners.append(await mqtt.async_subscribe(
        hass, f"{config_entry.data[CONF_PREFIX]}/{EHUB_TOPIC}", ehub_event_received, 0
    ))
    listeners.append(await mqtt.async_subscribe(
        hass, f"{config_entry.data[CONF_PREFIX]}/{SSO_TOPIC}", sso_event_received, 0
    ))
    listeners.append(await mqtt.async_subscribe(
        hass, f"{config_entry.data[CONF_PREFIX]}/{ESO_TOPIC}", eso_event_received, 0
    ))
    listeners.append(await mqtt.async_subscribe(
        hass, f"{config_entry.data[CONF_PREFIX]}/{ESM_TOPIC}", esm_event_received, 0
    ))

    return True


async def options_update_listener(hass, entry):
    """Handle options update."""
    config = hass.data[DOMAIN][DATA_DEVICES][entry.unique_id]
    for device in config.values():
        for sensor in device.values():
            sensor.set_interval(entry.options.get(CONF_INTERVAL))


class FerroampSensor(RestoreEntity):
    """Representation of a Ferroamp Sensor."""

    def __init__(self, name, key, unit, icon, device_id, device_name, interval, config_id):
        """Initialize the sensor."""
        self._state = None
        self._name = name
        self._state_key = key
        self._unit_of_measurement = unit
        self._icon = icon
        self._device_id = device_id
        self._device_name = device_name
        self.interval = interval
        self.config_id = config_id
        self.updated = datetime.min
        self.event = {}
        self.events = []
        self.attrs = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return unique ID of entity."""
        return f"{self.device_id}-{self._state_key}"

    @property
    def icon(self):
        return self._icon

    @property
    def device_id(self):
        return self._device_id

    @property
    def device_info(self):
        """Return the device_info of the device."""
        device_info = {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._device_name,
            "manufacturer": MANUFACTURER,
        }
        return device_info

    def add_event(self, event):
        self.events.append(event)
        self.event.update(event)
        now = datetime.now()
        delta = (now - self.updated).total_seconds()
        if delta > self.interval:
            temp = self.events
            self.events = []
            self.updated = now
            if self.entity_id is not None:
                self.update_state_from_events(temp)
                self.async_write_ha_state()

    def update_state_from_events(self, events):
        event = self.event
        for e in events:
            event.update(e)
        self._state = event.get(self._state_key, None)

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def should_poll(self) -> bool:
        return False

    @property
    def state_attributes(self):
        return self.attrs

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if not state:
            return
        self._state = state.state
        self.hass.data[DOMAIN][DATA_DEVICES][self.config_id][self.device_id][self.unique_id] = self

    def set_interval(self, interval):
        self.interval = interval


class IntValFerroampSensor(FerroampSensor):
    """Representation of a Ferroamp integer value Sensor."""

    def __init__(self, name, key, unit, icon, device_id, device_name, interval, config_id):
        """Initialize the sensor."""
        super().__init__(name, key, unit, icon, device_id, device_name, interval, config_id)

    def update_state_from_events(self, events):
        temp = 0
        event = self.event
        for e in events:
            event.update(e)
            v = event.get(self._state_key, None)
            if v is not None:
                temp += float(v["val"])
        self._state = int(temp / len(events))


class StringValFerroampSensor(FerroampSensor):
    """Representation of a Ferroamp string value Sensor."""

    def __init__(self, name, key, unit, icon, device_id, device_name, interval, config_id):
        """Initialize the sensor."""
        super().__init__(name, key, unit, icon, device_id, device_name, interval, config_id)

    def update_state_from_events(self, events):
        temp = None
        event = self.event
        for e in events:
            event.update(e)
            v = event.get(self._state_key, None)
            if v is not None:
                temp = v["val"]
        if temp is not None:
            self._state = temp


class FloatValFerroampSensor(FerroampSensor):
    """Representation of a Ferroamp float value Sensor."""

    def __init__(self, name, key, unit, icon, device_id, device_name, interval, config_id):
        """Initialize the sensor."""
        super().__init__(name, key, unit, icon, device_id, device_name, interval, config_id)

    def update_state_from_events(self, events):
        temp = 0
        event = self.event
        for e in events:
            event.update(e)
            v = event.get(self._state_key, None)
            if v is not None:
                temp += float(v["val"])
        self._state = round(temp / len(events), 2)


class DcLinkFerroampSensor(FerroampSensor):
    """Representation of a Ferroamp DC Voltage value Sensor."""

    def __init__(self, name, key, icon, device_id, device_name, interval, config_id):
        """Initialize the sensor."""
        super().__init__(name, key, VOLT, icon, device_id, device_name, interval, config_id)

    def get_voltage(self, event):
        voltage = event.get(self._state_key, None)
        if voltage is not None:
            voltage = dict(neg=float(voltage["neg"]), pos=float(voltage["pos"]))
        return voltage

    def update_state_from_events(self, events):
        neg = pos = 0
        event = self.event
        for e in events:
            event.update(e)
            voltage = self.get_voltage(event)
            if voltage is not None:
                neg += voltage["neg"]
                pos += voltage["pos"]
        self._state = int(neg / len(events) + pos / len(events))
        self.attrs = dict(neg=round(float(neg / len(events)), 2), pos=round(float(pos / len(events)), 2))


class BatteryFerroampSensor(IntValFerroampSensor):
    def __init__(self, name, key, device_id, device_name, interval, config_id):
        super().__init__(
            name, key, PERCENTAGE, "mdi:battery-low", device_id, device_name, interval, config_id
        )

    @property
    def icon(self):
        if self.state is None:
            return self._icon
        pct = self.state
        if isinstance(pct, str):
            pct = int(pct)
        pct = int(pct / 10) * 10
        if pct <= 90:
            self._icon = f"mdi:battery-{pct}"
        else:
            self._icon = "mdi:battery"

        return self._icon


class EnergyFerroampSensor(IntValFerroampSensor):
    """Representation of a Ferroamp energy in kWh value Sensor."""

    def __init__(self, name, key, icon, device_id, device_name, interval, config_id):
        """Initialize the sensor"""
        super().__init__(name, key, ENERGY_KILO_WATT_HOUR, icon, device_id, device_name, interval, config_id)

    def update_state_from_events(self, events):
        temp = 0
        event = self.event
        for e in events:
            event.update(e)
            v = event.get(self._state_key, None)
            if v is not None:
                temp += float(v["val"])
        self._state = int(temp / len(events) / 3600000000)


class RelayStatusFerroampSensor(FerroampSensor):
    def __init__(self, name, key, device_id, device_name, interval, config_id):
        """Initialize the sensor"""
        super().__init__(name, key, "", "", device_id, device_name, interval, config_id)

    def update_state_from_events(self, events):
        temp = None
        event = self.event
        for e in events:
            event.update(e)
            v = event.get(self._state_key, None)
            if v is not None:
                val = int(v["val"])
                if val == 0:
                    temp = "closed"
                elif val == 1:
                    temp = "open/disconnected"
                elif val == 2:
                    temp = "precharge"
        if temp is not None:
            self._state = temp


class PowerFerroampSensor(FerroampSensor):
    """Representation of a Ferroamp Power Sensor based on V and A."""

    def __init__(self, name, voltage_key, current_key, icon, device_id, device_name, interval, config_id):
        """Initialize the sensor."""
        super().__init__(
            name, voltage_key, POWER_KILO_WATT, icon, device_id, device_name, interval, config_id
        )
        self._voltage_key = voltage_key
        self._current_key = current_key

    @property
    def unique_id(self):
        """Return unique ID of entity."""
        return f"{self.device_id}-{self._voltage_key}-{self._current_key}"

    def update_state_from_events(self, events):
        temp_voltage = temp_current = 0
        event = self.event
        for e in events:
            event.update(e)
            voltage = event.get(self._voltage_key, None)
            current = event.get(self._current_key, None)
            if current is not None and voltage is not None:
                temp_voltage += float(voltage["val"])
                temp_current += float(current["val"])

        self._state = round(temp_voltage / len(events) * temp_current / len(events) / 1000, 2)


class ThreePhaseFerroampSensor(FerroampSensor):
    """Representation of a Ferroamp ThreePhase Sensor."""

    def __init__(self, name, key, unit, icon, device_id, device_name, interval, config_id):
        """Initialize the sensor."""
        super().__init__(name, key, unit, icon, device_id, device_name, interval, config_id)

    def get_phases(self, event):
        phases = event.get(self._state_key, None)
        _LOGGER.debug(phases)
        if phases is not None:
            phases = dict(
                L1=float(phases["L1"]), L2=float(phases["L2"]), L3=float(phases["L3"])
            )
        return phases

    def update_state_from_events(self, events):
        l1 = l2 = l3 = 0
        event = self.event
        for e in events:
            event.update(e)
            phases = self.get_phases(event)
            if phases is not None:
                l1 += phases["L1"]
                l2 += phases["L2"]
                l3 += phases["L3"]
        self._state = int(l1 / len(events) + l2 / len(events) + l3 / len(events))
        self.attrs = dict(
            L1=round(float(l1 / len(events)), 2),
            L2=round(float(l2 / len(events)), 2),
            L3=round(float(l3 / len(events)), 2),
        )


class ThreePhaseEnergyFerroampSensor(ThreePhaseFerroampSensor):
    def __init__(self, name, key, icon, device_id, device_name, interval, config_id):
        """Initialize the sensor."""
        super().__init__(name, key, ENERGY_KILO_WATT_HOUR, icon, device_id, device_name, interval, config_id)

    def get_phases(self, event):
        phases = super().get_phases(event)
        if phases is not None:
            phases = dict(
                L1=int(phases["L1"] / 3600000000),
                L2=int(phases["L2"] / 3600000000),
                L3=int(phases["L3"] / 3600000000),
            )

        return phases


def ehub_sensors(slug, name, interval, config_id):
    return [
        ThreePhaseFerroampSensor(
            f"{name} External Voltage",
            "ul",
            VOLT,
            "mdi:current-ac",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        ThreePhaseFerroampSensor(
            f"{name} Inverter RMS current",
            "il",
            ELECTRICAL_CURRENT_AMPERE,
            "mdi:current-dc",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        ThreePhaseFerroampSensor(
            f"{name} Inverter reactive current",
            "ild",
            ELECTRICAL_CURRENT_AMPERE,
            "mdi:current-dc",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        ThreePhaseFerroampSensor(
            f"{name} Grid Current",
            "iext",
            ELECTRICAL_CURRENT_AMPERE,
            "mdi:current-ac",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        ThreePhaseFerroampSensor(
            f"{name} Grid Reactive Current",
            "iextd",
            ELECTRICAL_CURRENT_AMPERE,
            "mdi:current-ac",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        ThreePhaseFerroampSensor(
            f"{name} External Active Current",
            "iextq",
            ELECTRICAL_CURRENT_AMPERE,
            "mdi:current-ac",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        ThreePhaseFerroampSensor(
            f"{name} Grid Power",
            "pext",
            POWER_WATT,
            "mdi:transmission-tower",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        ThreePhaseFerroampSensor(
            f"{name} Grid Power Reactive",
            "pextreactive",
            POWER_WATT,
            "mdi:transmission-tower",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        ThreePhaseFerroampSensor(
            f"{name} Inverter Power, active",
            "pinv",
            POWER_WATT,
            "mdi:solar-power",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        ThreePhaseFerroampSensor(
            f"{name} Inverter Power, reactive",
            "pinvreactive",
            POWER_WATT,
            "mdi:solar-power",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        ThreePhaseFerroampSensor(
            f"{name} Consumption Power",
            "pload",
            POWER_WATT,
            "mdi:power-plug",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        ThreePhaseFerroampSensor(
            f"{name} Consumption Power Reactive",
            "ploadreactive",
            POWER_WATT,
            "mdi:power-plug",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        ThreePhaseEnergyFerroampSensor(
            f"{name} External Energy Produced",
            "wextprodq",
            "mdi:power-plug",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        ThreePhaseEnergyFerroampSensor(
            f"{name} External Energy Consumed",
            "wextconsq",
            "mdi:power-plug",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        ThreePhaseEnergyFerroampSensor(
            f"{name} Inverter Energy Produced",
            "winvprodq",
            "mdi:power-plug",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        ThreePhaseEnergyFerroampSensor(
            f"{name} Inverter Energy Consumed",
            "winvconsq",
            "mdi:power-plug",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        ThreePhaseEnergyFerroampSensor(
            f"{name} Load Energy Produced",
            "wloadprodq",
            "mdi:power-plug",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        ThreePhaseEnergyFerroampSensor(
            f"{name} Load Energy Consumed",
            "wloadconsq",
            "mdi:power-plug",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        EnergyFerroampSensor(
            f"{name} Total Solar Energy",
            "wpv",
            "mdi:solar-power",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        EnergyFerroampSensor(
            f"{name} Battery Energy Produced",
            "wbatprod",
            "mdi:solar-power",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        EnergyFerroampSensor(
            f"{name} Battery Energy Consumed",
            "wbatcons",
            "mdi:solar-power",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        IntValFerroampSensor(
            f"{name} System State",
            "state",
            "",
            "mdi:traffic-light",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        DcLinkFerroampSensor(
            f"{name} DC Link Voltage",
            "udc",
            "mdi:current-ac",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        BatteryFerroampSensor(
            f"{name} System State of Charge",
            "soc",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        BatteryFerroampSensor(
            f"{name} System State of Health",
            "soh",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        IntValFerroampSensor(
            f"{name} Apparent power",
            "sext",
            "VA",
            "mdi:transmission-tower",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        IntValFerroampSensor(
            f"{name} Solar Power",
            "ppv",
            POWER_WATT,
            "mdi:solar-power",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        IntValFerroampSensor(
            f"{name} Battery Power",
            "pbat",
            POWER_WATT,
            "mdi:battery",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
        IntValFerroampSensor(
            f"{name} Total rated capacity of all batteries",
            "ratedcap",
            ENERGY_WATT_HOUR,
            "mdi:battery",
            f"{slug}_{EHUB}",
            f"{name} {EHUB_NAME}",
            interval,
            config_id,
        ),
    ]
