import json
from typing import Any, Dict

def parse_comment_field(raw: Any) -> Dict[str, Any]:
    """TradingView 'comment'가 dict 또는 JSON-string이든 안전하게 dict로 변환."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {}
