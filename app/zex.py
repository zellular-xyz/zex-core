from collections import deque
from collections.abc import Callable
from copy import deepcopy
from decimal import Decimal, FloatOperation, getcontext
from io import BytesIO
from threading import Lock
from time import time as unix_time
from typing import IO
import asyncio
import heapq
import struct

from loguru import logger
import pandas as pd

from .config import settings
from .models.transaction import (
    Deposit,
    WithdrawTransaction,
)
from .proto import zex_pb2
from .singleton import SingletonMeta

BTC_XMR_DEPOSIT, DEPOSIT, WITHDRAW, BUY, SELL, CANCEL, REGISTER = b"xdwbscr"
TRADES_TTL = 1000


def chunkify(lst, n_chunks):
    for i in range(0, len(lst), n_chunks):
        yield lst[i : i + n_chunks]


class Zex(metaclass=SingletonMeta):
    def __init__(
        self,
        kline_callback: Callable[[str, pd.DataFrame], None],
        depth_callback: Callable[[str, dict], None],
        state_dest: str,
        light_node: bool = False,
        benchmark_mode=False,
    ):
        c = getcontext()
        c.traps[FloatOperation] = True
        self.kline_callback = kline_callback
        self.depth_callback = depth_callback
        self.state_dest = state_dest
        self.light_node = light_node
        self.save_frequency = (
            settings.zex.state_save_frequency
        )  # save state every N transactions

        self.benchmark_mode = benchmark_mode

        self.last_tx_index = 0
        self.saved_state_index = 0
        self.save_state_tx_index_threshold = self.save_frequency
        self.markets: dict[str, Market] = {}
        self.assets: dict[str, dict[bytes, Decimal]] = {settings.zex.usdt_mainnet: {}}
        self.contract_to_token_id_on_chain_lookup: dict[str, dict[str, int]] = (
            settings.zex.verified_tokens_id
        )
        self.token_id_to_contract_on_chain_lookup: dict[str, dict[int, str]] = {
            chain: {
                token_id: contract_address for contract_address, token_id in val.items()
            }
            for chain, val in settings.zex.verified_tokens_id.items()
        }
        self.token_decimal_on_chain_lookup: dict[str, dict[str, int]] = (
            settings.zex.default_tokens_decimal
        )
        self.last_token_id: dict[str, int] = {
            chain: max(tokens.values())
            for chain, tokens in self.contract_to_token_id_on_chain_lookup.items()
        }
        self.amounts: dict[bytes, Decimal] = {}
        self.trades: dict[bytes, deque] = {}
        self.orders: dict[bytes, dict[bytes, bool]] = {}
        self.user_deposits: dict[bytes, list[Deposit]] = {}
        self.public_to_id_lookup: dict[bytes, int] = {}
        self.id_to_public_lookup: dict[int, bytes] = {}

        self.user_withdraws_on_chain: dict[
            str, dict[bytes, list[WithdrawTransaction]]
        ] = {}

        self.withdraws_on_chain: dict[str, list[WithdrawTransaction]] = {}
        self.deposits: dict[str, set[tuple[str, int]]] = {
            chain: set() for chain in settings.zex.chains
        }
        self.user_withdraw_nonce_on_chain: dict[str, dict[bytes, int]] = {
            k: {} for k in self.deposits.keys()
        }
        self.withdraw_nonce_on_chain: dict[str, int] = {
            k: 0 for k in self.deposits.keys()
        }
        self.nonces: dict[bytes, int] = {}
        self.pair_lookup: dict[bytes, tuple[str, str, str]] = {}

        self.last_user_id_lock = Lock()
        self.last_user_id = 0

        self.test_mode = not settings.zex.mainnet
        if self.test_mode:
            self.initialize_test_mode()

    def initialize_test_mode(self):
        from secp256k1 import PrivateKey

        client_private = (
            "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43eba0"
        )
        client_priv = PrivateKey(bytes(bytearray.fromhex(client_private)), raw=True)
        client_pub = client_priv.pubkey.serialize()
        self.register_pub(client_pub)

        private_seed = (
            "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebac"
        )
        private_seed_int = int.from_bytes(
            bytearray.fromhex(private_seed), byteorder="big"
        )

        tokens = {
            "BTC": [(1, "0x" + "0" * 40)],
            "POL": [
                (1, "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"),
                (2, "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"),
                (3, "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6"),
                (4, "0x53E0bca35eC356BD5ddDFebbD1Fc0fD03FaBad39"),
            ],
            "BSC": [
                (1, "0x55d398326f99059fF775485246999027B3197955"),
                (2, "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"),
                (3, "0x0555E30da8f98308EdB960aa94C0Db47230d2B9c"),
                (4, "0xF8A0BF9cF54Bb92F17374d9e9A321E6a111a51bD"),
            ],
            "OPT": [
                (1, "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58"),
                (2, "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85"),
                (3, "0x68f180fcCe6836688e9084f035309E29Bf0A2095"),
                (4, "0x350a791Bfc2C21F9Ed5d10980Dad2e2638ffa7f6"),
            ],
        }

        for i in range(110):
            bot_private_key = (private_seed_int + i).to_bytes(32, "big")
            bot_priv = PrivateKey(bot_private_key, raw=True)
            bot_pub = bot_priv.pubkey.serialize()
            self.register_pub(bot_pub)

            for chain, token_ids in tokens.items():
                for token_id, contract_address in token_ids:
                    if chain not in self.last_token_id:
                        self.last_token_id[chain] = 0
                    if chain not in self.contract_to_token_id_on_chain_lookup:
                        self.contract_to_token_id_on_chain_lookup[chain] = {}
                    if chain not in self.token_id_to_contract_on_chain_lookup:
                        self.token_id_to_contract_on_chain_lookup[chain] = {}
                    if (
                        contract_address
                        not in self.contract_to_token_id_on_chain_lookup[chain]
                    ):
                        self.contract_to_token_id_on_chain_lookup[chain][
                            contract_address
                        ] = token_id
                        self.token_id_to_contract_on_chain_lookup[chain][token_id] = (
                            contract_address
                        )
                        self.last_token_id[chain] += 1
                    if f"{chain}:{token_id}" not in self.assets:
                        self.assets[f"{chain}:{token_id}"] = {}
                    self.assets[f"{chain}:{token_id}"][bot_pub] = Decimal("100")
                    self.assets[f"{chain}:{token_id}"][client_pub] = Decimal("200")

    def to_protobuf(self) -> zex_pb2.ZexState:
        state = zex_pb2.ZexState()

        state.last_tx_index = self.last_tx_index

        for pair, market in self.markets.items():
            pb_market = state.markets[pair]
            pb_market.base_token = market.base_token
            pb_market.quote_token = market.quote_token
            for order in market.buy_orders:
                pb_order = pb_market.buy_orders.add()
                pb_order.price = str(-order[0])  # Negate price for buy orders
                pb_order.index = order[1]
                pb_order.tx = order[2]
            for order in market.sell_orders:
                pb_order = pb_market.sell_orders.add()
                pb_order.price = str(order[0])
                pb_order.index = order[1]
                pb_order.tx = order[2]
            for price, amount in market.bids_order_book.items():
                entry = pb_market.bids_order_book.add()
                entry.price = str(price)
                entry.amount = str(amount)
            for price, amount in market.asks_order_book.items():
                entry = pb_market.asks_order_book.add()
                entry.price = str(price)
                entry.amount = str(amount)
            pb_market.first_id = market.first_id
            pb_market.final_id = market.final_id
            pb_market.last_update_id = market.last_update_id

            # TODO: find a better solution since loading pickle is dangerous
            buffer = BytesIO()
            market.kline.to_pickle(buffer)
            pb_market.kline = buffer.getvalue()

        for token, balances in self.assets.items():
            pb_balance = state.balances[token]
            for public, amount in balances.items():
                entry = pb_balance.balances.add()
                entry.public_key = public
                entry.amount = str(amount)

        for tx, amount in self.amounts.items():
            entry = state.amounts.add()
            entry.tx = tx
            entry.amount = str(amount)

        for public, trades in self.trades.items():
            entry = state.trades.add()
            entry.public_key = public
            for trade in trades:
                pb_trade = entry.trades.add()
                (
                    pb_trade.t,
                    pb_trade.amount,
                    pb_trade.pair,
                    pb_trade.order_type,
                    pb_trade.order,
                ) = trade[0], str(trade[1]), trade[2], trade[3], trade[4]

        for public, orders in self.orders.items():
            entry = state.orders.add()
            entry.public_key = public
            entry.orders.extend(orders.keys())

        for chain, withdraws in self.withdraws_on_chain.items():
            pb_withdraws = state.withdraws_on_chain[chain]
            entry = pb_withdraws.withdraws.add()
            entry.raw_txs.extend([w.raw_tx for w in withdraws])

        for chain, withdraws in self.user_withdraws_on_chain.items():
            pb_withdraws = state.user_withdraws_on_chain[chain]
            for public, withdraw_list in withdraws.items():
                entry = pb_withdraws.withdraws.add()
                entry.public_key = public
                entry.raw_txs.extend([w.raw_tx for w in withdraw_list])

        for chain, withdraw_nonces in self.user_withdraw_nonce_on_chain.items():
            pb_withdraw_nonces = state.user_withdraw_nonce_on_chain[chain]
            for public, nonce in withdraw_nonces.items():
                entry = pb_withdraw_nonces.nonces.add()
                entry.public_key = public
                entry.nonce = nonce

        state.withdraw_nonce_on_chain.update(self.withdraw_nonce_on_chain)

        for chain, deposits in self.deposits.items():
            pb_deposits = state.deposits[chain]
            for deposit in deposits:
                entry = pb_deposits.deposits.add()
                entry.tx_hash = deposit[0]
                entry.vout = deposit[1]

        for public, nonce in self.nonces.items():
            entry = state.nonces.add()
            entry.public_key = public
            entry.nonce = nonce

        for public, deposits in self.user_deposits.items():
            entry = state.user_deposits.add()
            entry.public_key = public
            for deposit in deposits:
                pb_deposit = entry.deposits.add()
                pb_deposit.token = deposit.token
                pb_deposit.amount = str(deposit.amount)
                pb_deposit.time = deposit.time

        for key, (base_token, quote_token, pair) in self.pair_lookup.items():
            entry = state.pair_lookup.add()
            entry.key = key
            entry.base_token = base_token
            entry.quote_token = quote_token
            entry.pair = pair

        for public, user_id in self.public_to_id_lookup.items():
            entry = state.public_to_id_lookup.add()
            entry.public_key = public
            entry.user_id = user_id
        state.id_to_public_lookup.update(self.id_to_public_lookup)

        for chain, details in self.contract_to_token_id_on_chain_lookup.items():
            entry = state.contract_to_token_id_on_chain_lookup.add()
            entry.chain = chain
            entry.contract_to_id.update(details)
        for chain, details in self.token_id_to_contract_on_chain_lookup.items():
            entry = state.token_id_to_contract_on_chain_lookup.add()
            entry.chain = chain
            entry.id_to_contract.update(details)
        for chain, details in self.token_decimal_on_chain_lookup.items():
            entry = state.token_decimal_on_chain_lookup.add()
            entry.chain = chain
            entry.contract_to_decimal.update(details)
        state.last_token_id_on_chain.update(self.last_token_id)

        return state

    @classmethod
    def from_protobuf(
        cls,
        pb_state: zex_pb2.ZexState,
        kline_callback: Callable[[str, pd.DataFrame], None],
        depth_callback: Callable[[str, dict], None],
        state_dest: str,
        light_node: bool,
    ):
        zex = cls(
            kline_callback,
            depth_callback,
            state_dest,
            light_node,
        )

        zex.last_tx_index = pb_state.last_tx_index

        zex.assets = {
            token: {e.public_key: Decimal(e.amount) for e in pb_balance.balances}
            for token, pb_balance in pb_state.balances.items()
        }
        for pair, pb_market in pb_state.markets.items():
            market = Market(pb_market.base_token, pb_market.quote_token, zex)
            market.buy_orders = [
                (-Decimal(o.price), o.index, o.tx) for o in pb_market.buy_orders
            ]
            market.sell_orders = [
                (Decimal(o.price), o.index, o.tx) for o in pb_market.sell_orders
            ]

            market.bids_order_book = {
                Decimal(e.price): Decimal(e.amount) for e in pb_market.bids_order_book
            }
            market.asks_order_book = {
                Decimal(e.price): Decimal(e.amount) for e in pb_market.asks_order_book
            }

            market.first_id = pb_market.first_id
            market.final_id = pb_market.final_id
            market.last_update_id = pb_market.last_update_id
            market.kline = pd.read_pickle(BytesIO(pb_market.kline))
            zex.markets[pair] = market

        zex.amounts = {e.tx: Decimal(e.amount) for e in pb_state.amounts}
        zex.trades = {
            e.public_key: deque(
                (
                    trade.t,
                    Decimal(trade.amount),
                    trade.pair,
                    trade.order_type,
                    trade.order,
                )
                for trade in e.trades
            )
            for e in pb_state.trades
        }
        zex.orders = {
            e.public_key: {order: True for order in e.orders} for e in pb_state.orders
        }

        zex.withdraws_on_chain = {}
        for chain, pb_withdraws in pb_state.withdraws_on_chain.items():
            zex.withdraws_on_chain[chain] = {}
            for entry in pb_withdraws.withdraws:
                zex.withdraws_on_chain[chain] = [
                    WithdrawTransaction.from_tx(raw_tx) for raw_tx in entry.raw_txs
                ]
        zex.withdraw_nonce_on_chain = dict(pb_state.withdraw_nonce_on_chain)

        zex.user_withdraws_on_chain = {}
        for chain, pb_withdraws in pb_state.user_withdraws_on_chain.items():
            zex.user_withdraws_on_chain[chain] = {}
            for entry in pb_withdraws.withdraws:
                zex.user_withdraws_on_chain[chain][entry.public_key] = [
                    WithdrawTransaction.from_tx(raw_tx) for raw_tx in entry.raw_txs
                ]

        zex.user_withdraw_nonce_on_chain = {}
        for chain, pb_withdraw_nonces in pb_state.user_withdraw_nonce_on_chain.items():
            zex.user_withdraw_nonce_on_chain[chain] = {
                entry.public_key: entry.nonce for entry in pb_withdraw_nonces.nonces
            }

        zex.deposits = {
            chain: {(item.tx_hash, item.vout) for item in e.deposits}
            for chain, e in pb_state.deposits.items()
        }

        zex.nonces = {e.public_key: e.nonce for e in pb_state.nonces}

        zex.user_deposits = {
            e.public_key: [
                Deposit(
                    token=pb_deposit.token,
                    amount=Decimal(pb_deposit.amount),
                    time=pb_deposit.time,
                )
                for pb_deposit in e.deposits
            ]
            for e in pb_state.user_deposits
        }

        zex.pair_lookup = {
            e.key: (e.base_token, e.quote_token, e.pair) for e in pb_state.pair_lookup
        }

        zex.public_to_id_lookup = {
            entry.public_key: entry.user_id for entry in pb_state.public_to_id_lookup
        }
        zex.id_to_public_lookup = dict(pb_state.id_to_public_lookup)

        zex.last_user_id = (
            max(zex.public_to_id_lookup.values()) if zex.public_to_id_lookup else 0
        )

        zex.contract_to_token_id_on_chain_lookup = {
            entry.chain: dict(entry.contract_to_id)
            for entry in pb_state.contract_to_token_id_on_chain_lookup
        }
        zex.token_id_to_contract_on_chain_lookup = {
            entry.chain: dict(entry.id_to_contract)
            for entry in pb_state.token_id_to_contract_on_chain_lookup
        }
        zex.token_decimal_on_chain_lookup = {
            entry.chain: dict(entry.contract_to_decimal)
            for entry in pb_state.token_decimal_on_chain_lookup
        }
        zex.last_token_id = dict(pb_state.last_token_id_on_chain)

        return zex

    def save_state(self):
        state = self.to_protobuf()
        with open(self.state_dest, "wb") as f:
            f.write(state.SerializeToString())

    @classmethod
    def load_state(
        cls,
        data: IO[bytes],
        kline_callback: Callable[[str, pd.DataFrame], None],
        depth_callback: Callable[[str, dict], None],
        state_dest: str,
        light_node: bool,
    ):
        pb_state = zex_pb2.ZexState()
        pb_state.ParseFromString(data.read())
        return cls.from_protobuf(
            pb_state,
            kline_callback,
            depth_callback,
            state_dest,
            light_node,
        )

    def process(self, txs: list[bytes], last_tx_index):
        modified_pairs = set()
        for tx in txs:
            if not tx:
                continue
            v, name = tx[0:2]
            if v != 1:
                logger.error("invalid version", version=v)
                continue

            if name == DEPOSIT or name == BTC_XMR_DEPOSIT:
                self.deposit(tx)
            elif name == WITHDRAW:
                tx = WithdrawTransaction.from_tx(tx)
                self.withdraw(tx)
            elif name in (BUY, SELL):
                base_token, quote_token, pair = self._get_tx_pair(tx)

                if pair not in self.markets:
                    if base_token not in self.assets:
                        self.assets[base_token] = {}
                    if quote_token not in self.assets:
                        self.assets[quote_token] = {}
                    self.markets[pair] = Market(base_token, quote_token, self)
                t = struct.unpack(">I", tx[32:36])[0]
                # fast route check for instant match
                logger.debug(
                    "executing tx base: {base_token}, quote: {quote_token}",
                    base_token=base_token,
                    quote_token=quote_token,
                )

                _, _, _, nonce, public, _ = _parse_transaction(tx)
                if not self.validate_nonce(public, nonce):
                    continue

                if self.markets[pair].match_instantly(tx, t):
                    modified_pairs.add(pair)
                    continue
                ok = self.markets[pair].place(tx)
                if not ok:
                    continue

                modified_pairs.add(pair)

            elif name == CANCEL:
                base_token, quote_token, pair = self._get_tx_pair(tx[1:])
                success = self.markets[pair].cancel(tx)
                if success:
                    modified_pairs.add(pair)
            elif name == REGISTER:
                self.register_pub(public=tx[2:35])
            else:
                raise ValueError(f"invalid transaction name {name}")
        for pair in modified_pairs:
            if self.benchmark_mode:
                break
            asyncio.create_task(self.kline_callback(pair, self.get_kline(pair)))
            asyncio.create_task(
                self.depth_callback(pair, self.get_order_book_update(pair))
            )
        self.last_tx_index = last_tx_index

        if self.saved_state_index + self.save_frequency < self.last_tx_index:
            self.saved_state_index = self.last_tx_index
            self.save_state()

    def deposit(self, tx: bytes):
        header_format = ">xx 3s H"
        header_size = struct.calcsize(header_format)
        chain, count = struct.unpack(header_format, tx[:header_size])
        chain = chain.upper().decode()

        if chain not in self.contract_to_token_id_on_chain_lookup:
            self.contract_to_token_id_on_chain_lookup[chain] = {}
        if chain not in self.last_token_id:
            self.last_token_id[chain] = 0

        deposit_format = ">66s 42s 32s B I Q B"
        deposit_size = struct.calcsize(deposit_format)

        deposits = list(
            chunkify(tx[header_size : header_size + deposit_size * count], deposit_size)
        )
        for chunk in deposits:
            tx_hash, token_contract, amount, decimal, t, user_id, vout = struct.unpack(
                deposit_format, chunk[:deposit_size]
            )
            amount = int.from_bytes(amount, byteorder="big")
            tx_hash = tx_hash.decode()

            if user_id < 1:
                logger.critical(
                    f"invalid user id: {user_id}, tx_hash: {tx_hash}, vout: {vout}, token_contract: {token_contract}, amount: {amount}, decimal: {decimal}"
                )
                continue
            if self.last_user_id < user_id:
                logger.error(
                    f"deposit for missing user: {user_id}, tx_hash: {tx_hash}, vout: {vout}, token_contract: {token_contract}, amount: {amount}, decimal: {decimal}"
                )
                continue

            if chain not in self.deposits:
                self.deposits[chain] = set()

            if (tx_hash, vout) in self.deposits[chain]:
                logger.error(
                    f"chain: {chain}, tx_hash: {tx_hash}, vout: {vout} has already been deposited"
                )
                continue
            self.deposits[chain].add((tx_hash, vout))

            amount = Decimal(str(amount))
            if chain not in self.token_decimal_on_chain_lookup:
                self.token_decimal_on_chain_lookup[chain] = {}
            if chain not in self.token_id_to_contract_on_chain_lookup:
                self.token_id_to_contract_on_chain_lookup[chain] = {}

            token_contract = token_contract.decode()
            if token_contract not in self.token_decimal_on_chain_lookup[chain]:
                self.token_decimal_on_chain_lookup[chain][token_contract] = decimal

            if self.token_decimal_on_chain_lookup[chain][token_contract] != decimal:
                logger.warning(
                    f"decimal for contract {token_contract} changed "
                    f"from {self.token_decimal_on_chain_lookup[chain][token_contract]} to {decimal}"
                )
                self.token_decimal_on_chain_lookup[chain][token_contract] = decimal
            amount /= 10 ** Decimal(decimal)

            if token_contract not in self.contract_to_token_id_on_chain_lookup[chain]:
                self.last_token_id[chain] += 1
                token_id = self.last_token_id[chain]
                self.contract_to_token_id_on_chain_lookup[chain][token_contract] = (
                    token_id
                )
                self.token_id_to_contract_on_chain_lookup[chain][token_id] = (
                    token_contract
                )
            else:
                token_id = self.contract_to_token_id_on_chain_lookup[chain][
                    token_contract
                ]
            token = f"{chain}:{token_id}"
            public = self.id_to_public_lookup[user_id]

            if token not in self.assets:
                self.assets[token] = {}
            if public not in self.assets[token]:
                self.assets[token][public] = Decimal("0")

            pair = f"{token}-{settings.zex.usdt_mainnet}"
            if pair not in self.markets:
                self.markets[pair] = Market(token, settings.zex.usdt_mainnet, self)

            if public not in self.user_deposits:
                self.user_deposits[public] = []

            self.user_deposits[public].append(
                Deposit(
                    token=token,
                    amount=amount,
                    time=t,
                )
            )
            self.assets[token][public] += amount
            logger.info(
                f"deposit on chain: {chain}, token: {token}, amount: {amount} for user: {public}, tx_hash: {tx_hash}, new balance: {self.assets[token][public]}"
            )

            if public not in self.trades:
                self.trades[public] = deque()
            if public not in self.orders:
                self.orders[public] = {}
            if public not in self.nonces:
                self.nonces[public] = 0

    def withdraw(self, tx: WithdrawTransaction):
        if tx.amount <= 0:
            logger.debug(f"invalid amount: {tx.amount}")
            return

        if tx.chain not in self.user_withdraw_nonce_on_chain:
            logger.debug(f"invalid chain: {self.nonces[tx.public]} != {tx.nonce}")
            return

        if self.user_withdraw_nonce_on_chain[tx.chain].get(tx.public, 0) != tx.nonce:
            logger.debug(f"invalid nonce: {self.nonces[tx.public]} != {tx.nonce}")
            return

        balance = self.assets[tx.internal_token].get(tx.public, Decimal("0"))
        if balance < tx.amount:
            logger.debug("balance not enough")
            return

        if tx.public not in self.user_withdraw_nonce_on_chain[tx.chain]:
            self.user_withdraw_nonce_on_chain[tx.chain][tx.public] = 0

        self.assets[tx.internal_token][tx.public] = balance - tx.amount

        if tx.chain not in self.user_withdraws_on_chain:
            self.user_withdraws_on_chain[tx.chain] = {}
        if tx.public not in self.user_withdraws_on_chain[tx.chain]:
            self.user_withdraws_on_chain[tx.chain][tx.public] = []
        self.user_withdraws_on_chain[tx.chain][tx.public].append(tx)

        if tx.chain not in self.withdraw_nonce_on_chain:
            self.withdraw_nonce_on_chain[tx.chain] = 0
        self.withdraw_nonce_on_chain[tx.chain] += 1

        self.user_withdraw_nonce_on_chain[tx.chain][tx.public] += 1
        if tx.chain not in self.withdraws_on_chain:
            self.withdraws_on_chain[tx.chain] = []
        self.withdraws_on_chain[tx.chain].append(tx)

    def validate_nonce(self, public: bytes, nonce: int) -> bool:
        if self.nonces[public] != nonce:
            logger.debug(
                "Invalid nonce: expected {expected_nonce}, got {nonce}",
                expected_nonce=self.nonces[public],
                nonce=nonce,
            )
            return False
        self.nonces[public] += 1
        return True

    def get_order_book_update(self, pair: str):
        order_book_update = self.markets[pair].get_order_book_update()
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
                [float(p), float(q)] for p, q in order_book_update["bids"].items()
            ],  # Bids to be updated
            "a": [
                [float(p), float(q)] for p, q in order_book_update["asks"].items()
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

    def _get_tx_pair(self, tx: bytes):
        if tx[2:16] in self.pair_lookup:
            return self.pair_lookup[tx[2:16]]
        base_token = f"{tx[2:5].upper().decode()}:{struct.unpack('>I', tx[5:9])[0]}"
        quote_token = f"{tx[9:12].upper().decode()}:{struct.unpack('>I', tx[12:16])[0]}"
        pair = f"{base_token}-{quote_token}"
        self.pair_lookup[tx[2:16]] = (base_token, quote_token, pair)
        return base_token, quote_token, pair

    def register_pub(self, public: bytes):
        if public not in self.public_to_id_lookup:
            with self.last_user_id_lock:
                self.last_user_id += 1
                self.public_to_id_lookup[public] = self.last_user_id
                self.id_to_public_lookup[self.last_user_id] = public

        if public not in self.trades:
            self.trades[public] = deque()
        if public not in self.orders:
            self.orders[public] = {}
        if public not in self.user_deposits:
            self.user_deposits[public] = []
        if public not in self.nonces:
            self.nonces[public] = 0


def get_current_1m_open_time():
    now = int(unix_time())
    open_time = now - now % 60
    return open_time * 1000


def _parse_transaction(tx: bytes) -> tuple[int, Decimal, Decimal, int, bytes, int]:
    operation, amount, price, nonce, public, index = struct.unpack(
        ">xB14xdd4xI33s64xQ", tx
    )
    return operation, Decimal(str(amount)), Decimal(str(price)), nonce, public, index


class Market:
    def __init__(self, base_token: str, quote_token: str, zex: Zex):
        self.base_token = base_token
        self.quote_token = quote_token
        self.pair = f"{base_token}-{quote_token}"
        self.zex = zex

        self.buy_orders: list[tuple[Decimal, int, bytes]] = []
        self.sell_orders: list[tuple[Decimal, int, bytes]] = []
        self.order_book_lock = Lock()
        self.bids_order_book: dict[Decimal, Decimal] = {}
        self.asks_order_book: dict[Decimal, Decimal] = {}
        self._order_book_updates = {"bids": {}, "asks": {}}

        self.first_id = 0
        self.final_id = 0
        self.last_update_id = 0

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
            ]
        ).set_index("OpenTime")

        self.base_token_balances = zex.assets[base_token]
        self.quote_token_balances = zex.assets[quote_token]

    def get_order_book_update(self):
        with self.order_book_lock:
            data = {
                "bids": self._order_book_updates["bids"],
                "asks": self._order_book_updates["asks"],
                "U": self.first_id,
                "u": self.final_id,
                "pu": self.last_update_id,
            }
            self._order_book_updates = {"bids": {}, "asks": {}}
            self.first_id = self.final_id + 1
            self.last_update_id = self.final_id
        return data

    def match_instantly(self, tx: bytes, t: int) -> bool:
        operation, amount, price, _, public, index = _parse_transaction(tx)
        if price <= 0 or amount <= 0:
            return False

        if operation == BUY:
            if not self.sell_orders:
                return False
            best_sell_price, _, _ = self.sell_orders[0]
            if price >= best_sell_price:
                return self._execute_instant_buy(public, amount, price, index, tx, t)
        elif operation == SELL:
            if not self.buy_orders:
                return False
            best_buy_price = -self.buy_orders[0][
                0
            ]  # Negate because buy prices are stored negatively
            if price <= best_buy_price:
                return self._execute_instant_sell(public, amount, price, index, tx, t)
        else:
            raise ValueError(f"Unsupported transaction type: {operation}")

        return False

    def _execute_instant_buy(
        self,
        public: bytes,
        amount: Decimal,
        price: Decimal,
        index: int,
        tx: bytes,
        t: int,
    ) -> bool:
        required = amount * price
        balance = self.quote_token_balances.get(public, 0)
        if balance < required:
            logger.debug(
                "Insufficient balance, current balance: {current_balance}, "
                "side: buy, base token: {base_token}, quote token: {quote_token}",
                current_balance=balance,
                base_token=self.base_token,
                quote_token=self.quote_token,
            )
            return False

        # Execute the trade
        while amount > 0 and self.sell_orders and self.sell_orders[0][0] <= price:
            sell_price, _, sell_order = self.sell_orders[0]
            trade_amount = min(amount, self.zex.amounts[sell_order])
            self._execute_trade(tx, sell_order, trade_amount, sell_price, t)

            sell_public = sell_order[40:73]
            self._update_sell_order(sell_order, trade_amount, sell_price, sell_public)
            self._update_balances(public, sell_public, trade_amount, sell_price)
            self.quote_token_balances[public] -= trade_amount * sell_price

            amount -= trade_amount

        if amount > 0:
            # Add remaining amount to buy orders
            heapq.heappush(self.buy_orders, (-price, index, tx))
            self.zex.amounts[tx] = amount
            self.zex.orders[public][tx] = True
            with self.order_book_lock:
                if price in self.bids_order_book:
                    self.bids_order_book[price] += amount
                else:
                    self.bids_order_book[price] = amount
                self._order_book_updates["bids"][price] = self.bids_order_book[price]
            self.quote_token_balances[public] -= amount * price

        return True

    def _execute_instant_sell(
        self,
        public: bytes,
        amount: Decimal,
        price: Decimal,
        index: int,
        tx: bytes,
        t: int,
    ) -> bool:
        balance = self.base_token_balances.get(public, 0)
        if balance < amount:
            logger.debug(
                "Insufficient balance, current balance: {current_balance}, "
                "side: sell, base token: {base_token}, quote token: {quote_token}",
                current_balance=balance,
                base_token=self.base_token,
                quote_token=self.quote_token,
            )
            return False
        # Execute the trade
        while amount > 0 and self.buy_orders and -self.buy_orders[0][0] >= price:
            buy_price, _, buy_order = self.buy_orders[0]
            buy_price = -buy_price  # Negate because buy prices are stored negatively
            trade_amount = min(amount, self.zex.amounts[buy_order])
            self._execute_trade(buy_order, tx, trade_amount, buy_price, t)

            buy_public = buy_order[40:73]
            self._update_buy_order(buy_order, trade_amount, buy_price, buy_public)
            self._update_balances(buy_public, public, trade_amount, buy_price)
            self.base_token_balances[public] -= trade_amount

            amount -= trade_amount

        if amount > 0:
            # Add remaining amount to sell orders
            heapq.heappush(self.sell_orders, (price, index, tx))
            self.zex.amounts[tx] = amount
            self.zex.orders[public][tx] = True
            with self.order_book_lock:
                if price in self.asks_order_book:
                    self.asks_order_book[price] += amount
                else:
                    self.asks_order_book[price] = amount
                self._order_book_updates["asks"][price] = self.asks_order_book[price]
            self.base_token_balances[public] -= amount
        return True

    def _execute_trade(
        self,
        buy_order: bytes,
        sell_order: bytes,
        trade_amount: Decimal,
        price: Decimal,
        t: int,
    ):
        buy_public = buy_order[40:73]
        sell_public = sell_order[40:73]

        self._record_trade(
            buy_order, sell_order, buy_public, sell_public, trade_amount, t
        )

        if not self.zex.benchmark_mode and not self.zex.light_node:
            self._update_kline(float(price), float(trade_amount))

        self.final_id += 1

    def place(self, tx: bytes) -> bool:
        operation, amount, price, _, public, index = _parse_transaction(tx)
        if price < 0 or amount < 0:
            return False

        if operation == BUY:
            side = "buy"
            order_book_update_key = "bids"
            order_book = self.bids_order_book
            orders_heap = self.buy_orders
            heap_item = (-price, index, tx)

            balances_dict = self.quote_token_balances
            balance = Decimal(str(balances_dict.get(public, 0)))

            required = amount * price
        elif operation == SELL:
            side = "sell"
            order_book_update_key = "asks"
            order_book = self.asks_order_book
            orders_heap = self.sell_orders
            heap_item = (price, index, tx)

            balances_dict = self.base_token_balances
            balance = Decimal(str(balances_dict.get(public, 0)))

            required = amount
        else:
            raise ValueError(f"Unsupported transaction type: {operation}")

        if balance < required:
            logger.debug(
                "Insufficient balance, current balance: {current_balance}, "
                "side: {side}, base token: {base_token}, quote token: {quote_token}",
                current_balance=float(balance),
                side=side,
                base_token=self.base_token,
                quote_token=self.quote_token,
            )
            return False

        heapq.heappush(orders_heap, heap_item)
        with self.order_book_lock:
            if price in order_book:
                order_book[price] += amount
            else:
                order_book[price] = amount
            self._order_book_updates[order_book_update_key][price] = order_book[price]

        balances_dict[public] = balance - required

        self.final_id += 1
        self.zex.amounts[tx] = amount
        self.zex.orders[public][tx] = True
        return True

    def cancel(self, tx: bytes) -> bool:
        public = tx[41:74]
        order_slice = tx[2:41]
        for order in self.zex.orders[public]:
            if order_slice not in order:
                continue
            operation, _, price, _, public, index = _parse_transaction(order)
            amount = self.zex.amounts.pop(order)
            del self.zex.orders[public][order]
            if operation == BUY:
                self.quote_token_balances[public] += amount * price
                self.buy_orders.remove((-price, index, order))
                heapq.heapify(self.buy_orders)
                with self.order_book_lock:
                    if amount >= self.bids_order_book[price]:
                        del self.bids_order_book[price]
                        self._order_book_updates["bids"][price] = 0
                    else:
                        self.bids_order_book[price] -= amount
                        self._order_book_updates["bids"][price] = self.bids_order_book[
                            price
                        ]

            else:
                self.base_token_balances[public] += amount
                self.sell_orders.remove((price, index, order))
                heapq.heapify(self.sell_orders)
                with self.order_book_lock:
                    if amount >= self.asks_order_book[price]:
                        del self.asks_order_book[price]
                        self._order_book_updates["asks"][price] = 0
                    else:
                        self.asks_order_book[price] -= amount
                        self._order_book_updates["asks"][price] = self.asks_order_book[
                            price
                        ]
            self.final_id += 1
            return True
        else:
            return False

    def get_last_price(self):
        if len(self.kline) == 0:
            return 0
        return self.kline["Close"].iloc[-1]

    def get_price_change_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span >= ms_in_24h:
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            return (
                self.kline["Close"].iloc[-1] - self.kline["Open"].iloc[prev_24h_index]
            )
        return self.kline["Close"].iloc[-1] - self.kline["Open"].iloc[0]

    def get_price_change_24h_percent(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span >= ms_in_24h:
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            open_price = self.kline["Open"].iloc[-prev_24h_index]
            close_price = self.kline["Close"].iloc[-1]
            if open_price == 0:
                return 0
            return ((close_price - open_price) / open_price) * 100

        close_price = self.kline["Close"].iloc[-1]
        open_price = self.kline["Open"].iloc[0]
        if open_price == 0:
            return 0
        return ((close_price - open_price) / open_price) * 100

    def get_price_change_7d_percent(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_7d = 7 * 24 * 60 * 60 * 1000
        if total_span > ms_in_7d:
            target_time = self.kline.index[-1] - 7 * 24 * 60 * 60 * 1000
            prev_7d_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            open_price = self.kline["Open"].iloc[prev_7d_index]
            close_price = self.kline["Close"].iloc[-1]
            return (close_price - open_price) / open_price
        return self.kline["Close"].iloc[-1] - self.kline["Open"].iloc[0]

    def get_volume_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span > ms_in_24h:
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            return self.kline["Volume"].iloc[prev_24h_index:].sum()
        return self.kline["Volume"].sum()

    def get_high_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span > ms_in_24h:
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            return self.kline["High"].iloc[prev_24h_index:].max()
        return self.kline["High"].max()

    def get_low_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span > ms_in_24h:
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            return self.kline["Low"].iloc[prev_24h_index:].min()
        return self.kline["Low"].min()

    def _update_buy_order(
        self,
        buy_order: bytes,
        trade_amount: Decimal,
        buy_price: Decimal,
        buy_public: bytes,
    ):
        with self.order_book_lock:
            if self.zex.amounts[buy_order] > trade_amount:
                self.bids_order_book[buy_price] -= trade_amount
                self._order_book_updates["bids"][buy_price] = self.bids_order_book[
                    buy_price
                ]
                self.zex.amounts[buy_order] -= trade_amount
                self.final_id += 1
            else:
                heapq.heappop(self.buy_orders)
                self._remove_from_order_book("bids", buy_price, trade_amount)
                del self.zex.amounts[buy_order]
                del self.zex.orders[buy_public][buy_order]
                self.final_id += 1

    def _update_sell_order(
        self,
        sell_order: bytes,
        trade_amount: Decimal,
        sell_price: Decimal,
        sell_public: bytes,
    ):
        with self.order_book_lock:
            if self.zex.amounts[sell_order] > trade_amount:
                self.asks_order_book[sell_price] -= trade_amount
                self._order_book_updates["asks"][sell_price] = self.asks_order_book[
                    sell_price
                ]
                self.zex.amounts[sell_order] -= trade_amount
                self.final_id += 1
            else:
                heapq.heappop(self.sell_orders)
                self._remove_from_order_book("asks", sell_price, trade_amount)
                del self.zex.amounts[sell_order]
                del self.zex.orders[sell_public][sell_order]
                self.final_id += 1

    def _remove_from_order_book(self, book_type: str, price: Decimal, amount: Decimal):
        order_book = (
            self.bids_order_book if book_type == "bids" else self.asks_order_book
        )
        if order_book[price] <= amount:
            self._order_book_updates[book_type][price] = 0
            del order_book[price]
        else:
            order_book[price] -= amount
            self._order_book_updates[book_type][price] = order_book[price]

    def _update_balances(
        self,
        buy_public: bytes,
        sell_public: bytes,
        trade_amount: Decimal,
        price: Decimal,
    ):
        self.base_token_balances[buy_public] = (
            self.base_token_balances.get(buy_public, 0) + trade_amount
        )

        self.quote_token_balances[sell_public] = (
            self.quote_token_balances.get(sell_public, 0) + price * trade_amount
        )

    def _record_trade(
        self,
        buy_order: bytes,
        sell_order: bytes,
        buy_public: bytes,
        sell_public: bytes,
        trade_amount: Decimal,
        t: int,
    ):
        for public, order_type in [(buy_public, BUY), (sell_public, SELL)]:
            trade = (
                t,
                trade_amount,
                self.pair,
                order_type,
                buy_order if order_type == BUY else sell_order,
            )
            self.zex.trades[public].append(trade)
            self._prune_old_trades(public, t)

    def _prune_old_trades(self, public: bytes, current_time: int):
        trades = self.zex.trades[public]
        while trades and current_time - trades[0][0] > TRADES_TTL:
            trades.popleft()

    def _update_kline(self, price: float, trade_amount: float):
        current_candle_index = get_current_1m_open_time()
        if len(self.kline.index) != 0 and current_candle_index == self.kline.index[-1]:
            self.kline.iat[-1, 2] = max(price, self.kline.iat[-1, 2])  # High
            self.kline.iat[-1, 3] = min(price, self.kline.iat[-1, 3])  # Low
            self.kline.iat[-1, 4] = price  # Close
            self.kline.iat[-1, 5] += trade_amount  # Volume
            self.kline.iat[-1, 6] += 1  # NumberOfTrades
        else:
            self.kline.loc[current_candle_index] = [
                current_candle_index + 59999,  # CloseTime
                price,  # Open
                price,  # High
                price,  # Low
                price,  # Close
                trade_amount,  # Volume
                1,  # Volume, NumberOfTrades
            ]
