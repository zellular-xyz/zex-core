import json
import os
import random
import time
from struct import pack, unpack
from threading import Lock, Thread

import requests
import websocket
from eth_hash.auto import keccak
from secp256k1 import PrivateKey
from websocket import WebSocket, WebSocketApp

DEPOSIT, WITHDRAW, BUY, SELL, CANCEL = b"dwbsc"

version = pack(">B", 1)

ip = os.getenv("HOST")
port = int(os.getenv("PORT") or 8000)


class ZexBot:
    def __init__(
        self,
        private_key: bytes,
        pair: str,
        side: str,
        best_bid: tuple[float, float],
        best_ask: tuple[float, float],
        digits: int,
        lock: Lock,
        seed: int | None = 1,
    ) -> None:
        self.privkey = PrivateKey(private_key, raw=True)
        self.pair = pair
        self.side = side
        self.send_tx_lock = lock
        self.is_running = False
        self.digits = digits
        self.rng = random.Random(seed)

        self.pubkey = self.privkey.pubkey.serialize()
        self.nonce = 0
        self.counter = 0
        self.orders = set()
        self.websocket: WebSocketApp = None

        # self.best_bid = (1950.0, 10)
        self.best_bid = best_bid
        self.bids = {best_bid[0]: best_bid[1]}

        self.best_ask = best_ask
        self.asks = {best_ask[0]: best_ask[1]}

    def on_open_wrapper(self):
        def on_open(ws: WebSocket):
            time.sleep(1)
            ws.send(
                json.dumps(
                    {
                        "method": "SUBSCRIBE",
                        "params": [f"{self.pair}@kline_1m", f"{self.pair}@depth"],
                        "id": 1,
                    }
                )
            )

        return on_open

    def on_messsage_wrapper(self):
        def on_message(_, msg):
            data = json.loads(msg)
            if "id" in data:
                return
            elif "depth" in data["stream"]:
                for price, qty in data["data"]["b"]:
                    if qty == 0:
                        if price in self.bids:
                            del self.bids[price]
                    else:
                        self.bids[price] = qty
                for price, qty in data["data"]["a"]:
                    if qty == 0:
                        if price in self.asks:
                            del self.asks[price]
                    else:
                        self.asks[price] = qty
                best_bid_price = max(self.bids.keys())
                self.best_bid = (best_bid_price, self.bids[best_bid_price])
                best_ask_price = min(self.asks.keys())
                self.best_ask = (best_ask_price, self.asks[best_ask_price])

        return on_message

    def create_order(
        self,
        price: float | int,
        volume: float,
        maker: bool = False,
        verbose=True,
    ):
        if self.side == "buy":
            tx = (
                pack(">B", BUY)
                + self.pair[:3].encode()
                + pack(">I", int(self.pair[4]))
                + self.pair[6:9].encode()
                + pack(">I", int(self.pair[10]))
                + pack(">d", volume)
                + pack(">d", float(price))
            )
        elif self.side == "sell":
            tx = (
                pack(">B", SELL)
                + self.pair[:3].encode()
                + pack(">I", int(self.pair[4]))
                + self.pair[6:9].encode()
                + pack(">I", int(self.pair[10]))
                + pack(">d", volume)
                + pack(">d", price)
            )
        if verbose:
            print(
                f"pair: {self.pair}, maker: {maker}, side: {self.side}, price: {price}, vol: {volume}"
            )
        tx = version + tx
        name = tx[1]
        t = int(time.time())
        tx += pack(">II", t, self.nonce) + self.pubkey
        msg = "v: 1\n"
        msg += f'name: {"buy" if name == BUY else "sell"}\n'
        msg += f'base token: {tx[2:5].decode("ascii")}:{unpack(">I", tx[5:9])[0]}\n'
        msg += f'quote token: {tx[9:12].decode("ascii")}:{unpack(">I", tx[12:16])[0]}\n'
        msg += f'amount: {unpack(">d", tx[16:24])[0]}\n'
        msg += f'price: {unpack(">d", tx[24:32])[0]}\n'
        msg += f"t: {t}\n"
        msg += f"nonce: {self.nonce}\n"
        msg += f"public: {self.pubkey.hex()}\n"
        msg = "\x19Ethereum Signed Message:\n" + str(len(msg)) + msg
        self.nonce += 1
        sig = self.privkey.ecdsa_sign(keccak(msg.encode("ascii")), raw=True)
        sig = self.privkey.ecdsa_serialize_compact(sig)
        tx += sig
        tx += pack(">Q", self.counter)
        self.counter += 1
        return tx

    def run(self):
        websocket.enableTrace(False)
        self.websocket = WebSocketApp(
            f"ws://{ip}:{port}/ws",
            on_open=self.on_open_wrapper(),
            on_message=self.on_messsage_wrapper(),
        )
        Thread(target=self.websocket.run_forever, kwargs={"reconnect": 5}).start()
        self.is_running = True
        while self.is_running:
            time.sleep(2)
            maker = self.rng.choices([True, False], [0.5, 0.75])[0]
            price = 0
            if maker:
                if self.side == "buy":
                    price = self.best_ask[0] - (
                        self.best_ask[0] * 0.05 * self.rng.random()
                    )
                elif self.side == "sell":
                    price = self.best_bid[0] + (
                        self.best_bid[0] * 0.05 * self.rng.random()
                    )
            else:
                if self.side == "buy":
                    price = self.best_ask[0]
                elif self.side == "sell":
                    price = self.best_bid[0]
            price = round(price, self.digits)
            volume = round(self.rng.random() * 0.02, 3)
            while volume < 0.001:
                volume = round(self.rng.random() * 0.02, 3)

            resp = requests.get(
                f"http://{ip}:{port}/api/v1/user/{self.pubkey.hex()}/nonce"
            )
            self.nonce = resp.json()["nonce"]
            # with self.send_tx_lock:
            tx = self.create_order(price, volume, maker=maker).decode("latin-1")
            self.orders.add(tx)
            requests.post(f"http://{ip}:{port}/api/v1/txs", json=[tx])