from datetime import timedelta
import uuid

from colander import iso8601
import mobile_codes

from ichnaea.customjson import encode_datetime
from ichnaea import geocalc
from ichnaea.models import (
    MAX_RADIO_TYPE,
    MIN_RADIO_TYPE,
    RADIO_TYPE,
)
from ichnaea import util
from ichnaea.data.constants import (
    REQUIRED,
    MAX_LAT,
    MIN_LAT,
    MAX_ACCURACY,
    MIN_ALTITUDE,
    MAX_ALTITUDE,
    MAX_ALTITUDE_ACCURACY,
    MAX_HEADING,
    MAX_SPEED,
    ALL_VALID_MCCS,
    INVALID_WIFI_REGEX,
    VALID_WIFI_REGEX,
)

from colander import Invalid
from ichnaea.data.schema import ValidMeasureSchema, ValidCellSchema, ValidCellMeasureSchema, ValidWifiSchema, ValidWifiMeasureSchema


def normalized_measure_dict(data):
    try:
        validated = ValidMeasureSchema().deserialize(data)
    except Exception, e:
        validated = None
    return validated


def normalized_wifi_dict(data):
    """
    Returns a normalized copy of the provided wifi dict data,
    or None if the dict was invalid.
    """
    try:
        validated = ValidWifiSchema().deserialize(data)
    except Exception, e:
        validated = None
    return validated


def normalized_wifi_measure_dict(data):
    """
    Returns a normalized copy of the provided wifi-measure dict data,
    or None if the dict was invalid.
    """
    try:
        validated = ValidWifiMeasureSchema().deserialize(data)
    except Exception, e:
        validated = None
    return validated


def normalized_cell_dict(data, default_radio=-1):
    """
    Returns a normalized copy of the provided cell dict data,
    or None if the dict was invalid.
    """
    try:
        validated = ValidCellSchema().deserialize(data, default_radio=default_radio)
    except Invalid, e:
        validated = None
    return validated


def normalized_cell_measure_dict(data, measure_radio=-1):
    """
    Returns a normalized copy of the provided cell-measure dict data,
    or None if the dict was invalid.
    """
    try:
        validated = ValidCellMeasureSchema().deserialize(data)
    except Invalid, e:
        validated = None
    return validated
