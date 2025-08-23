import json, re
from typing import Any, Dict

def parse_comment_field(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        # 1) 표준 JSON 시도
        try:
            return json.loads(s)
        except Exception:
            pass
        # 2) 키에 따옴표가 없는 유사-JSON 보정
        try:
            s2 = s.replace("'", '"')
            s2 = re.sub(r'(?<!")\b(entry|sl|tp|atr|kind|strategy)\b(?!")\s*:', r'"\1":', s2)
            return json.loads(s2)
        except Exception:
            return {}
    return {}
