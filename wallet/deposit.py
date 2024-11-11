from asyncio import subprocess
from pprint import pprint
from struct import pack
import asyncio
import hashlib
import json
import os
import signal

from bitcoinrpc import BitcoinRPC, RPCError
from bitcoinutils.keys import P2trAddress, PublicKey
from bitcoinutils.setup import setup
from bitcoinutils.utils import tweak_taproot_pubkey
from secp256k1 import PrivateKey
import httpx
import yaml

setup("mainnet")


IS_RUNNING = True

TOKENS = {
    "BTC": {
        # 0: 1,  # value is already in BTC
        "0x" + "0" * 40: 8,
    },
    "XMR": {
        "0x" + "0" * 40: 12,
    },
}


def create_tx(
    deposits, chain: str, from_block, to_block, timestamp, monitor: PrivateKey
):
    header_format = ">B B 3s Q Q H"
    version = 1
    chain: bytes = chain.encode()

    tx = pack(
        header_format,
        version,
        int.from_bytes(b"x", "big"),
        chain,
        from_block,
        to_block,
        len(deposits),
    )
    for deposit in deposits:
        user_id = deposit["user_id"]
        token_id = "0x" + "0" * 40
        amount = deposit["amount"]
        decimal = int(TOKENS[chain.decode()].get(token_id, 18))

        print(token_id, amount, decimal, timestamp)

        tx += pack(
            ">42s Q B I Q", token_id.encode(), amount, decimal, timestamp, user_id
        )
    tx += monitor.schnorr_sign(tx, bip340tag="zex")
    return tx


def tagged_hash(data: bytes, tag: str) -> bytes:
    """
    Tagged hashes ensure that hashes used in one context can not be used in another.
    It is used extensively in Taproot

    A tagged hash is: SHA256( SHA256("TapTweak") ||
                              SHA256("TapTweak") ||
                              data
                            )
    """

    tag_digest = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(tag_digest + tag_digest + data).digest()


# to convert hashes to ints we need byteorder BIG...
def b_to_i(b: bytes) -> int:
    """Converts a bytes to a number"""
    return int.from_bytes(b, byteorder="big")


def i_to_b8(i: int) -> bytes:
    """Converts an integer to bytes"""
    return i.to_bytes(8, byteorder="big")


def calculate_tweak(pubkey: PublicKey, user_id: int) -> int:
    """
    Calculates the tweak to apply to the public and private key when required.
    """

    # only the x coordinate is tagged_hash'ed
    key_x = pubkey.to_bytes()[:32]

    tweak = tagged_hash(key_x + i_to_b8(user_id), "TapTweak")

    # we convert to int for later elliptic curve  arithmetics
    tweak_int = b_to_i(tweak)

    return tweak_int


def get_taproot_address(master_public: PublicKey, user_id: int) -> P2trAddress:
    tweak_int = calculate_tweak(master_public, user_id)
    # keep x-only coordinate
    tweak_and_odd = tweak_taproot_pubkey(master_public.key.to_string(), tweak_int)
    pubkey = tweak_and_odd[0][:32]
    is_odd = tweak_and_odd[1]

    return P2trAddress(witness_program=pubkey.hex(), is_odd=is_odd)


