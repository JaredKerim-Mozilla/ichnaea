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

from colander import MappingSchema, SchemaNode, SequenceSchema, Boolean, Float, Integer, String, OneOf, Invalid, DateTime, Range

from ichnaea.service.submit.schema import CellSchema, BaseMeasureSchema

from ichnaea.models import RADIO_TYPE_KEYS


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


class TransformingSchema(MappingSchema):

    def deserialize(self, data):
        return super(TransformingSchema, self).deserialize(copy.copy(data))


class ValidCellBaseSchema(TransformingSchema):
    radio = DefaultNode(Integer(), missing=-1, validator=Range(MIN_RADIO_TYPE, MAX_RADIO_TYPE))
    mcc = SchemaNode(Integer(), validator=Range(1, 999))
    mnc = SchemaNode(Integer(), validator=Range(0, 32767))
    lac = DefaultNode(Integer(), missing=-1, validator=Range(1, 65535))
    cid = DefaultNode(Integer(), missing=-1, validator=Range(1, 268435455))
    psc = DefaultNode(Integer(), missing=-1, validator=Range(0, 512))
    lat = SchemaNode(Float(), missing=0.0, validator=Range(MIN_LAT, MAX_LAT))
    lon = SchemaNode(Float(), missing=0.0, validator=Range(-180, 180))
    signal = DefaultNode(Integer(), missing=0, validator=Range(-150, -1))
    ta = DefaultNode(Integer(), missing=0, validator=Range(0, 63))
    asu = DefaultNode(Integer(), missing=-1, validator=Range(0, 97))

    def deserialize(self, data, default_radio=-1):
        if data:
            if 'radio' in data:
                if isinstance(data['radio'], basestring):
                    data['radio'] = RADIO_TYPE.get(data['radio'], -1)

                # If a default radio was set, and we don't know, use it as fallback
                if data['radio'] == -1 and default_radio != -1:
                    data['radio'] = default_radio

                # If the cell id >= 65536 then it must be a umts tower
                if 'cid' in data and data['cid'] >= 65536 and data['radio'] == RADIO_TYPE['gsm']:
                    data['radio'] = RADIO_TYPE['umts']

            else:
                data['radio'] = default_radio

            # Treat cid=65535 without a valid lac as an unspecified value
            if 'lac' in data and 'cid' in data and data['lac'] == -1 and data['cid'] == 65535:
                data['cid'] = -1

        return super(ValidCellBaseSchema, self).deserialize(data)

    def validator(self, schema, data):
        if data['mcc'] not in ALL_VALID_MCCS:
            raise Invalid(schema, 'Check against the list of all known valid mccs')

        if data['radio'] == RADIO_TYPE['cdma'] and (data['lac'] < 0 or data['cid'] < 0):
            raise Invalid(schema, 'Skip CDMA towers missing lac or cid (no psc on CDMA exists to backfill using inference)')

        if (data['radio'] in (RADIO_TYPE['gsm'], RADIO_TYPE['umts'], RADIO_TYPE['lte']) and data['mnc'] > 999):
            raise Invalid(schema, 'Skip GSM/LTE/UMTS towers with an invalid MNC')

        if (data['lac'] == -1 or data['cid'] == -1) and data['psc'] == -1:
            raise Invalid(schema, 'Must have (lac and cid) or psc (psc-only to use in backfill)')


class ValidCellSchema(ValidCellBaseSchema):
    created = SchemaNode(LiteralDateTime(), missing=None)
    modified = SchemaNode(LiteralDateTime(), missing=None)
    changeable = SchemaNode(Boolean(), missing=True)
    total_measures = SchemaNode(Integer(), missing=0)
    range = SchemaNode(Integer(), missing=0)


class ValidCellMeasureSchema(ValidCellBaseSchema):
    accuracy = DefaultNode(Float(), missing=0, validator=Range(0, MAX_ACCURACY))
    altitude = DefaultNode(Float(), missing=0, validator=Range(MIN_ALTITUDE, MAX_ALTITUDE))
    altitude_accuracy = DefaultNode(Float(), missing=0, validator=Range(0, MAX_ALTITUDE_ACCURACY))
    created = SchemaNode(String(), missing=None)
    heading = DefaultNode(Integer(), missing=-1, validator=Range(0, MAX_HEADING))
    report_id = SchemaNode(String(), missing='', preparer=lambda report_id: report_id or uuid.uuid1().hex)
    speed = DefaultNode(Float(), missing=-1, validator=Range(0, MAX_SPEED))
    time = SchemaNode(String(), missing=None, preparer=lambda time: normalized_time(time) if time else datetime.date.today().strftime('%Y-%m-%d'))

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
            raise Invalid(schema, 'Must have (lac and cid) or psc (psc-only to use in backfill)')

        if not any([geocalc.location_is_in_country(data['lat'], data['lon'], c.alpha2, 1) for c in mobile_codes.mcc(str(data['mcc']))]):
            raise Invalid(schema, 'Lat/lon must be inside one of the bounding boxes for the MCC')

        if (data['radio'] in (RADIO_TYPE['gsm'], RADIO_TYPE['umts'], RADIO_TYPE['lte'])and data['mnc'] > 999):
            raise Invalid(schema, '{radio} can not have an MNC > 999'.format(radio=data['radio']))

        if data['radio'] == RADIO_TYPE['cdma'] and (data['lac'] < 0 or data['cid'] < 0):
            raise Invalid(schema, 'CDMA towers  must have lac or cid (no psc on CDMA exists to backfill using inference)')
