import asyncio
from copy import deepcopy
import heapq
from struct import unpack
from collections import deque
from threading import Lock
from time import time as unix_time
from typing import Callable

import pandas as pd
import line_profiler
from loguru import logger

from models.transaction import (
    DepositTransaction,
    WithdrawTransaction,
)
from verify import chunkify, verify
import tx_utils


DEPOSIT, WITHDRAW, BUY, SELL, CANCEL = b"dwbsc"

TRADES_TTL = 1000


class SingletonMeta(type):
    """
    This is a thread-safe implementation of Singleton.
    """

    _instances = {}

    _lock: Lock = Lock()
    """
    We now have a lock object that will be used to synchronize threads during
    first access to the Singleton.
    """

    def __call__(cls, *args, **kwargs):
        """
        Possible changes to the value of the `__init__` argument do not affect
        the returned instance.
        """
        # Now, imagine that the program has just been launched. Since there's no
        # Singleton instance yet, multiple threads can simultaneously pass the
        # previous conditional and reach this point almost at the same time. The
        # first of them will acquire lock and will proceed further, while the
        # rest will wait here.
        with cls._lock:
            # The first thread to acquire the lock, reaches this conditional,
            # goes inside and creates the Singleton instance. Once it leaves the
            # lock block, a thread that might have been waiting for the lock
            # release may then enter this section. But since the Singleton field
            # is already initialized, the thread won't create a new object.
            if cls not in cls._instances:
                instance = super().__call__(*args, **kwargs)
                cls._instances[cls] = instance
        return cls._instances[cls]