async def run_monitor_btc(network: dict, api_url: str, monitor: PrivateKey):
    blocks_confirmation = network["blocks_confirmation"]
    block_duration = network["block_duration"]
    chain = network["chain"]
    sent_block = httpx.get(f"{api_url}/block/latest?chain={chain}").json()["block"]
    processed_block = sent_block

    rpc = BitcoinRPC.from_config(network["node_url"], None)

    master_pub = PublicKey.from_hex(network["public_key"])

    latest_user_id = 0
    all_taproot_addresses: dict[str, int] = {}

    try:
        while IS_RUNNING:
            try:
                latest_block_num = await rpc.getblockcount()
            except (httpx.ReadTimeout, RPCError) as e:
                print(f"{chain} error {e}")
                await asyncio.sleep(10)
                continue
            if processed_block >= latest_block_num - (blocks_confirmation - 1):
                print(f"{chain} waiting for new block")
                await asyncio.sleep(block_duration)
                continue

            new_latest_user_id = httpx.get(f"{api_url}/users/latest-id").json()["id"]
            if latest_user_id != new_latest_user_id:
                for i in range(latest_user_id + 1, new_latest_user_id + 1):
                    taproot_pub = get_taproot_address(master_pub, i)

                    if i == 1:
                        print(f"God user taproot address: {taproot_pub.to_string()}")
                    all_taproot_addresses[taproot_pub.to_string()] = i

                latest_user_id = new_latest_user_id

            try:
                block_hash = await rpc.getblockhash(processed_block + 1)
                latest_block = await rpc.getblock(block_hash, 2)
            except (httpx.ReadTimeout, RPCError) as e:
                print(f"{chain} error {e}")
                await asyncio.sleep(10)
                continue

            seen_txs = set()
            deposits = []

            # Iterate through transactions in the block
            for tx in latest_block["tx"]:
                if tx["txid"] in seen_txs:
                    continue
                seen_txs.add(tx["txid"])

                # Check if any output address matches our list of Taproot addresses
                for out in tx["vout"]:
                    if "address" not in out["scriptPubKey"]:
                        continue

                    address = out["scriptPubKey"]["address"]
                    if address in all_taproot_addresses:
                        deposits.append(
                            {
                                "user_id": all_taproot_addresses[address],
                                "tokenIndex": "0x" + "0" * 40,
                                "amount": int(
                                    out["value"]
                                    * (10 ** TOKENS["BTC"]["0x" + "0" * 40])
                                ),
                            }
                        )
                        print(f"found deposit to address: {address}")
                await asyncio.sleep(0)  # give time to other tasks

            processed_block += 1
            if len(deposits) == 0:
                print(f"{chain} no deposit in block: {processed_block}")

            tx = create_tx(
                deposits,
                chain,
                sent_block + 1,
                processed_block,
                latest_block["time"],
                monitor,
            )
            httpx.post(f"{api_url}/deposit", json=[tx.decode("latin-1")])
            # to check if request is applied, query latest processed block from zex

            sent_block = httpx.get(f"{api_url}/block/latest?chain={chain}").json()[
                "block"
            ]
            while sent_block != processed_block and IS_RUNNING:
                print(
                    f"{chain} deposit is not yet applied, server desposited block: {sent_block}, script processed block: {processed_block}"
                )
                await asyncio.sleep(2)

                sent_block = httpx.get(f"{api_url}/block/latest?chain={chain}").json()[
                    "block"
                ]
                continue
    except asyncio.CancelledError:
        pass

    return network


