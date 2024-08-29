from pydantic import BaseModel


class BalanceResponse(BaseModel):
    chain: str
    token: int
    balance: str
    price: float
    change_24h: float
    value: float


class TradeResponse(BaseModel):
    name: str
    t: int
    base_chain: str
    base_token: int
    quote_chain: str
    quote_token: int
    amount: float
    price: float
    nonce: int


class OrderResponse(BaseModel):
    name: str
    base_chain: str
    base_token: int
    quote_chain: str
    quote_token: int
    amount: float
    price: float
    t: int
    nonce: int


class NonceResponse(BaseModel):
    nonce: int


class UserIDResponse(BaseModel):
    id: int


class UserPublicResponse(BaseModel):
    public: str


class Addresses(BaseModel):
    BTC: str
    XMR: str
    BST: str
    HOL: str
    SEP: str


class UserAddressesResponse(BaseModel):
    user: str
    addresses: Addresses


class Asset(BaseModel):
    chain: str
    id: int


class DepositResponse(BaseModel):
    token: str
    amount: float
    time: int


class Symbol(BaseModel):
    symbol: str
    baseAsset: Asset
    quoteAsset: Asset
    lastPrice: float
    volume24h: float
    priceChange24h: float
    high24h: float
    low24h: float
    priceChange7D: float


class ExchangeInfoResponse(BaseModel):
    timezone: str
    symbols: list[Symbol]
