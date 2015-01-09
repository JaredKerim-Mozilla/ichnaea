import datetime

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
    time = SchemaNode(DateTime(), missing=None, preparer=lambda time: time or datetime.datetime.now())
    created = SchemaNode(DateTime(), missing=None, preparer=lambda created: created or datetime.datetime.now())

    #lat=(MIN_LAT, MAX_LAT, REQUIRED)
    lat = SchemaNode(Float(), validator=Range(MIN_LAT, MAX_LAT))
    #lon=(-180, 180, REQUIRED)
    lon = SchemaNode(Float(), validator=Range(-180, 180))
    #mcc=(1, 999, REQUIRED)
    mcc = SchemaNode(Integer(), validator=Range(1, 999))
    #mnc=(0, 32767, REQUIRED)
    mnc = SchemaNode(Integer(), validator=Range(0, 32767))
    #heading=(0, MAX_HEADING, -1)
    heading = DefaultNode(Integer(), missing=-1, validator=Range(0, MAX_HEADING))
    #speed=(0, MAX_SPEED, -1)
    speed = DefaultNode(Integer(), missing=-1, validator=Range(0, MAX_SPEED))
    #altitude=(MIN_ALTITUDE, MAX_ALTITUDE, 0)
    altitude = DefaultNode(Integer(), missing=0, validator=Range(MIN_ALTITUDE, MAX_ALTITUDE))
    #altitude_accuracy=(0, MAX_ALTITUDE_ACCURACY, 0)
    altitude_accuracy = DefaultNode(Integer(), missing=0, validator=Range(0, MAX_ALTITUDE_ACCURACY))
    #accuracy=(0, MAX_ACCURACY, 0)))
    accuracy = DefaultNode(Integer(), missing=0, validator=Range(0, MAX_ACCURACY))
    #radio=(MIN_RADIO_TYPE, MAX_RADIO_TYPE, missing_radio)
    radio = DefaultNode(Integer(), missing=-1, validator=Range(MIN_RADIO_TYPE, MAX_RADIO_TYPE))
    #lac=(1, 65535, -1)
    lac = DefaultNode(Integer(), missing=-1, validator=Range(1, 65535))
    #cid=(1, 268435455, -1)
    cid = DefaultNode(Integer(), missing=-1, validator=Range(1, 268435455))
    #psc=(0, 512, -1)))
    psc = DefaultNode(Integer(), missing=-1, validator=Range(0, 512))
    #asu=(0, 97, -1)
    asu = DefaultNode(Integer(), missing=-1, validator=Range(0, 97))
    #signal=(-150, -1, 0)
    signal = DefaultNode(Integer(), missing=0, validator=Range(-150, -1))
    #ta=(0, 63, 0)))
    ta = DefaultNode(Integer(), missing=0, validator=Range(0, 63))
    report_id = SchemaNode(String(), missing='', preparer=lambda report_id: report_id or uuid.uuid1().hex)

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
