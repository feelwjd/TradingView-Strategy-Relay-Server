import json, math
from typing import Dict, Any, Optional
from app.parsers import parse_comment_field
from fastapi import APIRouter, Request, HTTPException
from .models import TVPayload
from .config import Config
from .logging_utils import log as logf, redact
from .symbols import tv_to_ccxt_symbol, normalize_symbol_for_exchange
from .market import fetch_positions, current_position_side_qty, market_info, round_step, get_last_or_mark
from .redis_utils import idempotency_check, is_cooldown, daily_dd_blocked, save_open_entry
from .sizing import compute_amount_server
from .regime import get_regime, fetch_phemex_funding_rate
from .risk_gate import slippage_guard, regime_alloc_and_lev, expected_edge_usdt
from .orders import set_leverage_if_needed, create_market_order, poll_order_completion, reconcile_target
from .pnl import realized_pnl_simple, after_exit_update

router = APIRouter()

def json_sanitize(obj):
    try:
        _ = json.dumps(obj); return obj
    except Exception:
        def clean(x):
            if isinstance(x, float):
                if math.isfinite(x): return x
                return None
            if isinstance(x, dict):
                return {k: clean(v) for k,v in x.items()}
            if isinstance(x, list):
                return [clean(v) for v in x]
            return x
        return clean(obj)

def symbol_from_payload(cfg: Config, payload: Dict[str,Any]) -> str:
    tv_sym = payload.get("symbol") or payload.get("ticker")
    ccxt_sym = tv_to_ccxt_symbol(str(tv_sym)) if tv_sym else None
    return ccxt_sym or cfg.symbol_fallback

def side_from_payload(payload: Dict[str,Any]) -> Optional[str]:
    action = (payload.get("side") or payload.get("action") or "").lower()
    if action in ("buy","long"): return "buy"
    if action in ("sell","short"): return "sell"
    return None

def desired_target_from_payload(payload: Dict[str,Any]) -> Dict[str,Any]:
    mp  = (payload.get("marketPosition") or "").lower()
    mps = payload.get("marketPositionSize")
    qty = payload.get("qty") or payload.get("amount") or payload.get("contracts")
    if mp in ("long","short","flat") and mps is not None:
        return {"mode":"target", "marketPosition": mp, "size": float(mps)}
    sd = side_from_payload(payload)
    if sd and qty is not None:
        return {"mode":"delta", "side": sd, "amount": float(qty)}
    if sd and qty is None:
        return {"mode":"delta", "side": sd, "amount": None}
    return {"mode":"none"}

@router.get("/health")
def health(request: Request):
    app = request.app
    return {"ok": True, "uptime_s": __import__("time").time()-app.state.app_start}

@router.get("/status")
def status(request: Request):
    app = request.app
    cfg = app.state.cfg; ex = app.state.ex; ex_regime = app.state.ex_regime
    sym = cfg.symbol_fallback
    try:
        pos = fetch_positions(ex, sym)
    except Exception:
        pos = {}
    regime, meta = get_regime(cfg, app.state.ex, ex_regime, cfg.symbol_fallback, "BTC/USDT:USDT")
    resp = {
        "trade": {"exchange": "phemex", "testnet": cfg.trade_testnet, "symbol": sym},
        "regime_source": {"exchange": cfg.regime_exchange, "testnet": cfg.regime_testnet},
        "position": {
            "side": pos.get("side"),
            "qty": pos.get("contracts"),
            "entry": pos.get("entryPrice"),
            "unrealizedPnl": pos.get("unrealizedPnl"),
        },
        "regime": regime,
        "regime_meta": meta,
    }
    return json_sanitize(resp)

