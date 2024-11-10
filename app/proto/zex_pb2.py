# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: zex.proto
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\tzex.proto\"\xfc\t\n\x08ZexState\x12\'\n\x07markets\x18\x01 \x03(\x0b\x32\x16.ZexState.MarketsEntry\x12)\n\x08\x62\x61lances\x18\x02 \x03(\x0b\x32\x17.ZexState.BalancesEntry\x12\x1d\n\x07\x61mounts\x18\x03 \x03(\x0b\x32\x0c.AmountEntry\x12\x1b\n\x06trades\x18\x04 \x03(\x0b\x32\x0b.TradeEntry\x12\x1b\n\x06orders\x18\x05 \x03(\x0b\x32\x0b.OrderEntry\x12+\n\twithdraws\x18\x06 \x03(\x0b\x32\x18.ZexState.WithdrawsEntry\x12\x36\n\x0fwithdraw_nonces\x18\x07 \x03(\x0b\x32\x1d.ZexState.WithdrawNoncesEntry\x12\x38\n\x10\x64\x65posited_blocks\x18\x08 \x03(\x0b\x32\x1e.ZexState.DepositedBlocksEntry\x12\x1b\n\x06nonces\x18\t \x03(\x0b\x32\x0b.NonceEntry\x12%\n\x0bpair_lookup\x18\n \x03(\x0b\x32\x10.PairLookupEntry\x12\x15\n\rlast_tx_index\x18\x0b \x01(\x04\x12\x1f\n\x08\x64\x65posits\x18\x0c \x03(\x0b\x32\r.DepositEntry\x12+\n\x13public_to_id_lookup\x18\r \x03(\x0b\x32\x0e.IDLookupEntry\x12<\n\x13id_to_public_lookup\x18\x0e \x03(\x0b\x32\x1f.ZexState.IdToPublicLookupEntry\x12G\n$contract_to_token_id_on_chain_lookup\x18\x0f \x03(\x0b\x32\x19.ContractToIDOnChainEntry\x12G\n$token_id_to_contract_on_chain_lookup\x18\x10 \x03(\x0b\x32\x19.IDToContractOnChainEntry\x12\x42\n\x1dtoken_decimal_on_chain_lookup\x18\x11 \x03(\x0b\x32\x1b.TokenToDecimalOnChainEntry\x12\x41\n\x16last_token_id_on_chain\x18\x12 \x03(\x0b\x32!.ZexState.LastTokenIdOnChainEntry\x1a\x37\n\x0cMarketsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\x16\n\x05value\x18\x02 \x01(\x0b\x32\x07.Market:\x02\x38\x01\x1a\x39\n\rBalancesEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\x17\n\x05value\x18\x02 \x01(\x0b\x32\x08.Balance:\x02\x38\x01\x1a<\n\x0eWithdrawsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\x19\n\x05value\x18\x02 \x01(\x0b\x32\n.Withdraws:\x02\x38\x01\x1a\x46\n\x13WithdrawNoncesEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\x1e\n\x05value\x18\x02 \x01(\x0b\x32\x0f.WithdrawNonces:\x02\x38\x01\x1a\x36\n\x14\x44\x65positedBlocksEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\x04:\x02\x38\x01\x1a\x37\n\x15IdToPublicLookupEntry\x12\x0b\n\x03key\x18\x01 \x01(\x04\x12\r\n\x05value\x18\x02 \x01(\x0c:\x02\x38\x01\x1a\x39\n\x17LastTokenIdOnChainEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\x04:\x02\x38\x01\"\x89\x02\n\x06Market\x12\x12\n\nbase_token\x18\x01 \x01(\t\x12\x13\n\x0bquote_token\x18\x02 \x01(\t\x12\x1a\n\nbuy_orders\x18\x03 \x03(\x0b\x32\x06.Order\x12\x1b\n\x0bsell_orders\x18\x04 \x03(\x0b\x32\x06.Order\x12(\n\x0f\x62ids_order_book\x18\x05 \x03(\x0b\x32\x0f.OrderBookEntry\x12(\n\x0f\x61sks_order_book\x18\x06 \x03(\x0b\x32\x0f.OrderBookEntry\x12\x10\n\x08\x66irst_id\x18\x07 \x01(\x04\x12\x10\n\x08\x66inal_id\x18\x08 \x01(\x04\x12\x16\n\x0elast_update_id\x18\t \x01(\x04\x12\r\n\x05kline\x18\n \x01(\x0c\"1\n\x05Order\x12\r\n\x05price\x18\x01 \x01(\x01\x12\r\n\x05index\x18\x02 \x01(\x03\x12\n\n\x02tx\x18\x03 \x01(\x0c\"/\n\x0eOrderBookEntry\x12\r\n\x05price\x18\x01 \x01(\x01\x12\x0e\n\x06\x61mount\x18\x02 \x01(\x01\"*\n\x07\x42\x61lance\x12\x1f\n\x08\x62\x61lances\x18\x01 \x03(\x0b\x32\r.BalanceEntry\"2\n\x0c\x42\x61lanceEntry\x12\x12\n\npublic_key\x18\x01 \x01(\x0c\x12\x0e\n\x06\x61mount\x18\x02 \x01(\x01\")\n\x0b\x41mountEntry\x12\n\n\x02tx\x18\x01 \x01(\x0c\x12\x0e\n\x06\x61mount\x18\x02 \x01(\x01\"8\n\nTradeEntry\x12\x12\n\npublic_key\x18\x01 \x01(\x0c\x12\x16\n\x06trades\x18\x02 \x03(\x0b\x32\x06.Trade\"S\n\x05Trade\x12\t\n\x01t\x18\x01 \x01(\r\x12\x0e\n\x06\x61mount\x18\x02 \x01(\x01\x12\x0c\n\x04pair\x18\x03 \x01(\t\x12\x12\n\norder_type\x18\x04 \x01(\r\x12\r\n\x05order\x18\x05 \x01(\x0c\"0\n\nOrderEntry\x12\x12\n\npublic_key\x18\x01 \x01(\x0c\x12\x0e\n\x06orders\x18\x02 \x03(\x0c\"4\n\rWithdrawEntry\x12\x12\n\npublic_key\x18\x01 \x01(\x0c\x12\x0f\n\x07raw_txs\x18\x02 \x03(\x0c\".\n\tWithdraws\x12!\n\twithdraws\x18\x01 \x03(\x0b\x32\x0e.WithdrawEntry\"7\n\x12WithdrawNonceEntry\x12\x12\n\npublic_key\x18\x01 \x01(\x0c\x12\r\n\x05nonce\x18\x02 \x01(\x04\"5\n\x0eWithdrawNonces\x12#\n\x06nonces\x18\x01 \x03(\x0b\x32\x13.WithdrawNonceEntry\">\n\x0c\x44\x65positEntry\x12\x12\n\npublic_key\x18\x01 \x01(\x0c\x12\x1a\n\x08\x64\x65posits\x18\x02 \x03(\x0b\x32\x08.Deposit\"6\n\x07\x44\x65posit\x12\r\n\x05token\x18\x01 \x01(\t\x12\x0e\n\x06\x61mount\x18\x02 \x01(\x01\x12\x0c\n\x04time\x18\x03 \x01(\x04\"/\n\nNonceEntry\x12\x12\n\npublic_key\x18\x01 \x01(\x0c\x12\r\n\x05nonce\x18\x02 \x01(\r\"U\n\x0fPairLookupEntry\x12\x0b\n\x03key\x18\x01 \x01(\x0c\x12\x12\n\nbase_token\x18\x02 \x01(\t\x12\x13\n\x0bquote_token\x18\x03 \x01(\t\x12\x0c\n\x04pair\x18\x04 \x01(\t\"4\n\rIDLookupEntry\x12\x12\n\npublic_key\x18\x01 \x01(\x0c\x12\x0f\n\x07user_id\x18\x02 \x01(\x04\"\xa3\x01\n\x18\x43ontractToIDOnChainEntry\x12\r\n\x05\x63hain\x18\x01 \x01(\t\x12\x43\n\x0e\x63ontract_to_id\x18\x02 \x03(\x0b\x32+.ContractToIDOnChainEntry.ContractToIdEntry\x1a\x33\n\x11\x43ontractToIdEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\x04:\x02\x38\x01\"\xa3\x01\n\x18IDToContractOnChainEntry\x12\r\n\x05\x63hain\x18\x01 \x01(\t\x12\x43\n\x0eid_to_contract\x18\x02 \x03(\x0b\x32+.IDToContractOnChainEntry.IdToContractEntry\x1a\x33\n\x11IdToContractEntry\x12\x0b\n\x03key\x18\x01 \x01(\x04\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01\"\xb6\x01\n\x1aTokenToDecimalOnChainEntry\x12\r\n\x05\x63hain\x18\x01 \x01(\t\x12O\n\x13\x63ontract_to_decimal\x18\x02 \x03(\x0b\x32\x32.TokenToDecimalOnChainEntry.ContractToDecimalEntry\x1a\x38\n\x16\x43ontractToDecimalEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\x04:\x02\x38\x01\x62\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'zex_pb2', _globals)
if _descriptor._USE_C_DESCRIPTORS == False:
  DESCRIPTOR._options = None
  _globals['_ZEXSTATE_MARKETSENTRY']._options = None
  _globals['_ZEXSTATE_MARKETSENTRY']._serialized_options = b'8\001'
  _globals['_ZEXSTATE_BALANCESENTRY']._options = None
  _globals['_ZEXSTATE_BALANCESENTRY']._serialized_options = b'8\001'
  _globals['_ZEXSTATE_WITHDRAWSENTRY']._options = None
  _globals['_ZEXSTATE_WITHDRAWSENTRY']._serialized_options = b'8\001'
  _globals['_ZEXSTATE_WITHDRAWNONCESENTRY']._options = None
  _globals['_ZEXSTATE_WITHDRAWNONCESENTRY']._serialized_options = b'8\001'
  _globals['_ZEXSTATE_DEPOSITEDBLOCKSENTRY']._options = None
  _globals['_ZEXSTATE_DEPOSITEDBLOCKSENTRY']._serialized_options = b'8\001'
  _globals['_ZEXSTATE_IDTOPUBLICLOOKUPENTRY']._options = None
  _globals['_ZEXSTATE_IDTOPUBLICLOOKUPENTRY']._serialized_options = b'8\001'
  _globals['_ZEXSTATE_LASTTOKENIDONCHAINENTRY']._options = None
  _globals['_ZEXSTATE_LASTTOKENIDONCHAINENTRY']._serialized_options = b'8\001'
  _globals['_CONTRACTTOIDONCHAINENTRY_CONTRACTTOIDENTRY']._options = None
  _globals['_CONTRACTTOIDONCHAINENTRY_CONTRACTTOIDENTRY']._serialized_options = b'8\001'
  _globals['_IDTOCONTRACTONCHAINENTRY_IDTOCONTRACTENTRY']._options = None
  _globals['_IDTOCONTRACTONCHAINENTRY_IDTOCONTRACTENTRY']._serialized_options = b'8\001'
  _globals['_TOKENTODECIMALONCHAINENTRY_CONTRACTTODECIMALENTRY']._options = None
  _globals['_TOKENTODECIMALONCHAINENTRY_CONTRACTTODECIMALENTRY']._serialized_options = b'8\001'
  _globals['_ZEXSTATE']._serialized_start=14
  _globals['_ZEXSTATE']._serialized_end=1290
  _globals['_ZEXSTATE_MARKETSENTRY']._serialized_start=870
  _globals['_ZEXSTATE_MARKETSENTRY']._serialized_end=925
  _globals['_ZEXSTATE_BALANCESENTRY']._serialized_start=927
  _globals['_ZEXSTATE_BALANCESENTRY']._serialized_end=984
  _globals['_ZEXSTATE_WITHDRAWSENTRY']._serialized_start=986
  _globals['_ZEXSTATE_WITHDRAWSENTRY']._serialized_end=1046
  _globals['_ZEXSTATE_WITHDRAWNONCESENTRY']._serialized_start=1048
  _globals['_ZEXSTATE_WITHDRAWNONCESENTRY']._serialized_end=1118
  _globals['_ZEXSTATE_DEPOSITEDBLOCKSENTRY']._serialized_start=1120
  _globals['_ZEXSTATE_DEPOSITEDBLOCKSENTRY']._serialized_end=1174
  _globals['_ZEXSTATE_IDTOPUBLICLOOKUPENTRY']._serialized_start=1176
  _globals['_ZEXSTATE_IDTOPUBLICLOOKUPENTRY']._serialized_end=1231
  _globals['_ZEXSTATE_LASTTOKENIDONCHAINENTRY']._serialized_start=1233
  _globals['_ZEXSTATE_LASTTOKENIDONCHAINENTRY']._serialized_end=1290
  _globals['_MARKET']._serialized_start=1293
  _globals['_MARKET']._serialized_end=1558
  _globals['_ORDER']._serialized_start=1560
  _globals['_ORDER']._serialized_end=1609
  _globals['_ORDERBOOKENTRY']._serialized_start=1611
  _globals['_ORDERBOOKENTRY']._serialized_end=1658
  _globals['_BALANCE']._serialized_start=1660
  _globals['_BALANCE']._serialized_end=1702
  _globals['_BALANCEENTRY']._serialized_start=1704
  _globals['_BALANCEENTRY']._serialized_end=1754
  _globals['_AMOUNTENTRY']._serialized_start=1756
  _globals['_AMOUNTENTRY']._serialized_end=1797
  _globals['_TRADEENTRY']._serialized_start=1799
  _globals['_TRADEENTRY']._serialized_end=1855
  _globals['_TRADE']._serialized_start=1857
  _globals['_TRADE']._serialized_end=1940
  _globals['_ORDERENTRY']._serialized_start=1942
  _globals['_ORDERENTRY']._serialized_end=1990
  _globals['_WITHDRAWENTRY']._serialized_start=1992
  _globals['_WITHDRAWENTRY']._serialized_end=2044
  _globals['_WITHDRAWS']._serialized_start=2046
  _globals['_WITHDRAWS']._serialized_end=2092
  _globals['_WITHDRAWNONCEENTRY']._serialized_start=2094
  _globals['_WITHDRAWNONCEENTRY']._serialized_end=2149
  _globals['_WITHDRAWNONCES']._serialized_start=2151
  _globals['_WITHDRAWNONCES']._serialized_end=2204
  _globals['_DEPOSITENTRY']._serialized_start=2206
  _globals['_DEPOSITENTRY']._serialized_end=2268
  _globals['_DEPOSIT']._serialized_start=2270
  _globals['_DEPOSIT']._serialized_end=2324
  _globals['_NONCEENTRY']._serialized_start=2326
  _globals['_NONCEENTRY']._serialized_end=2373
  _globals['_PAIRLOOKUPENTRY']._serialized_start=2375
  _globals['_PAIRLOOKUPENTRY']._serialized_end=2460
  _globals['_IDLOOKUPENTRY']._serialized_start=2462
  _globals['_IDLOOKUPENTRY']._serialized_end=2514
  _globals['_CONTRACTTOIDONCHAINENTRY']._serialized_start=2517
  _globals['_CONTRACTTOIDONCHAINENTRY']._serialized_end=2680
  _globals['_CONTRACTTOIDONCHAINENTRY_CONTRACTTOIDENTRY']._serialized_start=2629
  _globals['_CONTRACTTOIDONCHAINENTRY_CONTRACTTOIDENTRY']._serialized_end=2680
  _globals['_IDTOCONTRACTONCHAINENTRY']._serialized_start=2683
  _globals['_IDTOCONTRACTONCHAINENTRY']._serialized_end=2846
  _globals['_IDTOCONTRACTONCHAINENTRY_IDTOCONTRACTENTRY']._serialized_start=2795
  _globals['_IDTOCONTRACTONCHAINENTRY_IDTOCONTRACTENTRY']._serialized_end=2846
  _globals['_TOKENTODECIMALONCHAINENTRY']._serialized_start=2849
  _globals['_TOKENTODECIMALONCHAINENTRY']._serialized_end=3031
  _globals['_TOKENTODECIMALONCHAINENTRY_CONTRACTTODECIMALENTRY']._serialized_start=2975
  _globals['_TOKENTODECIMALONCHAINENTRY_CONTRACTTODECIMALENTRY']._serialized_end=3031
# @@protoc_insertion_point(module_scope)
