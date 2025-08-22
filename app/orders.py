from typing import Dict, Any
from .market import fetch_positions, current_position_side_qty
from .market import get_last_or_mark

def set_leverage_if_needed(ex, symbol: str, leverage: int):
    try:
        ex.set_leverage(int(leverage), symbol, params={"marginMode":"cross"})
    except Exception:
        pass

def create_market_order(ex, sym: str, side: str, amount: float, reduce_only: bool=False, limit_px: float=None):
    if limit_px is None:
        params = {"reduceOnly": reduce_only}
        return ex.create_order(sym, "market", side, amount, None, params)
    params = {"timeInForce": "IOC", "reduceOnly": reduce_only}
    return ex.create_order(sym, "limit", side, amount, limit_px, params)

def poll_order_completion(ex, symbol: str, order_id: str, retries: int, wait_s: float):
    last_order = None
    for _ in range(max(1, retries)):
        try:
            last_order = ex.fetch_order(order_id, symbol)
            if last_order and last_order.get("status") in ("closed","canceled"):
                break
        except Exception:
            pass
        import time; time.sleep(wait_s)
    return last_order

def reconcile_target(ex, sym: str, desired: Dict[str,Any]):
    pos = fetch_positions(ex, sym)
    cur_side, cur_qty = current_position_side_qty(pos)
    want_mp = desired["marketPosition"]
    want_sz = float(desired["size"])
    if want_mp == "flat":
        if cur_qty > 0:
            side = "sell" if cur_side == "long" else "buy"
            create_market_order(ex, sym, side, cur_qty, reduce_only=True)
        pos2 = fetch_positions(ex, sym)
        s2, q2 = current_position_side_qty(pos2)
        return {"current": {"side": s2, "qty": q2}, "target": {"side": "flat", "qty": 0}}
    target_side = "long" if want_mp == "long" else "short"
    if cur_side == target_side:
        diff = want_sz - cur_qty
        if abs(diff) > 0:
            side = "buy" if target_side == "long" else "sell"
            create_market_order(ex, sym, side, abs(diff), reduce_only=False)
    else:
        if cur_qty > 0:
            side_close = "sell" if cur_side == "long" else "buy"
            create_market_order(ex, sym, side_close, cur_qty, reduce_only=True)
        side_open = "buy" if target_side == "long" else "sell"
        if want_sz > 0:
            create_market_order(ex, sym, side_open, want_sz, reduce_only=False)
    pos3 = fetch_positions(ex, sym)
    s3, q3 = current_position_side_qty(pos3)
    return {"current": {"side": s3, "qty": q3}, "target": {"side": target_side, "qty": want_sz}}
