import ccxt
from typing import Tuple
from .config import Config

def pick_keys(use_testnet: bool, key_dev: str, sec_dev: str, key_prod: str, sec_prod: str,
              fallback_key: str = "", fallback_sec: str = "") -> Tuple[str,str]:
    if use_testnet:
        return (key_dev or fallback_key), (sec_dev or fallback_sec)
    return (key_prod or fallback_key), (sec_prod or fallback_sec)

def make_phemex(testnet: bool, api_key: str = "", secret: str = ""):
    ex = ccxt.phemex({"apiKey": api_key, "secret": secret, "enableRateLimit": True})
    ex.set_sandbox_mode(bool(testnet))
    ex.load_markets()
    return ex

def make_binance(market: str = "spot", testnet: bool = False, api_key: str = "", secret: str = ""):
    if market == "usdm":
        exb = ccxt.binanceusdm({"apiKey": api_key, "secret": secret, "enableRateLimit": True})
        if testnet:
            exb.urls["api"]["fapi"]   = "https://testnet.binancefuture.com/fapi/v1"
            exb.urls["api"]["public"] = exb.urls["api"]["fapi"]
        exb.options["defaultType"] = "future"
        exb.load_markets()
        return exb
    else:
        exb = ccxt.binance({"apiKey": api_key, "secret": secret, "enableRateLimit": True})
        exb.options["defaultType"] = "spot"
        if testnet: exb.set_sandbox_mode(True)
        exb.load_markets()
        return exb

def build_exchanges(cfg: Config):
    # trade
    trade_key, trade_sec = pick_keys(
        cfg.trade_testnet,
        cfg.phemex_api_key_dev, cfg.phemex_secret_dev,
        cfg.phemex_api_key_prod, cfg.phemex_secret_prod,
        cfg.api_key_fallback, cfg.api_sec_fallback
    )
    ex_trade = make_phemex(cfg.trade_testnet, trade_key, trade_sec)

    # regime
    if cfg.regime_exchange == "phemex":
        reg_key, reg_sec = pick_keys(
            cfg.regime_testnet,
            cfg.regime_phemex_key_dev, cfg.regime_phemex_sec_dev,
            cfg.regime_phemex_key_prod, cfg.regime_phemex_sec_prod
        )
        ex_regime = make_phemex(cfg.regime_testnet, reg_key, reg_sec)
    elif cfg.regime_exchange == "binance":
        bin_key, bin_sec = pick_keys(
            cfg.regime_testnet,
            cfg.regime_binance_key_dev, cfg.regime_binance_sec_dev,
            cfg.regime_binance_key_prod, cfg.regime_binance_sec_prod
        )
        ex_regime = make_binance(cfg.regime_binance_market, cfg.regime_testnet, bin_key, bin_sec)
    else:
        ex_regime = ex_trade

    return ex_trade, ex_regime
