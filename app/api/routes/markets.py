from urllib.parse import unquote
import json
import re
import time

from fastapi import APIRouter, HTTPException
import numpy as np
import pandas as pd

from app import zex
from app.api.cache import timed_lru_cache
from app.config import settings
from app.models.response import (
    ExchangeInfoResponse,
    StatisticsFullResponse,
    StatisticsMiniResponse,
    Symbol,
    Token,
)

from . import NAMES, USDT_MAINNET

router = APIRouter()

market_filter_list = (
    "BTC-USDT",
    "LINK-USDT",
)

token_filter_list = (
    "BTC",
    "USDT",
    "LINK",
)


@router.get("/depth")
async def depth(symbol: str, limit: int = 500):
    return zex.get_order_book(symbol.upper(), limit)


def get_token_info(token) -> Token:
    t = Token(
        token=token,
        chainType="evm" if token[:3] not in ["BTC"] else "native_only",
        price=zex.markets[f"{token}-{USDT_MAINNET}"].get_last_price()
        if f"{token}-{USDT_MAINNET}" in zex.markets
        else 0
        if token != USDT_MAINNET
        else 1,
        change_24h=zex.markets[f"{token}-{USDT_MAINNET}"].get_price_change_24h_percent()
        if token != USDT_MAINNET and f"{token}-{USDT_MAINNET}" in zex.markets
        else 0,
        name=NAMES.get(token, token),
        symbol=token,
    )
    return t


@timed_lru_cache(seconds=60 if settings.zex.mainnet else 1)
def _exchange_info_response(symbols: tuple[str]):
    symbols_result = []
    for name in zex.markets.keys():
        if name not in symbols:
            continue
        base_asset, quote_asset = name.split("-")
        s = Symbol(
            symbol=name,
            status="TRADING",
            baseAsset=base_asset,
            baseAssetPrecision=0,
            quoteAsset=quote_asset,
            quotePrecision=0,
            quoteAssetPrecision=0,
            orderTypes=["LIMIT"],
            filters=[],
        )
        symbols_result.append(s)
    return ExchangeInfoResponse(
        timezone="UTC",
        serverTime=int(time.time() * 1000),
        symbols=symbols_result,
    )


