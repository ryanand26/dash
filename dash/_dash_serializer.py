import base64
import json
import uuid
import random
import pandas as pd


srd = random.Random(0)


PROP_TYPE = "__type"
PROP_VALUE = "__value"
PROP_ENGINE = "__engine"
PROP_ID = "__internal_id"


class NotSerializable(Exception):
    pass


class DashSerializer:
    @classmethod
    def __serialize_value(cls, prop):
        try:
            serializeFn = getattr(prop, "serialize")
            return serializeFn()
        except AttributeError:
            pass

        if isinstance(prop, pd.DataFrame):
            # TODO: Consider partial updates
            # => Consider borrowing idea from DataTableAIO for stateless DataFrame
            # shared between server & client side
            # let's try with `.fastparquet` file instead of using redis
            engine = "fastparquet"
            internalId = str(
                uuid.UUID(int=srd.randint(0, 2 ** 128))
            )  # TODO: fix to rely on component_id
            outputPath = "{}.fastparquet".format(internalId)
            prop.to_parquet(outputPath, compression="gzip", engine=engine)
            with open(outputPath, encoding="ISO-8859-1") as f:
                buffer_val = f.read().encode("utf-8")
                f.close()
            b64Value = base64.b64encode(buffer_val).decode("utf-8")
            return {
                PROP_TYPE: "pd.DataFrame",
                PROP_VALUE: b64Value,
                PROP_ENGINE: engine,
                PROP_ID: internalId,
            }

        raise NotSerializable

    @classmethod
    def __deserialize_value(cls, prop):
        try:
            deserializeFn = getattr(prop, "deserialize")
            return deserializeFn()
        except AttributeError:
            pass
        try:
            jsonObj = json.loads(prop) if isinstance(prop, str) else prop
            obj = (
                jsonObj
                if isinstance(jsonObj, dict) and PROP_TYPE in jsonObj
                else {PROP_TYPE: None, PROP_ENGINE: None}
            )
            [_type, _engine, _id] = [obj[PROP_TYPE], obj[PROP_ENGINE], obj[PROP_ID]]
            if _type == "pd.DataFrame":
                # TODO: Consider partial updates? - use _id to find from file for original/full DataFrame, then apply patch only?
                return pd.read_parquet(obj[PROP_VALUE], _engine)
        except AttributeError:
            pass
        return prop

    @classmethod
    def deserialize(cls, obj):
        props = obj if isinstance(obj, list) else [obj]
        return [
            (
                {**prop, "value": DashSerializer.__deserialize_value(prop["value"])}
                if "value" in prop
                else prop
            )
            for prop in props
        ]

    @classmethod
    def serialize(cls, obj):
        try:
            return DashSerializer.__serialize_value(obj)
        except NotSerializable:
            pass

        # Plotly
        try:
            obj = obj.to_plotly_json()
        except AttributeError:
            pass

        if isinstance(obj, (list, tuple)):
            if obj:
                # Must process list recursively even though it may be slow
                return [cls.serialize(v) for v in obj]

        # Recurse into lists and dictionaries
        if isinstance(obj, dict):
            return {k: cls.serialize(v) for k, v in obj.items()}

        return obj
