import math
from typing import Optional, Dict, Any, Tuple

def market_info(ex, symbol: str, fallback: str):
    if symbol not in ex.markets:
        ex.load_markets()
    sym = symbol if symbol in ex.markets else fallback
    m = ex.market(sym)
    prec = m.get("precision", {})
    limits = m.get("limits", {})
    return {
        "price_step": prec.get("price", None),
        "amount_step": prec.get("amount", None),
        "min_cost": (limits.get("cost") or {}).get("min", None),
        "min_qty": (limits.get("amount") or {}).get("min", None),
    }

def round_step(val: float, step: Optional[float]) -> float:
    if not step or step <= 0: return val
    return math.floor(val / step) * step

def get_last_or_mark(ex, symbol: str, use_mark: bool) -> float:
    t = ex.fetch_ticker(symbol)
    if use_mark:
        return float(t.get("info",{}).get("markPrice", t["last"]))
    return float(t["last"])

def fetch_positions(ex, symbol: str) -> Dict[str, Any]:
    try:
        poss = ex.fetch_positions([symbol])
        if poss:
            return poss[0]
    except Exception:
        pass
    return {}

def current_position_side_qty(pos: Dict[str,Any]) -> Tuple[str, float]:
    side = pos.get("side") or ""
    qty  = float(pos.get("contracts") or 0)
    return side, qty
