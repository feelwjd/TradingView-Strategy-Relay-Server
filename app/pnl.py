from typing import Optional
from .redis_utils import update_daily_pnl, get_loss_streak, set_loss_streak, start_cooldown
from .config import Config

def realized_pnl_simple(side: str, entry_px: float, exit_px: float, amount: float, taker_fee: float) -> float:
    pnl = (exit_px - entry_px) * amount if side == "buy" else (entry_px - exit_px) * amount
    pnl -= (entry_px*amount + exit_px*amount) * taker_fee
    return pnl

def after_exit_update(r, cfg: Config, strategy_name: str, pnl: float):
    cur, peak, dd = update_daily_pnl(r, pnl)
    if pnl < 0:
        streak = get_loss_streak(r, strategy_name) + 1
        set_loss_streak(r, strategy_name, streak)
        lim = cfg.loss_streak_limit_bull if strategy_name=="bull" else cfg.loss_streak_limit_bear
        mins= cfg.cooldown_min_bull if strategy_name=="bull" else cfg.cooldown_min_bear
        if streak >= lim:
            start_cooldown(r, strategy_name, mins)
    else:
        set_loss_streak(r, strategy_name, 0)
    return cur, peak, dd