@router.post("/tv-webhook")
def tv_webhook(payload: TVPayload, request: Request):
    app = request.app
    cfg = app.state.cfg; ex = app.state.ex; ex_regime = app.state.ex_regime
    r   = app.state.r; logger = app.state.logger

    client_ip = getattr(request.client, "host", "unknown")
    if cfg.relay_shared_secret and payload.relaySecret != cfg.relay_shared_secret:
        logf(logger, cfg.log_json, "auth_failed", ip=client_ip, body=redact(payload.model_dump(exclude_none=True)))
        raise HTTPException(status_code=401, detail="unauthorized")

    data = payload.model_dump(exclude_none=True)
    tv_id = data.get("id")
    logf(logger, cfg.log_json, "webhook_received",
         ip=client_ip, id=tv_id, symbol=data.get("symbol"), action=(data.get("action") or data.get("side")),
         qty=(data.get("qty") or data.get("amount") or data.get("contracts")), price=data.get("price"))

    if not idempotency_check(r, tv_id, cfg.idempotency_ttl):
        logf(logger, cfg.log_json, "ignored_duplicate", id=tv_id)
        return {"status": "duplicate_ignored", "id": tv_id}

    server_uid = __import__("uuid").uuid4().hex
    sym = symbol_from_payload(cfg, data)
    desired = desired_target_from_payload(data)
    if desired["mode"] == "none":
        r.delete(f"idemp:{tv_id}")
        logf(logger, cfg.log_json, "invalid_payload", id=tv_id, reason="missing_target_or_delta", body=redact(data))
        raise HTTPException(400, "payload must include action+qty or marketPosition+marketPositionSize")

    # Strategy detection
    strategy_name = (data.get("strategy") or "").lower()
    if not strategy_name:
        sd = side_from_payload(data)
        strategy_name = "bull" if sd == "buy" else ("bear" if sd == "sell" else "unknown")

    # Regime / global gates
    regime, reg_meta = get_regime(cfg, app.state.ex, ex_regime, cfg.symbol_fallback, "BTC/USDT:USDT")
    blocked, dd_meta = daily_dd_blocked(r, cfg.daily_max_dd_usdt)
    if blocked:
        r.delete(f"idemp:{tv_id}")
        logf(logger, cfg.log_json, "blocked_daily_dd", id=tv_id, meta=dd_meta)
        return {"status":"blocked_daily_dd", "meta": dd_meta}

    cd, until = is_cooldown(r, strategy_name)
    if cd:
        r.delete(f"idemp:{tv_id}")
        logf(logger, cfg.log_json, "blocked_cooldown", id=tv_id, strategy=strategy_name, until_ms=until)
        return {"status":"blocked_cooldown", "strategy":strategy_name, "until_ms": until}

    # Slippage guard
    ref_price = float(data.get("price") or 0.0)
    try:
        slippage_guard(cfg, ex, ref_price, sym)
        limit_px = None
    except HTTPException as e:
        if e.status_code == 409:
            px = get_last_or_mark(ex, sym, cfg.use_mark_price)
            band = 1.0 + (cfg.max_slippage if (data.get("action","").lower() in ("buy","long")) else -cfg.max_slippage)
            limit_px = px * band
        else:
            r.delete(f"idemp:{tv_id}")
            raise

    # Regime-based alloc / leverage
    alloc_by_regime, lev_by_regime = regime_alloc_and_lev(cfg, strategy_name, regime)
    if alloc_by_regime <= 0.0:
        r.delete(f"idemp:{tv_id}")
        logf(logger, cfg.log_json, "blocked_by_regime", id=tv_id, strategy=strategy_name, regime=regime, meta=reg_meta)
        return {"status":"blocked_by_regime", "strategy":strategy_name, "regime":regime, "meta":reg_meta}

    # leverage set
    set_leverage_if_needed(ex, sym, data.get("leverage") or lev_by_regime)

    # comment JSON
    comm = parse_comment_field(data.get("comment"))
    if "comment" in data:
        try: comm = json.loads(data["comment"])
        except: comm = {}

    # sizing
    sizing   = data.get("sizing")
    riskPct  = data.get("riskPct")
    allocPct = alloc_by_regime if data.get("allocPct") is None else data.get("allocPct")

    result: Dict[str,Any] = {"mode": desired["mode"], "server_uid": server_uid, "regime": regime, "regime_meta": reg_meta}
    order_id = None

    # get current pos (exit detection)
    pos = fetch_positions(ex, sym)
    cur_side, cur_qty = current_position_side_qty(pos)

    id_hint   = (data.get("id") or "").upper()
    mp        = (data.get("marketPosition") or "").lower()
    prev_mp   = (data.get("prevMarketPosition") or "").lower()
    side      = desired.get("side")

    looks_exit = (mp == "flat") or ("EXIT" in id_hint) or ((prev_mp == "long" and side == "sell") or (prev_mp == "short" and side == "buy"))
    if looks_exit:
        amt_for_exit = cur_qty
        if not (amt_for_exit and amt_for_exit > 0):
            logf(logger, cfg.log_json, "exit_no_position", symbol=sym, side=cur_side, qty=cur_qty)
            return {"status": "no_position_to_exit", "symbol": sym, "side": cur_side, "qty": cur_qty}
        mi = market_info(ex, sym, cfg.symbol_fallback)
        amt_for_exit = round_step(amt_for_exit, mi["amount_step"])
        side_exec = "sell" if cur_side == "long" else ("buy" if cur_side == "short" else side or "sell")
        order = create_market_order(ex, sym, side_exec, amt_for_exit, reduce_only=True)
        order_id = order.get("id")
        result["order"] = order
        if order_id:
            last = poll_order_completion(ex, sym, order_id, cfg.recon_retries, cfg.recon_wait)
            result["order_final"] = last
            exit_px = float((last or {}).get("average") or (last or {}).get("price") or 0.0) or get_last_or_mark(ex, sym, cfg.use_mark_price)
            # realized pnl approx
            snap = app.state.r.get(f"pos:{strategy_name}")
            pnl = None
            if snap:
                try:
                    import json as _json
                    rec = _json.loads(snap)
                    pnl = realized_pnl_simple(rec.get("side"), float(rec.get("entry") or 0.0), exit_px, float(rec.get("amount") or 0.0), cfg.taker_fee)
                except Exception:
                    pnl = None
                app.state.r.delete(f"pos:{strategy_name}")
            if pnl is not None:
                cur, peak, dd = after_exit_update(app.state.r, cfg, strategy_name, pnl)
                result["realized_pnl"] = pnl
                result["day_pnl"] = cur; result["day_peak"] = peak; result["day_dd"] = dd
        pos = fetch_positions(ex, sym)
        result["final_position"] = {"side": pos.get("side"), "qty": pos.get("contracts"), "entry": pos.get("entryPrice")}
        logf(logger, cfg.log_json, "webhook_processed_exit", id=tv_id, final_position=result["final_position"])
        return json_sanitize(result)

    # ENTRY/DELTA or TARGET flow
    try:
        if desired["mode"] == "delta":
            side = desired["side"]
            if cfg.server_sizing and desired.get("amount") is None:
                entry_px = float(data.get("price") or comm.get("entry") or 0.0)
                from .balance import fetch_equity_generic  # local import to avoid cycles
                amt = compute_amount_server(cfg, ex, sym, side, entry_px, comm, sizing, riskPct, allocPct, data.get("leverage") or lev_by_regime, fetch_equity_generic(ex, cfg))
            else:
                # use explicit amount (with fee buffer + rounding)
                mi = market_info(ex, sym, cfg.symbol_fallback)
                amt = desired["amount"] * (1.0 - cfg.fee_buffer)
                amt = round_step(amt, mi["amount_step"])
                if mi["min_qty"] and amt < mi["min_qty"]:
                    raise HTTPException(400, f"amount below min_qty: {amt} < {mi['min_qty']}")
                if amt <= 0:
                    raise HTTPException(400, "amount too small after buffer/rounding")

            entry_px = float(data.get("price") or get_last_or_mark(ex, sym, cfg.use_mark_price))
            tp_px    = float(comm.get("tp") or 0.0) if isinstance(comm, dict) else 0.0
            fr       = fetch_phemex_funding_rate(ex, sym)
            edge     = expected_edge_usdt(cfg, side, entry_px, tp_px if tp_px>0 else None, amt, int(data.get("leverage") or lev_by_regime), fr)
            if edge <= 0:
                app.state.r.delete(f"idemp:{tv_id}")
                logf(logger, cfg.log_json, "blocked_by_edge", id=tv_id, edge=edge, entry=entry_px, tp=tp_px, amount=amt, fr=fr)
                return {"status":"blocked_by_edge","edge":edge,"entry":entry_px,"tp":tp_px,"amount":amt,"fr":fr}

            ro = bool(data.get("reduceOnly", False))
            order = create_market_order(ex, sym, side, amt, reduce_only=ro, limit_px=limit_px)
            order_id = order.get("id")
            result["order"] = order
            if order_id:
                last = poll_order_completion(ex, sym, order_id, cfg.recon_retries, cfg.recon_wait)
                result["order_final"] = last
                filled_avg = float((last or {}).get("average") or (last or {}).get("price") or 0.0) or entry_px
                if not ro:  # open entry
                    save_open_entry(app.state.r, strategy_name, side, filled_avg, float(amt))

        elif desired["mode"] == "target":
            result["pre_position"] = fetch_positions(ex, sym)
            recon = reconcile_target(ex, sym, desired)
            result["reconcile"] = recon

        pos = fetch_positions(ex, sym)
        result["final_position"] = {"side": pos.get("side"), "qty": pos.get("contracts"), "entry": pos.get("entryPrice")}
        logf(logger, cfg.log_json, "webhook_processed", id=tv_id, uid=server_uid, final_position=result["final_position"])
        return json_sanitize(result)

    except Exception as e:
        app.state.r.delete(f"idemp:{tv_id}")
        logf(logger, cfg.log_json, "error_processing", id=tv_id, uid=server_uid, error=str(e))
        raise
