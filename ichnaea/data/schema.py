import copy
import datetime
from ichnaea.customjson import encode_datetime
from datetime import timedelta
from colander import iso8601
from ichnaea import util

import uuid
import mobile_codes
from ichnaea import geocalc

from ichnaea.models import (
    MAX_RADIO_TYPE,
    MIN_RADIO_TYPE,
    RADIO_TYPE,
)

from ichnaea.data.constants import (
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

from colander import (
    MappingSchema,
    SchemaNode,
    Boolean,
    Float,
    Integer,
    String,
    Invalid,
    DateTime,
    Range,
)


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


class DefaultNode(SchemaNode):
    """
    A DefaultNode will use its ``missing`` value
    if it fails to validate during deserialization.
    """

    def deserialize(self, cstruct):
        try:
            return super(DefaultNode, self).deserialize(cstruct)
        except Invalid:
            return self.missing


class LiteralDateTime(DateTime):

    def deserialize(self, schema, cstruct):
        if type(cstruct) == datetime.datetime:
            return cstruct
        return super(LiteralDateTime, self).deserialize(schema, cstruct)


class DateTimeToString(String):

    def deserialize(self, schema, cstruct):
        if type(cstruct) == datetime.datetime:
            cstruct = cstruct.strftime('%Y-%m-%d')
        return super(DateTimeToString, self).deserialize(schema, cstruct)


def normalized_wifi_key(key):
    if ":" in key or "-" in key or "." in key:
        key = key.replace(":", "").replace("-", "").replace(".", "")
    return key.lower()


def valid_wifi_pattern(key):
    return INVALID_WIFI_REGEX.match(key) and \
        VALID_WIFI_REGEX.match(key) and len(key) == 12


class WifiKeyNode(SchemaNode):

    def preparer(self, cstruct):
        return normalized_wifi_key(cstruct)

    def validator(self, node, cstruct):
        if not valid_wifi_pattern(cstruct):
            raise Invalid(node, 'Invalid wifi key')


class ReportNode(SchemaNode):

    def preparer(self, cstruct):
        return cstruct or uuid.uuid1().hex


class TimeNode(SchemaNode):

    def preparer(self, cstruct):
        if cstruct:
            return normalized_time(cstruct)
        else:
            return datetime.date.today().strftime('%Y-%m-%d')


class CopyingSchema(MappingSchema):

    def deserialize(self, data):
        return super(CopyingSchema, self).deserialize(copy.copy(data))


class ValidMeasureSchema(CopyingSchema):
    lat = SchemaNode(Float(), missing=0.0, validator=Range(MIN_LAT, MAX_LAT))
    lon = SchemaNode(Float(), missing=0.0, validator=Range(-180, 180))
    accuracy = DefaultNode(
        Float(), missing=0, validator=Range(0, MAX_ACCURACY))
    altitude = DefaultNode(
        Float(), missing=0, validator=Range(MIN_ALTITUDE, MAX_ALTITUDE))
    altitude_accuracy = DefaultNode(
        Float(), missing=0, validator=Range(0, MAX_ALTITUDE_ACCURACY))
    heading = DefaultNode(Float(), missing=-1, validator=Range(0, MAX_HEADING))
    speed = DefaultNode(Float(), missing=-1, validator=Range(0, MAX_SPEED))
    report_id = ReportNode(String(), missing='')
    time = TimeNode(DateTimeToString(), missing=None)


class ValidWifiSchema(ValidMeasureSchema):
    signal = DefaultNode(Integer(), missing=0, validator=Range(-200, -1))
    signalToNoiseRatio = DefaultNode(
        Integer(), missing=0, validator=Range(0, 100))
    key = WifiKeyNode(String())
    channel = SchemaNode(Integer(), validator=Range(0, 166))

    def deserialize(self, data):
        if data:
            channel = int(data.get('channel', 0))

            if not 0 < channel < 166:
                # if no explicit channel was given, calculate
                freq = data.get('frequency', 0)

                if 2411 < freq < 2473:
                    # 2.4 GHz band
                    data['channel'] = (freq - 2407) // 5

                elif 5169 < freq < 5826:
                    # 5 GHz band
                    data['channel'] = (freq - 5000) // 5

                else:
                    data['channel'] = 0

            data.pop('frequency', None)
            data.pop('radio', None)

        return super(ValidWifiSchema, self).deserialize(data)


class ValidWifiMeasureSchema(ValidWifiSchema, ValidMeasureSchema):
    pass


class ValidCellBaseSchema(ValidMeasureSchema):
    asu = DefaultNode(Integer(), missing=-1, validator=Range(0, 97))
    cid = DefaultNode(Integer(), missing=-1, validator=Range(1, 268435455))
    lac = DefaultNode(Integer(), missing=-1, validator=Range(1, 65535))
    mcc = SchemaNode(Integer(), validator=Range(1, 999))
    mnc = SchemaNode(Integer(), validator=Range(0, 32767))
    psc = DefaultNode(Integer(), missing=-1, validator=Range(0, 512))
    radio = DefaultNode(
        Integer(), missing=-1, validator=Range(MIN_RADIO_TYPE, MAX_RADIO_TYPE))
    signal = DefaultNode(Integer(), missing=0, validator=Range(-150, -1))
    ta = DefaultNode(Integer(), missing=0, validator=Range(0, 63))

    def deserialize(self, data, default_radio=-1):
        if data:
            if 'radio' in data:
                if isinstance(data['radio'], basestring):
                    data['radio'] = RADIO_TYPE.get(data['radio'], -1)

                # If a default radio was set,
                # and we don't know, use it as fallback
                if data['radio'] == -1 and default_radio != -1:
                    data['radio'] = default_radio

                # If the cell id >= 65536 then it must be a umts tower
                if (data.get('cid', 0) >= 65536
                        and data['radio'] == RADIO_TYPE['gsm']):
                    data['radio'] = RADIO_TYPE['umts']

            else:
                data['radio'] = default_radio

            # Treat cid=65535 without a valid lac as an unspecified value
            if data.get('lac', -1) == -1 and data.get('cid', -1) == 65535:
                data['cid'] = -1

        return super(ValidCellBaseSchema, self).deserialize(data)

    def validator(self, schema, data):
        if data['mcc'] not in ALL_VALID_MCCS:
            raise Invalid(
                schema, 'Check against the list of all known valid mccs')

        if (data['radio'] == RADIO_TYPE['cdma']
                and (data['lac'] < 0 or data['cid'] < 0)):
            raise Invalid(schema, (
                'Skip CDMA towers missing lac or cid '
                '(no psc on CDMA exists to backfill using inference)'))

        radio_types = RADIO_TYPE['gsm'], RADIO_TYPE['umts'], RADIO_TYPE['lte']
        if data['radio'] in radio_types and data['mnc'] > 999:
            raise Invalid(
                schema, 'Skip GSM/LTE/UMTS towers with an invalid MNC')

        if (data['lac'] == -1 or data['cid'] == -1) and data['psc'] == -1:
            raise Invalid(schema, (
                'Must have (lac and cid) or '
                'psc (psc-only to use in backfill)'))


class ValidCellSchema(ValidCellBaseSchema):
    created = SchemaNode(LiteralDateTime(), missing=None)
    modified = SchemaNode(LiteralDateTime(), missing=None)
    changeable = SchemaNode(Boolean(), missing=True)
    total_measures = SchemaNode(Integer(), missing=0)
    range = SchemaNode(Integer(), missing=0)


class ValidCellMeasureSchema(ValidCellBaseSchema):
    created = SchemaNode(String(), missing=None)

    def deserialize(self, data):
        if data:
            # The radio field may be a string
            # If so we look it up in RADIO_TYPE
            if type(data.get('radio', None)) == str:
                data['radio'] = RADIO_TYPE.get(data['radio'], -1)

            # Sometimes the asu and signal fields are swapped
            if data.get('asu', 0) < -1 and data.get('signal', -1) == 0:
                data['signal'] = data['asu']
                data['asu'] = -1

        return super(ValidCellMeasureSchema, self).deserialize(data)

    def validator(self, schema, data):
        if (data['lac'] == -1 or data['cid'] == -1) and data['psc'] == -1:
            raise Invalid(schema, (
                'Must have (lac and cid) or '
                'psc (psc-only to use in backfill)'))

        in_country = [
            geocalc.location_is_in_country(
                data['lat'], data['lon'], code.alpha2, 1)
            for code in mobile_codes.mcc(str(data['mcc']))
        ]

        if not any(in_country):
            raise Invalid(schema, (
                'Lat/lon must be inside one of '
                'the bounding boxes for the MCC'))

        radio_types = RADIO_TYPE['gsm'], RADIO_TYPE['umts'], RADIO_TYPE['lte']
        if data['radio'] in radio_types and data['mnc'] > 999:
            raise Invalid(
                schema,
                '{radio} can not have an MNC > 999'.format(
                    radio=data['radio']))

        if (data['radio'] == RADIO_TYPE['cdma'] and
                (data['lac'] < 0 or data['cid'] < 0)):
            raise Invalid(schema, (
                'CDMA towers  must have lac or cid (no psc '
                'on CDMA exists to backfill using inference)'))