class Zex(metaclass=SingletonMeta):
    def __init__(
        self,
        kline_callback: Callable[[str, pd.DataFrame], None],
        depth_callback: Callable[[str, dict], None],
        benchmark_mode=False,
    ):
        self.kline_callback = kline_callback
        self.depth_callback = depth_callback

        self.benchmark_mode = benchmark_mode

        self.markets: dict[str, Market] = {}
        self.balances = {}
        self.amounts = {}
        self.trades = {}
        self.orders = {}
        self.withdrawals = {}
        self.deposited_blocks = {"pol": 0, "eth": 0, "bst": 42051703}
        self.nonces = {}

    @line_profiler.profile
    def process(self, txs: list[bytes]):
        verify(txs)
        modified_pairs = set()
        for tx in txs:
            if not tx:
                continue
            v, name = tx[0:2]
            if v != 1:
                logger.error("invalid verion", version=v)
                continue

            if name == DEPOSIT:
                self.deposit(tx)
            elif name == WITHDRAW:
                tx = WithdrawTransaction.from_tx(tx)
                self.withdraw(tx)
            elif name in (BUY, SELL):
                pair = tx_utils.pair(tx)
                if pair not in self.markets:
                    base_token = tx_utils.base_token(tx)
                    quote_token = tx_utils.quote_token(tx)
                    self.markets[pair] = Market(base_token, quote_token, self)
                    if base_token not in self.balances:
                        self.balances[base_token] = {}
                    if quote_token not in self.balances:
                        self.balances[quote_token] = {}
                # fast route check for instant match
                # if self.orderbooks[pair].match_instantly(tx):
                #     modified_pairs.add(pair)
                #     continue
                t = tx_utils.time(tx)
                self.markets[pair].place(tx)
                while self.markets[pair].match(t):
                    pass
                modified_pairs.add(pair)

            elif name == CANCEL:
                self.markets[pair].cancel(tx)
                modified_pairs.add(pair)
            else:
                raise ValueError(f"invalid transaction name {name}")
        for pair in modified_pairs:
            if self.benchmark_mode:
                break
            asyncio.create_task(self.kline_callback(pair, self.get_kline(pair)))
            asyncio.create_task(
                self.depth_callback(pair, self.get_order_book_update(pair))
            )

    def deposit(self, tx: bytes):
        chain = tx_utils.base_chain(tx)
        from_block, to_block, count = unpack(">QQH", tx[5:23])
        if self.deposited_blocks[chain] != from_block - 1:
            logger.error(
                f"invalid from block. self.deposited_blocks[chain]: {self.deposited_blocks[chain]}, from_block - 1: {from_block - 1}"
            )
            return
        self.deposited_blocks[chain] = to_block

        # chunk_size = 49
        # deposits = [tx[i : i + chunk_size] for i in range(0, len(tx), chunk_size)]
        deposits = list(chunkify(tx[23 : 23 + 49 * count], 49))
        for chunk in deposits:
            token = f"{chain}:{unpack('>I', chunk[:4])[0]}"
            amount, t = unpack(">dI", chunk[4:16])
            public = chunk[16:49]
            if token not in self.balances:
                self.balances[token] = {}
            if public not in self.balances[token]:
                self.balances[token][public] = 0
            self.balances[token][public] += amount
            if public not in self.trades:
                self.trades[public] = deque()
                self.orders[public] = {}
                self.nonces[public] = 0

    def cancel(self, tx: bytes):
        operation = tx_utils.operation(tx)
        base_token, quote_token = tx_utils.base_token(tx), tx_utils.quote_token(tx)
        amount, price = tx_utils.amount(tx), tx_utils.price(tx)
        public = tx_utils.public(tx)
        order_slice = tx_utils.order_slice(tx)
        for order in self.orders[public]:
            if order_slice not in order:
                continue
            self.amounts[order] = 0
            if operation == BUY:
                self.balances[quote_token][public] += amount * price
            else:
                self.balances[base_token][public] += amount
            break
        else:
            raise Exception("order not found")

    def withdraw(self, tx: WithdrawTransaction):
        if self.nonces[tx.public] != tx.nonce:
            logger.debug(f"invalid nonce: {self.nonces[tx.public]} != {tx.nonce}")
            return
        balance = self.balances[tx.token].get(tx.public, 0)
        if balance < tx.amount:
            logger.debug("balance not enough")
            return
        self.balances[tx.token][tx.public] = balance - tx.amount
        if tx.chain not in self.withdrawals:
            self.withdrawals[tx.chain] = {}
        if tx.public not in self.withdrawals[tx.chain]:
            self.withdrawals[tx.chain][tx.public] = []
        self.withdrawals[tx.chain][tx.public].append(tx)

    def get_order_book_update(self, pair: str):
        order_book_update = self.markets[pair].get_order_book_update()
        print(order_book_update)
        now = int(unix_time() * 1000)
        return {
            "e": "depthUpdate",  # Event type
            "E": now,  # Event time
            "T": now,  # Transaction time
            "s": pair.upper(),
            "U": order_book_update["U"],
            "u": order_book_update["u"],
            "pu": order_book_update["pu"],
            "b": [
                [p, q] for p, q in order_book_update["bids"].items()
            ],  # Bids to be updated
            "a": [
                [p, q] for p, q in order_book_update["asks"].items()
            ],  # Asks to be updated
        }

    def get_order_book(self, pair: str, limit: int):
        if pair not in self.markets:
            now = int(unix_time() * 1000)
            return {
                "lastUpdateId": 0,
                "E": now,  # Message output time
                "T": now,  # Transaction time
                "bids": [],
                "asks": [],
            }
        with self.markets[pair].order_book_lock:
            order_book = {
                "bids": deepcopy(self.markets[pair].bids_order_book),
                "asks": deepcopy(self.markets[pair].asks_order_book),
            }
        last_update_id = self.markets[pair].last_update_id
        now = int(unix_time() * 1000)
        return {
            "lastUpdateId": last_update_id,
            "E": now,  # Message output time
            "T": now,  # Transaction time
            "bids": [
                [p, q]
                for p, q in sorted(
                    order_book["bids"].items(), key=lambda x: x[0], reverse=True
                )[:limit]
            ],
            "asks": [
                [p, q]
                for p, q in sorted(order_book["asks"].items(), key=lambda x: x[0])[
                    :limit
                ]
            ],
        }

    def get_order_book_all(self):
        return [{}]

    def get_kline(self, pair: str) -> pd.DataFrame:
        if pair not in self.markets:
            kline = pd.DataFrame(
                columns=[
                    "OpenTime",
                    "CloseTime",
                    "Open",
                    "High",
                    "Low",
                    "Close",
                    "Volume",
                    "NumberOfTrades",
                ],
            ).set_index("OpenTime")
            return kline
        return self.markets[pair].kline


