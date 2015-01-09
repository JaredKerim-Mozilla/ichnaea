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

from colander import MappingSchema, SchemaNode, SequenceSchema, Float, Integer, String, OneOf, Invalid, DateTime, Range

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


class ValidCellMeasureSchema(CellSchema, BaseMeasureSchema):
    accuracy = DefaultNode(Float(), missing=0, validator=Range(0, MAX_ACCURACY))
    altitude = DefaultNode(Float(), missing=0, validator=Range(MIN_ALTITUDE, MAX_ALTITUDE))
    altitude_accuracy = DefaultNode(Float(), missing=0, validator=Range(0, MAX_ALTITUDE_ACCURACY))
    asu = DefaultNode(Integer(), missing=-1, validator=Range(0, 97))
    cid = DefaultNode(Integer(), missing=-1, validator=Range(1, 268435455))
    created = SchemaNode(String(), missing=None)
    heading = DefaultNode(Integer(), missing=-1, validator=Range(0, MAX_HEADING))
    lac = DefaultNode(Integer(), missing=-1, validator=Range(1, 65535))
    lat = SchemaNode(Float(), validator=Range(MIN_LAT, MAX_LAT))
    lon = SchemaNode(Float(), validator=Range(-180, 180))
    mcc = SchemaNode(Integer(), validator=Range(1, 999))
    mnc = SchemaNode(Integer(), validator=Range(0, 32767))
    psc = DefaultNode(Integer(), missing=-1, validator=Range(0, 512))
    radio = DefaultNode(Integer(), missing=-1, validator=Range(MIN_RADIO_TYPE, MAX_RADIO_TYPE))
    report_id = SchemaNode(String(), missing='', preparer=lambda report_id: report_id or uuid.uuid1().hex)
    signal = DefaultNode(Integer(), missing=0, validator=Range(-150, -1))
    speed = DefaultNode(Float(), missing=-1, validator=Range(0, MAX_SPEED))
    ta = DefaultNode(Integer(), missing=0, validator=Range(0, 63))
    time = SchemaNode(String(), missing=None, preparer=lambda time: normalized_time(time) if time else datetime.date.today().strftime('%Y-%m-%d'))

    def deserialize(self, data):
        if data:
            # The radio field may be a string
            # If so we look it up in RADIO_TYPE
            if type(data.get('radio', None)) == str:
                data['radio'] = RADIO_TYPE.get(data['radio'], -1)

            # If the cell id >= 65536 then it must be a umts tower
            if data.get('cid', 0) >= 65536 and data.get('radio', -1) == RADIO_TYPE['gsm']:
                data['radio'] = RADIO_TYPE['umts']

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
