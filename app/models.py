from typing import Dict, Any, Optional, Tuple, Union
from pydantic import BaseModel

class TVPayload(BaseModel):
    id: Optional[str] = None
    symbol: Optional[str] = None
    side: Optional[str] = None
    action: Optional[str] = None
    qty: Optional[float] = None
    amount: Optional[float] = None
    contracts: Optional[float] = None
    price: Optional[float] = None
    marketPosition: Optional[str] = None
    marketPositionSize: Optional[float] = None
    leverage: Optional[int] = None
    reduceOnly: Optional[bool] = None
    timestamp: Optional[str] = None
    relaySecret: Optional[str] = None
    comment: Optional[Any] = None            # ← str 또는 dict 모두 허용
    strategy: Optional[str] = None           # ← TV가 보낸 strategy 태그도 받기
    # sizing overrides
    sizing: Optional[str] = None
    riskPct: Optional[float] = None
    allocPct: Optional[float] = None

    class Config:
        extra = "allow"  # ← 알려지지 않은 필드가 와도 422 발생하지 않게