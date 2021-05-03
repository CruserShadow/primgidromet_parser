from dataclasses import dataclass
from typing import Tuple
from enum import Enum


class Period(Enum):
    night = 0
    daylight = 1


@dataclass
class Wind:
    wind_speed: str
    direction: str = None


@dataclass
class Station:
    name: str
    time: float
    wind: Wind


@dataclass
class PeriodForecast:
    forecast_period: Period

    wind_info: Wind

    atmosphere: str
    precipitation: str
    visibility: str
    wave_height: str
    temperature: Tuple[int, int]


@dataclass
class OneZoneForecast:
    zone_name: str
    day: PeriodForecast = None
    night: PeriodForecast = None
