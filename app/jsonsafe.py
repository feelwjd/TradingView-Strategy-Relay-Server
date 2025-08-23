import math
from typing import Any, Optional

def jnum(x: Any) -> Optional[float]:
    """float로 변환 가능한 값만 반환, NaN/Inf는 None으로 치환"""
    try:
        f = float(x)
        return f if math.isfinite(f) else None
    except Exception:
        return None