def parse_symbol_list(input_str: str) -> list[str]:
    """
    Parse a string that could be either JSON or URL-encoded JSON into a Python list.

    Args:
        input_str: String that could be either:
            - JSON array string: '["BTCUSDT","BNBUSDT"]'
            - URL-encoded JSON: '%5B%22BTCUSDT%22,%22BNBUSDT%22%5D'

    Returns:
        list: Python list of strings

    Examples:
        >>> parse_symbol_list('["BTCUSDT","BNBUSDT"]')
        ['BTCUSDT', 'BNBUSDT']
        >>> parse_symbol_list("%5B%22BTCUSDT%22,%22BNBUSDT%22%5D")
        ['BTCUSDT', 'BNBUSDT']
    """
    try:
        # First try to decode as URL-encoded string
        decoded_str = unquote(input_str)
        # Then parse as JSON
        return json.loads(decoded_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format: {e}")


@router.get("/exchangeInfo")
async def exhange_info(
    symbol: str | None = None, symbols: str | None = None
) -> ExchangeInfoResponse:
    if symbol and symbols:
        raise HTTPException(
            400, {"error": "only one of symbol or symbols should be used"}
        )
    if not symbol and not symbols:
        symbols = market_filter_list
    elif not symbols:
        symbols = (symbol,)
    else:
        try:
            symbols = tuple(parse_symbol_list(symbols))
        except ValueError:
            raise HTTPException(422, "failed to parse list of symbols")

    for s in symbols:
        if s in zex.markets.keys():
            continue
        raise HTTPException(400, {"error": f"invalid symbol {s}"})

    return _exchange_info_response(symbols)


@router.get("/klines")
async def klines(
    symbol: str,
    timeframe: str,
    startTime: int | None = None,
    endTime: int | None = None,
    limit: int = 500,
):
    base_klines = zex.get_kline(symbol.upper())
    if len(base_klines) == 0:
        return []

    if timeframe not in [
        "1min",
        "3min",
        "5min",
        "15min",
        "30min",
        "1h",
        "4h",
        "1d",
        "1W",
    ]:
        raise HTTPException(
            400,
            {
                "error": "invalid timeframe. use one of [1min, 3min, 5min, 15min, 30min, 1h, 4h, 1d, 1w]"
            },
        )

    if timeframe == "1min":
        resampled = base_klines
    else:
        df = base_klines.copy()
        df.index = pd.to_datetime(df.index, unit="ms")

        # Define aggregation functions for each column
        agg_dict = {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
            "NumberOfTrades": "sum",
            "CloseTime": "last",
        }
        # Define resampling rules for OHLC
        resampled = df.resample(timeframe).agg(agg_dict)
        # Remove rows with NaN values (periods with no trades)
        resampled = resampled.dropna()

        # Calculate CloseTime based on timeframe
        freq_map = {
            "min": 60000,  # 1 minute in milliseconds
            "h": 3600000,  # 1 hour in milliseconds
            "d": 86400000,  # 1 day in milliseconds
            "W": 604800000,  # 1 week in milliseconds
        }

        number_as_str = re.findall(r"\d+", timeframe)[0]
        number = int(number_as_str)
        number_len = len(number_as_str)
        unit = timeframe[number_len:]

        # Calculate milliseconds to add
        ms_to_add = number * freq_map[unit] - 1

        # Convert index to Unix timestamps in milliseconds
        resampled.index = resampled.index.astype(np.int64) // 10**6
        # Calculate CloseTime
        resampled["CloseTime"] = resampled.index + ms_to_add

    if not startTime:
        startTime = resampled.index[0]

    if not endTime:
        endTime = resampled.iloc[-1]["CloseTime"]

    return [
        [
            idx,
            x["Open"],
            x["High"],
            x["Low"],
            x["Close"],
            x["Volume"],
            x["CloseTime"],
            0,
            x["NumberOfTrades"],
            0,
            0,
            -1,
        ]
        for idx, x in resampled.iterrows()
        if startTime <= idx and endTime >= x["CloseTime"]
    ][-limit:]


@router.get("/ticker/tradingDay")
def get_price_statistics(
    symbol: str | None, symbols: str | None
) -> StatisticsMiniResponse | list[StatisticsMiniResponse]:
    if symbol and symbols:
        raise HTTPException(
            400, {"error": "only one of symbol or symbols should be used"}
        )
    if not symbol and not symbols:
        symbols = market_filter_list
    elif not symbols:
        symbols = (symbol,)
    else:
        try:
            symbols = tuple(parse_symbol_list(symbols))
        except ValueError:
            raise HTTPException(422, "failed to parse list of symbols")

    for s in symbols:
        if s in zex.markets.keys():
            continue
        raise HTTPException(400, {"error": f"invalid symbol {s}"})

    raise NotImplementedError("tradingDay not implemented")


@router.get("/ticker/price")
def get_price(symbol: str | None, symbols: str | None):
    if symbol and symbols:
        raise HTTPException(
            400, {"error": "only one of symbol or symbols should be used"}
        )
    if not symbol and not symbols:
        symbols = market_filter_list
    elif not symbols:
        symbols = (symbol,)
    else:
        try:
            symbols = parse_symbol_list(symbols)
        except ValueError:
            raise HTTPException(422, "failed to parse list of symbols")

    for s in symbols:
        if s in zex.markets.keys():
            continue
        raise HTTPException(400, {"error": f"invalid symbol {s}"})

    if symbol:
        return {{"symbol": symbol, "price": str(zex.markets[symbol].get_last_price())}}
    return [
        {
            "symbol": s,
            "price": str(zex.markets[s].get_last_price()),
        }
        for s in symbols
    ]


@router.get("/ticker/bookTicker")
def get_book_ticker(symbol: str | None, symbols: str | None):
    if symbol and symbols:
        raise HTTPException(
            400, {"error": "only one of symbol or symbols should be used"}
        )
    if not symbol and not symbols:
        symbols = market_filter_list
    elif not symbols:
        symbols = (symbol,)
    else:
        try:
            symbols = tuple(parse_symbol_list(symbols))
        except ValueError:
            raise HTTPException(422, "failed to parse list of symbols")

    for s in symbols:
        if s in zex.markets.keys():
            continue
        raise HTTPException(400, {"error": f"invalid symbol {s}"})

    raise NotImplementedError()


@router.get("/ticker")
def get_ticker(
    symbol: str | None, symbols: str | None
) -> StatisticsFullResponse | list[StatisticsFullResponse]:  # noqa: F821
    if symbol and symbols:
        raise HTTPException(
            400, {"error": "only one of symbol or symbols should be used"}
        )
    if not symbol and not symbols:
        symbols = market_filter_list
    elif not symbols:
        symbols = (symbol,)
    else:
        try:
            symbols = tuple(parse_symbol_list(symbols))
        except ValueError:
            raise HTTPException(422, "failed to parse list of symbols")

    for s in symbols:
        if s in zex.markets.keys():
            continue
        raise HTTPException(400, {"error": f"invalid symbol {s}"})

    response = []
    for s in symbols:
        market = zex.markets[s]
        r = StatisticsFullResponse(
            symbol=s,
            openPrice=market.get_open_24h(),
            highPrice=market.get_high_24h(),
            lowPrice=market.get_low_24h(),
            lastPrice=market.get_last_price(),
            volume=market.get_volume_24h(),
            quoteVolume="",
            openTime=market.get_open_time_24h(),
            closeTime=int(time.time() * 1000),
            firstId=0,
            lastId=0,
            count=market.get_trade_num_24h(),
            priceChange=market.get_price_change_24h(),
            priceChangePercent=market.get_price_change_24h_percent(),
            weightedAvgPrice="0",
        )
        response.append(r)

    if symbol:
        return response[0]
    return response
