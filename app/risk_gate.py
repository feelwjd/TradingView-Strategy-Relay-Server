from fastapi import HTTPException
from typing import Optional, Tuple
from .config import Config
from .market import get_last_or_mark

def slippage_guard(cfg: Config, ex, ref_price: float, sym: str):
    if ref_price is None or ref_price <= 0:
        return
    px = get_last_or_mark(ex, sym, cfg.use_mark_price)
    slip = abs(px - ref_price) / ref_price
    if slip > cfg.max_slippage:
        raise HTTPException(409, f"slippage {slip:.4f} > MAX_SLIPPAGE")

def regime_alloc_and_lev(cfg: Config, strategy: str, regime: str) -> Tuple[float,int]:
    s = (strategy or "").lower()
    if s not in ("bull","bear"):
        return cfg.alloc_pct, cfg.lev_default
    if s == "bull":
        if regime == "bull":    return cfg.alloc_bull_bull,    cfg.lev_bull_bull
        if regime == "bear":    return cfg.alloc_bull_bear,    cfg.lev_bull_bear
        return cfg.alloc_bull_neutral, cfg.lev_bull_neutral
    else:
        if regime == "bull":    return cfg.alloc_bear_bull,    cfg.lev_bear_bull
        if regime == "bear":    return cfg.alloc_bear_bear,    cfg.lev_bear_bear
        return cfg.alloc_bear_neutral, cfg.lev_bear_neutral

def expected_edge_usdt(cfg: Config, side: str, entry_px: float, tp_px: Optional[float],
                       amount: float, leverage: int, funding_rate: Optional[float]) -> float:
    if not (entry_px and amount and leverage):
        return 0.0
    notional = entry_px * amount
    fee_cost = notional * cfg.taker_fee * 2.0
    fr = float(funding_rate or 0.0)
    fund_cost = notional * fr * (cfg.assume_hold_hours/8.0)
    exp_profit = 0.0
    if tp_px and tp_px > 0:
        if side == "buy":
            exp_profit = max(0.0, (tp_px - entry_px) * amount)
        else:
            exp_profit = max(0.0, (entry_px - tp_px) * amount)
    return exp_profit - (fee_cost + abs(fund_cost))
