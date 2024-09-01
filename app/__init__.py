import os
from io import BytesIO

import requests

from app.callbacks import depth_event, kline_event
from app.connection_manager import ConnectionManager

from .zex import Zex

LIGHT_NODE = os.getenv("LIGHT_NODE")
ZEX_STATE_SOURCE = os.getenv("ZEX_STATE_SOURCE")
ZEX_STATE_DEST = os.getenv("ZEX_STATE_DEST")
assert ZEX_STATE_DEST is not None, "ZEX_STATE_DEST must be specified"
# ZSEQ_HOST = os.environ.get("ZSEQ_HOST")
# ZSEQ_PORT = int(os.environ.get("ZSEQ_PORT"))
# ZSEQ_URL = f"http://{ZSEQ_HOST}:{ZSEQ_PORT}/node/transactions"
BLS_PRIVATE = os.environ.get("BLS_PRIVATE")
SCHNORR_PRIVATE = int(os.environ.get("SCHNORR_PRIVATE"))

assert (
    SCHNORR_PRIVATE or BLS_PRIVATE
), "SCHNORR_PRIVATE or BLS_PRIVATE env variable need to be set"

ZEX_BTC_PUBLIC_KEY = os.environ.get("ZEX_BTC_PUBLIC_KEY")
assert ZEX_BTC_PUBLIC_KEY, "ZEX_BTC_PUBLIC_KEY env variable is not set"
ZEX_MONERO_PUBLIC_ADDRESS = os.environ.get("ZEX_MONERO_PUBLIC_ADDRESS")
assert ZEX_MONERO_PUBLIC_ADDRESS, "ZEX_MONERO_PUBLIC_ADDRESS env variable is not set"

manager = ConnectionManager()


if ZEX_STATE_SOURCE:
    response = requests.get(ZEX_STATE_SOURCE)
    response.raise_for_status()
    data = BytesIO(response.content)
    zex = Zex.load_state(
        data=data,
        kline_callback=kline_event(manager),
        depth_callback=depth_event(manager),
        state_dest=ZEX_STATE_DEST,
        light_node=False if LIGHT_NODE is None else True,
    )
else:
    zex = Zex(
        kline_callback=kline_event(manager),
        depth_callback=depth_event(manager),
        state_dest=ZEX_STATE_DEST,
        light_node=False if LIGHT_NODE is None else True,
    )