async def get_xmr_last_block(network: dict):
    process = await subprocess.create_subprocess_exec(
        "node",
        "monero/get-height.js",
        f"rpc={network['node_url']}",
        f"network={0 if network['mainnet'] else 2}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    # Wait for the subprocess to finish and capture output
    stdout, stderr = await process.communicate()

    # Decode and strip the output
    output = stdout.decode().strip()
    error = stderr.decode().strip()
    if error:
        print(f"{network['chain']} exec error: {error}")
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError as e:
        print(f"{network['chain']} decode error: {e}")
        return None


async def get_xmr_transactions(network: dict, from_block, to_block):
    process = await subprocess.create_subprocess_exec(
        "node",
        "monero/get-blocks.js",
        f"rpc={network['node_url']}",
        f"network={0 if network['mainnet'] else 2}",
        f"walletPath={network['wallet_path']}",
        f"walletPass={network['wallet_pass']}",
        f"from={from_block}",
        f"to={to_block}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    # Wait for the subprocess to finish and capture output
    stdout, stderr = await process.communicate()

    # Decode and strip the output
    output = stdout.decode().strip()
    error = stderr.decode().strip()
    if error:
        print(f"{network['chain']} exec error: {error}")
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError as e:
        print(f"{network['chain']} decode error: {e}")
        return None


async def run_monitor_xmr(network: dict, api_url: str, monitor: PrivateKey):
    blocks_confirmation = network["blocks_confirmation"]
    block_duration = network["block_duration"]
    chain = network["chain"]
    sent_block = httpx.get(f"{api_url}/block/latest?chain={chain}").json()["block"]
    processed_block = sent_block

    while IS_RUNNING:
        latest_block = await get_xmr_last_block(network)
        if latest_block is None:
            print(f"{chain} failed to get latest block info")
            await asyncio.sleep(10)
            continue

        if processed_block >= latest_block["height"] - (blocks_confirmation - 1):
            print(f"{chain} waiting for new block")
            await asyncio.sleep(block_duration)
            continue
        txs = await get_xmr_transactions(
            network, processed_block + 1, latest_block["height"]
        )
        if txs is None:
            print(f"{chain} failed to get transactions")
            await asyncio.sleep(10)
            continue
        deposits = []
        for tx in txs:
            if "paymentId" not in tx["tx"]:
                continue
            user_id = int(tx["tx"]["paymentId"], 16)
            resp = httpx.get(f"{api_url}/user/public?id={user_id}")
            if resp.status_code != 200:
                print(f"{chain} deposit for not registered user with id={user_id}")
                continue
            deposits.append(
                {
                    "user_id": user_id,
                    "tokenIndex": b"\x00" * 42,
                    "amount": int(tx["amount"]),
                }
            )

        if len(deposits) == 0:
            print(
                f"{chain} no deposit in from block {processed_block + 1} to {latest_block['height']}"
            )
        processed_block = latest_block["height"] - (blocks_confirmation - 1)

        tx = create_tx(
            deposits,
            chain,
            sent_block + 1,
            processed_block,
            latest_block["block"]["timestamp"],
            monitor,
        )
        httpx.post(f"{api_url}/deposit", json=[tx.decode("latin-1")])
        # to check if request is applied, query latest processed block from zex

        sent_block = httpx.get(f"{api_url}/block/latest?chain={chain}").json()["block"]
        while sent_block != processed_block and IS_RUNNING:
            print(
                f"{chain} deposit is not yet applied, server desposited block: {sent_block}, script processed block: {processed_block}"
            )
            await asyncio.sleep(2)

            sent_block = httpx.get(f"{api_url}/block/latest?chain={chain}").json()[
                "block"
            ]
            continue

    return network


async def main():
    # processed_block = web3.eth.block_number - BLOCKS_CONFIRMATION # should be queried from zex
    # print(processed_block)
    # Set up signal handler
    def signal_handler():
        global IS_RUNNING
        IS_RUNNING = False
        print("\nInterrupt received. Stopping tasks...")

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, signal_handler)
    loop.add_signal_handler(signal.SIGTERM, signal_handler)

    with open("config.yaml") as file:
        config = yaml.safe_load(file)

    networks = config["networks"]
    api_url = config["api_url"]
    monitor_private = config["monitor_private"]
    monitor = PrivateKey(bytes(bytearray.fromhex(monitor_private)), raw=True)

    tasks = []
    for network in networks:
        if network["name"] == "btc":
            t = asyncio.create_task(run_monitor_btc(network, api_url, monitor))
        elif network["name"] == "monero":
            t = asyncio.create_task(run_monitor_xmr(network, api_url, monitor))
        else:
            print("invalid network")
            continue
        tasks.append(t)

    try:
        # Wait for all tasks to complete or until interrupted
        results = await asyncio.gather(*tasks, return_exceptions=False)
        config["networks"] = results
        pprint(config, indent=2)
        # with open("config.yaml", "w") as file:
        #     yaml.safe_dump(config)
    except asyncio.CancelledError:
        print("Tasks were cancelled")
    finally:
        # Ensure all tasks are properly cancelled
        for task in tasks:
            if not task.done():
                task.cancel()

        # Wait for all tasks to be cancelled
        await asyncio.gather(*tasks, return_exceptions=False)

        print("All tasks have been stopped. Exiting program.")


if __name__ == "__main__":
    asyncio.run(main())
