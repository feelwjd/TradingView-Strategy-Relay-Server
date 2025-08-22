from fastapi import HTTPException
from typing import Optional, Dict, Any
from .config import Config
from .market import market_info, round_step, get_last_or_mark

def compute_amount_server(cfg: Config, ex, sym: str, side: str, entry: float, comm: Dict[str,Any],
                          sizing: Optional[str], riskPct: Optional[float], allocPct: Optional[float],
                          leverage: Optional[int], equity_fetcher) -> float:
    sizing_mode = (sizing or cfg.sizing_mode).lower()
    risk_pct    = float(riskPct) if riskPct is not None else cfg.risk_pct
    alloc_pct   = float(allocPct) if allocPct is not None else cfg.alloc_pct
    lev         = int(leverage) if leverage else cfg.lev_default

    equity = float(equity_fetcher())
    mi = market_info(ex, sym, cfg.symbol_fallback)
    last = get_last_or_mark(ex, sym, cfg.use_mark_price)
    px   = entry or last

    amt = 0.0
    if sizing_mode == "risk":
        stop = comm.get("sl")
        if stop is None:
            raise HTTPException(400, "risk sizing requires stop (comment.sl)")
        risk_usd = equity * risk_pct
        risk_per_unit = abs(px - float(stop))
        if risk_per_unit <= 0:
            raise HTTPException(400, "invalid stop/entry for risk sizing")
        amt = risk_usd / risk_per_unit
    elif sizing_mode == "notional":
        notional = equity * alloc_pct * lev
        amt = notional / px
    elif sizing_mode == "fixed":
        raise HTTPException(400, "fixed sizing requires explicit amount from payload")

    notional = amt * px
    max_notional = equity * lev * cfg.margin_buffer
    if notional > max_notional:
        amt = max_notional / px

    if equity <= 0:
        raise HTTPException(400, "equity_usdt_is_zero (check balance / code / account type)")

    notional = amt * px
    if notional < cfg.min_notional_usdt:
        raise HTTPException(400, f"computed notional too small: {notional:.4f} < {cfg.min_notional_usdt}")

    amt = amt * (1.0 - cfg.fee_buffer)
    amt = round_step(amt, mi["amount_step"])
    if mi["min_qty"] and amt < mi["min_qty"]:
        raise HTTPException(400, f"amount below min_qty: {amt} < {mi['min_qty']}")
    if amt <= 0:
        raise HTTPException(400, "computed amount <= 0")
    return amt
