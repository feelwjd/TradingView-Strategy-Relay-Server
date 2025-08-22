import requests
from typing import List, Tuple, Dict, Any, Optional
from .symbols import normalize_symbol_for_exchange
from .config import Config

EMA_LEN_4H = 200

def fetch_ohlcv(ex, symbol: str, timeframe: str = "4h", limit: int = 200):
    return ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

def ema_from_closes(closes: List[float], length: int) -> Optional[float]:
    if not closes or len(closes) < 2: return None
    alpha = 2 / (length + 1)
    ema = closes[0]
    for c in closes[1:]:
        ema = alpha * c + (1 - alpha) * ema
    return float(ema)

def safe_float(x):
    try:
        if x is None: return None
        return float(x)
    except: return None

def is_http_url(s: str) -> bool:
    if not s: return False
    s = s.strip().lower()
    return s.startswith("http://") or s.startswith("https://")

def fetch_vix(cfg: Config):
    try:
        if not is_http_url(cfg.vix_url): return None
        resp = requests.get(cfg.vix_url, timeout=3)
        if not resp.ok: return None
        j = resp.json()
        v = j.get("vix") or j.get("value")
        return safe_float(v)
    except Exception:
        return None

def fetch_phemex_funding_rate(ex_trade, symbol: str) -> Optional[float]:
    try:
        fr = ex_trade.fetch_funding_rate(symbol)
        if not isinstance(fr, dict): return None
        v = fr.get("fundingRate")
        if v is None:
            info = fr.get("info") or {}
            v = info.get("fundingRate") or info.get("lastFundingRate") or info.get("predictedFundingRate")
        return safe_float(v)
    except Exception:
        return None

def get_regime(cfg: Config, ex_trade, ex_regime, sym_eth: str, sym_btc: str) -> Tuple[str, Dict[str,Any]]:
    eth_sym = normalize_symbol_for_exchange(cfg.regime_symbol_eth or sym_eth, cfg.regime_exchange)
    btc_sym = normalize_symbol_for_exchange(cfg.regime_symbol_btc or sym_btc, cfg.regime_exchange)

    eth_px = eth_ema = btc_px = btc_ema = None
    try:
        eth_ohlcv = fetch_ohlcv(ex_regime, eth_sym, "4h", 200)
        ec = [c[4] for c in eth_ohlcv if c and len(c)>4]
        if len(ec) >= EMA_LEN_4H:
            eth_px  = safe_float(ec[-1])
            eth_ema = ema_from_closes(ec[-EMA_LEN_4H:], EMA_LEN_4H)
    except Exception:
        pass
    try:
        btc_ohlcv = fetch_ohlcv(ex_regime, btc_sym, "4h", 200)
        bc = [c[4] for c in btc_ohlcv if c and len(c)>4]
        if len(bc) >= EMA_LEN_4H:
            btc_px  = safe_float(bc[-1])
            btc_ema = ema_from_closes(bc[-EMA_LEN_4H:], EMA_LEN_4H)
    except Exception:
        pass

    base_regime = "neutral"
    if all(v is not None for v in (eth_px, eth_ema, btc_px, btc_ema)):
        if (eth_px > eth_ema) and (btc_px > btc_ema): base_regime = "bull"
        elif (eth_px < eth_ema) and (btc_px < btc_ema): base_regime = "bear"

    fr_eth = fetch_phemex_funding_rate(ex_trade, "ETH/USDT:USDT")
    vix_val = fetch_vix(cfg)

    gated = False; gate_reason = None
    if fr_eth is not None and abs(fr_eth) > cfg.funding_abs_max:
        gated = True; gate_reason = f"funding_abs>{cfg.funding_abs_max}"
    if not gated and vix_val is not None and vix_val > cfg.vix_max:
        gated = True; gate_reason = f"vix>{cfg.vix_max}"

    meta = {
        "base": base_regime,
        "eth_px": eth_px, "btc_px": btc_px,
        "eth_ema": eth_ema, "btc_ema": btc_ema,
        "funding": fr_eth, "vix": vix_val,
        "gated": gated, "reason": gate_reason,
        "source": {"exchange": cfg.regime_exchange, "testnet": cfg.regime_testnet, "eth_sym": eth_sym, "btc_sym": btc_sym},
    }
    final_regime = "neutral" if gated else base_regime
    return final_regime, meta