def get_current_1m_open_time():
    now = int(unix_time())
    open_time = now - now % 60
    return open_time * 1000


class Market:
    def __init__(self, base_token: str, quote_token: str, zex: Zex):
        self.amount_tolerance = 1e-8
        # bid price
        self.buy_orders: list[
            tuple[float, int, bytes]
        ] = []  # Max heap for buy orders, prices negated
        # ask price
        self.sell_orders: list[
            tuple[float, int, bytes]
        ] = []  # Min heap for sell orders
        heapq.heapify(self.buy_orders)
        heapq.heapify(self.sell_orders)
        self.order_book_lock = Lock()
        self.bids_order_book = {}
        self.asks_order_book = {}

        self._bids_order_book_update = {}
        self._asks_order_book_update = {}

        self.first_id = 0
        self.final_id = 0
        self.last_update_id = 0
        self.base_token = base_token
        self.quote_token = quote_token
        self.pair = base_token + quote_token
        self.kline = pd.DataFrame(
            columns=[
                "OpenTime",
                "CloseTime",
                "Open",
                "High",
                "Low",
                "Close",
                "Volume",
                "NumberOfTrades",
            ],
        ).set_index("OpenTime")

        self.zex = zex
        self.base_token_balances = zex.balances[base_token]
        self.quote_token_balances = zex.balances[quote_token]

    def get_order_book_update(self):
        data = {
            "bids": self._bids_order_book_update,
            "asks": self._asks_order_book_update,
        }
        self._bids_order_book_update = {}
        self._asks_order_book_update = {}

        data["U"] = self.first_id
        data["u"] = self.final_id
        data["pu"] = self.last_update_id
        self.first_id = self.final_id + 1
        self.last_update_id = self.final_id
        return data

    @line_profiler.profile
    def match_instantly(self, tx: bytes):
        return False

    @line_profiler.profile
    def place(self, tx: bytes):
        name = tx_utils.operation(tx)
        amount, price = tx_utils.amount(tx), tx_utils.price(tx)
        nonce = tx_utils.nonce(tx)
        public = tx_utils.public(tx)

        if self.zex.nonces[public] != nonce:
            logger.debug(
                f"invalid nonce: expected: {self.zex.nonces[public]} !=  got: {nonce}"
            )
            return
        self.zex.nonces[public] += 1
        index = tx_utils.index(tx)
        if name == BUY:
            required = amount * price
            balance = self.quote_token_balances.get(public, 0)
            if balance < required:
                logger.debug(
                    "balance not enough",
                    current_balance=balance,
                    quote_token=tx_utils.quote_token(tx),
                )
                return
            heapq.heappush(self.buy_orders, (-price, index, tx))
            with self.order_book_lock:
                a = 0
                if price not in self.bids_order_book:
                    a = amount
                    self.bids_order_book[price] = a
                else:
                    a = self.bids_order_book[price] + amount
                    self.bids_order_book[price] = a

                self._bids_order_book_update[price] = a
            self.quote_token_balances[public] = balance - required
        elif name == SELL:
            required = amount
            balance = self.base_token_balances.get(public, 0)
            if balance < required:
                logger.debug(
                    "balance not enough",
                    current_balance=balance,
                    base_token=tx_utils.base_token(tx),
                )
                return
            heapq.heappush(self.sell_orders, (price, index, tx))
            with self.order_book_lock:
                a = 0
                if price not in self.asks_order_book:
                    a = amount
                    self.asks_order_book[price] = a
                else:
                    a = self.asks_order_book[price] + amount
                    self.asks_order_book[price] = a

                self._asks_order_book_update[price] = a
            self.base_token_balances[public] = balance - required
        else:
            raise NotImplementedError(f"transaction type {name} is not supported")
        self.final_id += 1
        self.zex.amounts[tx] = amount
        self.zex.orders[public][tx] = True

    @line_profiler.profile
    def match(self, t):
        # Match orders while there are matching orders available
        if not self.buy_orders or not self.sell_orders:
            return False

        # Check if the top buy order matches the top sell order
        buy_price, buy_i, buy_order = self.buy_orders[0]
        sell_price, sell_i, sell_order = self.sell_orders[0]
        buy_price = -buy_price
        if buy_price < sell_price:
            return False

        # Determine the amount to trade
        trade_amount = min(self.zex.amounts[buy_order], self.zex.amounts[sell_order])

        # Update orders
        buy_public = tx_utils.public(buy_order)
        sell_public = tx_utils.public(sell_order)

        if self.zex.amounts[buy_order] > trade_amount:
            with self.order_book_lock:
                self.bids_order_book[buy_price] -= trade_amount
                self._bids_order_book_update[buy_price] = self.bids_order_book[
                    buy_price
                ]
            self.zex.amounts[buy_order] -= trade_amount
            self.final_id += 1
        else:
            heapq.heappop(self.buy_orders)
            with self.order_book_lock:
                if (
                    self.bids_order_book[buy_price] < trade_amount
                    or abs(self.bids_order_book[buy_price] - trade_amount)
                    < self.amount_tolerance
                ):
                    self._bids_order_book_update[buy_price] = 0
                    del self.bids_order_book[buy_price]
                else:
                    self.bids_order_book[buy_price] -= trade_amount
                    self._bids_order_book_update[buy_price] = self.bids_order_book[
                        buy_price
                    ]
            del self.zex.amounts[buy_order]
            del self.zex.orders[buy_public][buy_order]
            self.final_id += 1

        if self.zex.amounts[sell_order] > trade_amount:
            with self.order_book_lock:
                amount = self.asks_order_book[sell_price] - trade_amount
                self.asks_order_book[sell_price] = amount
                self._asks_order_book_update[sell_price] = amount
            self.zex.amounts[sell_order] -= trade_amount
            self.final_id += 1
        else:
            heapq.heappop(self.sell_orders)
            with self.order_book_lock:
                if (
                    self.asks_order_book[sell_price] < trade_amount
                    or abs(self.asks_order_book[sell_price] - trade_amount)
                    < self.amount_tolerance
                ):
                    self._asks_order_book_update[sell_price] = 0
                    del self.asks_order_book[sell_price]
                else:
                    amount = self.asks_order_book[sell_price] - trade_amount
                    self.asks_order_book[sell_price] = amount
                    self._asks_order_book_update[sell_price] = amount
            del self.zex.orders[sell_public][sell_order]
            del self.zex.amounts[sell_order]
            self.final_id += 1

        # This should be delegated to another process
        if not self.zex.benchmark_mode:
            current_candle_index = get_current_1m_open_time()
            if current_candle_index in self.kline.index:
                self.kline.iat[-1, 2] = max(sell_price, self.kline.iat[-1, 2])  # High
                self.kline.iat[-1, 3] = min(sell_price, self.kline.iat[-1, 3])  # Low
                self.kline.iat[-1, 4] = sell_price  # Close
                self.kline.iat[-1, 5] += trade_amount  # Volume
                self.kline.iat[-1, 6] += 1  # NumberOfTrades
            else:
                self.kline.loc[current_candle_index] = [
                    current_candle_index + 59999,  # CloseTime
                    sell_price,  # Open
                    sell_price,  # High
                    sell_price,  # Low
                    sell_price,  # Close
                    trade_amount,  # Volume
                    1,  # NumberOfTrades
                ]

        # Amount for canceled order is set to 0
        if trade_amount == 0:
            return False

        # Update users balances
        price = sell_price if sell_i < buy_i else buy_price
        base_balance = self.zex.balances[self.base_token].get(buy_public, 0)
        self.zex.balances[self.base_token][buy_public] = base_balance + trade_amount
        quote_balance = self.zex.balances[self.quote_token].get(sell_public, 0)
        self.zex.balances[self.quote_token][sell_public] = (
            quote_balance + price * trade_amount
        )

        # Add trades to users in-memory history
        buy_q = self.zex.trades[buy_public]
        sell_q = self.zex.trades[sell_public]
        buy_q.append((t, trade_amount, self.pair, BUY))
        sell_q.append((t, trade_amount, self.pair, SELL))

        # Remove trades older than TRADES_TTL from users in-memory history
        while len(buy_q) > 0 and t - buy_q[0][0] > TRADES_TTL:
            buy_q.popleft()
        while len(sell_q) > 0 and t - sell_q[0][0] > TRADES_TTL:
            sell_q.popleft()

        return True
