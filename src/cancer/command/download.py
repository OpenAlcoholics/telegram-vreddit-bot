import logging
import os
import signal
import subprocess
import sys
import uuid
from tempfile import TemporaryDirectory
from typing import List

from yt_dlp import YoutubeDL

from cancer import telegram
from cancer.adapter.mqtt import MqttSubscriber, MqttConfig
from cancer.adapter.rabbit import RabbitConfig, RabbitSubscriber
from cancer.message import DownloadMessage, Topic
from cancer.port.subscriber import Subscriber

_STORAGE_DIR = os.getenv("STORAGE_DIR", "downloads")
_UPLOAD_CHAT = os.getenv("UPLOAD_CHAT_ID", "1259947317")

_LOG = logging.getLogger(__name__)


def _download_videos(base_folder: str, url: str) -> List[str]:
    cure_id = str(uuid.uuid4())
    cure_dir = os.path.join(base_folder, cure_id)
    os.mkdir(cure_dir)

    ytdl = YoutubeDL(params={
        "outtmpl": f"{cure_dir}/output%(autonumber)d.%(ext)s",
    })

    return_code = ytdl.download([url])
    if return_code != 0:
        _LOG.error("YTDL returned error code %d", return_code)
        return []

    cure_names = os.listdir(cure_dir)
    _LOG.debug("Downloaded files %s", cure_names)

    return [
        os.path.join(cure_dir, cure_name)
        for cure_name in cure_names
    ]


def _convert_cure(input_path: str, output_path: str):
    _LOG.info("Converting from %s to %s", input_path, output_path)
    process = subprocess.Popen([
        'ffmpeg',
        '-i', input_path,
        output_path,
    ])
    if process.wait() != 0:
        raise RuntimeError("Could not convert file!")


def _ensure_compatibility(original_path: str) -> str:
    base, ext = os.path.splitext(original_path)
    if ext == ".mp4":
        return original_path

    converted_path = f"{base}.mp4"
    _convert_cure(original_path, converted_path)
    return converted_path


def _upload_video(video_file: str) -> str:
    cure_path = _ensure_compatibility(video_file)
    message = telegram.upload_video(_UPLOAD_CHAT, cure_path)
    video = message["video"]
    file_id = video["file_id"]
    return file_id


def _handle_payload(payload: DownloadMessage) -> Subscriber.Result:
    _LOG.info("Received payload: %s", payload)

    with TemporaryDirectory(dir=_STORAGE_DIR) as folder:
        files = [
            file
            for url in payload.urls
            for file in _download_videos(folder, url)
        ]
        video_ids = [_upload_video(file) for file in files]

        telegram.send_video_group(
            chat_id=payload.chat_id,
            reply_to_message_id=payload.message_id,
            videos=video_ids,
        )

        return Subscriber.Result.Ack


def run():
    telegram.check()

    if not os.path.exists(_STORAGE_DIR):
        os.mkdir(_STORAGE_DIR)

    signal.signal(signal.SIGTERM, lambda _: sys.exit(0))

    legacy_topic = os.getenv("MQTT_TOPIC_DOWNLOAD")
    if legacy_topic == "cancer/instaDownload":
        topic = Topic.instaDownload
    else:
        topic = Topic.download
    _LOG.debug("Subscribing to topic %s", topic)
    subscriber: Subscriber
    try:
        subscriber = RabbitSubscriber(RabbitConfig.from_env())
    except ValueError as e:
        _LOG.info("Couldn't initialize Rabbit subscriber, falling back to MQTT")
        subscriber = MqttSubscriber(MqttConfig.from_env())

    subscriber.subscribe(topic, DownloadMessage, _handle_payload)
