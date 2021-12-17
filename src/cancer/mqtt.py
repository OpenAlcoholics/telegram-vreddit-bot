import logging
import os
from typing import List, Callable, TypeVar, Type

from paho.mqtt.publish import multiple
from paho.mqtt.subscribe import callback

from cancer.message import Message

_LOG = logging.getLogger(__name__)

_HOST = os.getenv("MQTT_HOST")
_PORT = os.getenv("MQTT_PORT")
_USER = os.getenv("MQTT_USER")
_PASSWORD = os.getenv("MQTT_PASSWORD")
_TRANSPORT = os.getenv("MQTT_TRANSPORT", "tcp")


def check():
    if not _HOST:
        raise ValueError("MQTT_HOST missing")

    if not _PORT:
        raise ValueError("MQTT_PORT missing")
    else:
        int(_PORT)

    if not _USER:
        raise ValueError("MQTT_USER missing")

    if not _PASSWORD:
        raise ValueError("MQTT_PASSWORD missing")

    if not _TRANSPORT:
        raise ValueError("MQTT_TRANSPORT missing")

    _LOG.debug("Going to use %s transport", _TRANSPORT)


def publish_messages(messages: List[Message]):
    _LOG.debug("Publishing messages %s", messages)
    multiple(
        msgs=[
            dict(topic=message.topic(), qos=1, payload=message.serialize())
            for message in messages
        ],
        hostname=_HOST,
        port=int(_PORT),
        transport=_TRANSPORT,
        auth={"username": _USER, "password": _PASSWORD},
        tls={},
    )


T = TypeVar('T', bound=Message)


def subscribe(message_type: Type[T], handle: Callable[[T], None]):
    def on_message(client, userdata, message):
        payload = message.payload
        _LOG.debug("Received message with payload %s", payload)
        handle(message_type.deserialize(payload))

    callback(
        on_message,
        topics=[message_type.topic()],
        qos=1,
        hostname=_HOST,
        port=int(_PORT),
        transport=_TRANSPORT,
        auth={"username": _USER, "password": _PASSWORD},
        tls={},
    )
