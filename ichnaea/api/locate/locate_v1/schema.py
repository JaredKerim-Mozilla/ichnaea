from colander import MappingSchema, SchemaNode, SequenceSchema
from colander import Integer, String, OneOf

from ichnaea.api.schema import (
    FallbackSchema,
    InternalMapping,
    InternalSchemaNode,
)
from ichnaea.api.locate.schema import BaseLocateSchema


RADIO_STRINGS = ['gsm', 'cdma', 'umts', 'wcdma', 'lte']


class CellSchema(MappingSchema):
    schema_type = InternalMapping

    radio = SchemaNode(String(),
                       validator=OneOf(RADIO_STRINGS), missing=None)
    mcc = SchemaNode(Integer(), missing=None)
    mnc = SchemaNode(Integer(), missing=None)
    lac = SchemaNode(Integer(), missing=None)
    cid = SchemaNode(Integer(), missing=None)

    asu = SchemaNode(Integer(), missing=None)
    psc = SchemaNode(Integer(), missing=None)
    signal = SchemaNode(Integer(), missing=None)
    ta = SchemaNode(Integer(), missing=None)


class CellsSchema(SequenceSchema):

    cell = CellSchema()


class WifiSchema(MappingSchema):
    schema_type = InternalMapping

    key = SchemaNode(String(), missing=None)
    frequency = SchemaNode(Integer(), missing=None)
    channel = SchemaNode(Integer(), missing=None)
    signal = SchemaNode(Integer(), missing=None)
    signalToNoiseRatio = InternalSchemaNode(
        Integer(), missing=None, internal_name='snr')


class WifisSchema(SequenceSchema):

    wifi = WifiSchema()


class LocateV1Schema(BaseLocateSchema):

    radio = SchemaNode(String(),
                       validator=OneOf(RADIO_STRINGS), missing=None)
    cell = CellsSchema(missing=())
    wifi = WifisSchema(missing=())
    fallbacks = FallbackSchema(missing=None)
