from datetime import timedelta
import uuid

from colander import iso8601
import mobile_codes

from ichnaea.customjson import (
    encode_datetime,
)
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
from ichnaea.data.schema import ValidCellMeasureSchema


def valid_wifi_pattern(key):
    return INVALID_WIFI_REGEX.match(key) and \
        VALID_WIFI_REGEX.match(key) and len(key) == 12


def normalized_time(time):
    """
    Takes a string representation of a time value, validates and parses
    it and returns a JSON-friendly string representation of the normalized
    time.
    """
    now = util.utcnow()
    if not time:
        time = None

    try:
        time = iso8601.parse_date(time)
    except (iso8601.ParseError, TypeError):
        time = now
    else:
        # don't accept future time values or
        # time values more than 60 days in the past
        min_time = now - timedelta(days=60)
        if time > now or time < min_time:
            time = now
    # cut down the time to a monthly resolution
    time = time.date().replace(day=1)
    return encode_datetime(time)


def normalized_wifi_key(key):
    if ":" in key or "-" in key or "." in key:
        key = key.replace(":", "").replace("-", "").replace(".", "")
    return key.lower()


def normalized_dict_value(data, k, lo, hi, default=REQUIRED):
    """
    Returns a dict value data[k] if within range [lo,hi]. If the
    Value is missing or out of range, return default, unless
    default is REQUIRED, in which case return None.
    """
    if k not in data or data[k] < lo or data[k] > hi:
        if default is REQUIRED:
            print '{field} is required between {lo} and {hi}, found value: {value}'.format(field=k, lo=lo, hi=hi, value=data[k])
            return None
        else:
            return default
    else:
        return data[k]


def normalized_dict(data, specs):
    """
    Returns a copy of the provided dict, with its values set to a default
    value if missing or outside a specified range. If any missing or
    out-of-range values were specified as REQUIRED, return None.

    Arguments:
    data -- a dict to normalize
    specs -- a dict mapping keys to (lo, hi, default) triples, where
             default may be the symbolic constant REQUIRED;
             if any REQUIRED fields are missing or out of
             range, return None.
    """
    if not isinstance(data, dict):
        return None

    n = {}
    for (k, (lo, hi, default)) in specs.items():
        v = normalized_dict_value(data, k, lo, hi, default)
        if v is None:
            return None
        n[k] = v

    # copy forward anything not specified
    for (k, v) in data.items():
        if k not in n:
            n[k] = v
    return n


def normalized_measure_dict(data):
    """
    Returns a normalized copy of the provided measurement dict data,
    or None if the dict was invalid.
    """
    data = normalized_dict(
        data, dict(lat=(MIN_LAT, MAX_LAT, REQUIRED),
                lon=(-180.0, 180.0, REQUIRED),
                heading=(0.0, MAX_HEADING, -1.0),
                speed=(0, MAX_SPEED, -1.0),
                altitude=(MIN_ALTITUDE, MAX_ALTITUDE, 0),
                altitude_accuracy=(0, MAX_ALTITUDE_ACCURACY, 0),
                accuracy=(0, MAX_ACCURACY, 0)))

    if data is None:
        return None

    data['time'] = normalized_time(data.get('time', None))

    if 'report_id' not in data:
        data['report_id'] = uuid.uuid1().hex
    return data


def normalized_wifi_channel(data):
    chan = int(data.get('channel', 0))

    if 0 < chan and chan < 166:
        return chan

    # if no explicit channel was given, calculate
    freq = data.get('frequency', 0)

    if 2411 < freq < 2473:
        # 2.4 GHz band
        return (freq - 2407) // 5

    elif 5169 < freq < 5826:
        # 5 GHz band
        return (freq - 5000) // 5

    return 0


def normalized_wifi_dict(data):
    """
    Returns a normalized copy of the provided wifi dict data,
    or None if the dict was invalid.
    """
    data = normalized_dict(
        data, dict(signal=(-200, -1, 0),
                signalToNoiseRatio=(0, 100, 0)))

    if data is None:  # pragma: no cover
        return None

    if 'key' not in data:  # pragma: no cover
        return None

    data['key'] = normalized_wifi_key(data['key'])

    if not valid_wifi_pattern(data['key']):
        return None

    data['channel'] = normalized_wifi_channel(data)
    data.pop('frequency', 0)

    if 'radio' in data:
        del data['radio']

    return data


def normalized_wifi_measure_dict(data):
    """
    Returns a normalized copy of the provided wifi-measure dict data,
    or None if the dict was invalid.
    """
    data = normalized_wifi_dict(data)
    return normalized_measure_dict(data)


def normalized_cell_dict(data, default_radio=-1):
    """
    Returns a normalized copy of the provided cell dict data,
    or None if the dict was invalid.
    """
    if not isinstance(data, dict):  # pragma: no cover
        return None

    data = data.copy()
    if 'radio' in data and isinstance(data['radio'], basestring):
        data['radio'] = RADIO_TYPE.get(data['radio'], -1)

    data = normalized_dict(
        data, dict(radio=(MIN_RADIO_TYPE, MAX_RADIO_TYPE, default_radio),
                mcc=(1, 999, REQUIRED),
                mnc=(0, 32767, REQUIRED),
                lac=(1, 65535, -1),
                cid=(1, 268435455, -1),
                psc=(0, 512, -1)))

    if data is None:
        return None

    # Check against the list of all known valid mccs
    if data['mcc'] not in ALL_VALID_MCCS:
        return None

    # If a default radio was set, and we don't know, use it as fallback
    if data['radio'] == -1 and default_radio != -1:
        data['radio'] = default_radio

    # Skip CDMA towers missing lac or cid (no psc on CDMA exists to
    # backfill using inference)
    if data['radio'] == RADIO_TYPE['cdma'] and (data['lac'] < 0 or data['cid'] < 0):
        return None

    # Skip GSM/LTE/UMTS towers with an invalid MNC
    if (data['radio'] in (
            RADIO_TYPE['gsm'], RADIO_TYPE['umts'], RADIO_TYPE['lte'])
            and data['mnc'] > 999):
        return None

    # Treat cid=65535 without a valid lac as an unspecified value
    if data['lac'] == -1 and data['cid'] == 65535:
        data['cid'] = -1

    # Must have (lac and cid) or psc (psc-only to use in backfill)
    if (data['lac'] == -1 or data['cid'] == -1) and data['psc'] == -1:
        return None

    # If the cell id >= 65536 then it must be a umts tower
    if data['cid'] >= 65536 and data['radio'] == RADIO_TYPE['gsm']:
        data['radio'] = RADIO_TYPE['umts']

    return data


def normalized_cell_measure_dict(data, measure_radio=-1):
    """
    Returns a normalized copy of the provided cell-measure dict data,
    or None if the dict was invalid.
    """
    try:
        return ValidCellMeasureSchema().deserialize(data)
    except Invalid, e:
        return None
