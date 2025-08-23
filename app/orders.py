# app/orders.py
import time
from typing import Optional, Dict, Any
from fastapi import HTTPException
from .market import fetch_positions, current_position_side_qty

def set_leverage_if_needed(ex, sym: str, leverage: int | None, cfg=None):
    lev = int(leverage or (getattr(cfg, "lev_default", 5)))
    params = {"marginMode": "cross"}
    # 참고: set_position_mode는 main에서 ensure_position_mode가 처리
    try:
        ex.set_leverage(lev, sym, params=params)
    except Exception:
        pass

def _infer_pos_side_for_phemex(side: str, reduce_only: bool) -> Optional[str]:
    """
    Phemex hedge 모드에서 posSide(Long/Short)를 추론.
    - 진입(증가): buy→Long, sell→Short
    - 청산(reduceOnly=True): sell→Long(롱 청산), buy→Short(숏 청산)
    """
    s = (side or "").lower()
    if reduce_only:
        return "Long" if s == "sell" else ("Short" if s == "buy" else None)
    return "Long" if s == "buy" else ("Short" if s == "sell" else None)

def create_market_order(
    ex,
    sym: str,
    side: str,                 # "buy" | "sell"
    amount: float,
    reduce_only: bool = False,
    limit_px: float | None = None,
    cfg=None                   # ← 여기 추가
):
    """
    Phemex hedge 모드면 posSide를 자동으로 부여.
    """
    params = {"reduceOnly": bool(reduce_only)}

    # hedge 모드면 posSide 필수 (Phemex)
    hedged = bool(getattr(cfg, "phemex_hedged", False)) if cfg is not None else False
    if hedged:
        # buy → Long, sell → Short
        params["posSide"] = "Long" if side.lower() == "buy" else "Short"

    if limit_px is None:
        return ex.create_order(sym, "market", side, amount, None, params)
    else:
        params["timeInForce"] = "IOC"
        return ex.create_order(sym, "limit", side, amount, limit_px, params)

def poll_order_completion(ex, sym: str, order_id: str, retries: int, wait_s: float):
    """주문 체결/취소까지 폴링."""
    last_order = None
    tries = max(1, int(retries or 1))
    delay = float(wait_s or 1.0)
    for _ in range(tries):
        try:
            last_order = ex.fetch_order(order_id, sym)
            if last_order and str(last_order.get("status", "")).lower() in ("closed", "canceled"):
                break
        except Exception:
            pass
        time.sleep(delay)
    return last_order

def reconcile_target(ex, sym: str, desired: Dict[str, Any]):
    """
    target 모드: marketPosition/size로 포지션을 맞춤.
    hedged 여부는 create_market_order가 해결.
    """
    pos = fetch_positions(ex, sym)
    cur_side, cur_qty = current_position_side_qty(pos)

    want_mp = desired["marketPosition"]  # 'long' | 'short' | 'flat'
    want_sz = float(desired["size"])

    if want_mp == "flat":
        if cur_qty and cur_qty > 0:
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
        if cur_qty and cur_qty > 0:
            side_close = "sell" if cur_side == "long" else "buy"
            create_market_order(ex, sym, side_close, cur_qty, reduce_only=True)
        side_open = "buy" if target_side == "long" else "sell"
        if want_sz > 0:
            create_market_order(ex, sym, side_open, want_sz, reduce_only=False)

    pos3 = fetch_positions(ex, sym)
    s3, q3 = current_position_side_qty(pos3)
    return {"current": {"side": s3, "qty": q3}, "target": {"side": target_side, "qty": want_sz}}


# app/orders.py (발췌/추가)

def ensure_position_mode(ex, cfg):
    """
    Phemex 포지션 모드(원웨이/헤지) 정합을 맞추고,
    ccxt 헬퍼들이 참조할 hedged 옵션을 세팅한다.
    - 실패해도 예외로 죽지 않게 best-effort.
    """
    # 1) ccxt 옵션에 hedged 플래그 세팅 (create_market_order에서 posSide 결정에 사용)
    try:
        ex.options = {**getattr(ex, "options", {}), "hedged": bool(cfg.phemex_hedged)}
    except Exception:
        pass

    # 2) 거래소에 실제 포지션 모드 적용 시도 (ccxt 버전에 따라 방식 다름)
    try:
        # ccxt 표준: True=hedge, False=oneway
        ex.set_position_mode(bool(cfg.phemex_hedged))
    except Exception:
        # 일부 구현은 키워드 필요
        try:
            ex.set_position_mode(hedged=bool(cfg.phemex_hedged))
        except Exception:
            # 일부 버전/계정권한에서는 미지원 → 무시
            pass
