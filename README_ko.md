
# Phemex 시그널 릴레이 서버 (Docker, Redis idempotency, Reconcile)

**목적**: TradingView → (이 서버) → Phemex 시그널 엔드포인트로 안전하게 중계합니다.  
중복/누락/슬리피지/수수료/최소주문단위/부분체결/포지션 보정을 서버에서 제어합니다.

## 구성
- FastAPI (`/tv-webhook`): TV/서드파티의 웹훅 수신
- Redis: idempotency(중복 방지) 키 저장 (TTL)
- ccxt: Phemex 주문/포지션 조회
- Docker: 앱/Redis 한 번에 구동

## 빠른 시작
```bash
# 1) .env 생성
cp .env.example .env
# PHEMEX_API_KEY/SECRET, PHEMEX_TESTNET, SYMBOL, RELAY_SHARED_SECRET 등 채우기

# 2) 실행
docker compose up -d --build

# 3) 헬스체크
curl http://localhost:8080/health
```

## TradingView 설정 (권장)
- **전략(strategy)** 로 Pine 작성(돈치안+EMA+ATR 등)
- 알림: **Only order fills** (주문 체결 시), Webhook URL을 `http://<공개주소>/tv-webhook`
- 메시지(JSON 템플릿 예)
```json
{
  "id": "{{strategy.order.id}}-{{timenow}}",
  "symbol": "{{ticker}}",
  "action": "{{strategy.order.action}}",
  "qty": "{{strategy.order.contracts}}",
  "price": "{{strategy.order.price}}",
  "marketPosition": "{{strategy.market_position}}",
  "prevMarketPosition": "{{strategy.prev_market_position}}",
  "marketPositionSize": "{{strategy.market_position_size}}",
  "prevMarketPositionSize": "{{strategy.prev_market_position_size}}",
  "signalToken": "YOUR_PUBLIC_SIGNAL_TOKEN",
  "timestamp": "{{timenow}}"
}
```
- 자리표시자(`{{...}}`)는 TV가 전송 시 실제 값으로 치환합니다.

## 엔드포인트
- `POST /tv-webhook` — 신호 수신
  - **헤더**: `X-Relay-Secret: <RELAY_SHARED_SECRET>` (선택/권장)
  - 바디(JSON): 위 TV 템플릿 또는 수동 JSON
- `GET /status` — 런타임 상태(최근 주문/포지션 요약)
- `GET /health` — 단순 헬스

## 주요 기능
- **Idempotency (Redis)**: `id` 키로 중복 신호를 15분간 차단
- **슬리피지 가드**: 기준가(`price`) 대비 현재가(`last`/`mark`) 편차가 `MAX_SLIPPAGE` 초과 시 차단
- **수수료/잔고 버퍼**: 발주 수량/노티오널에 `1 - FEE_BUFFER` 적용
- **스텝/최소주문 라운딩**: 거래소 메타(티크/스텝/최소비용)로 반올림
- **리컨실(reconcile)**:
  - 주문 후 N회 폴링: `fetch_order`/`fetch_open_orders` 로 **부분체결** 감지
  - 목표 포지션(target)과 실제 포지션(actual)이 차이 나면 **보정 주문**(추가/감소)
  - `reduceOnly` 엄격 적용(청산/역전 시)
- **심볼∼정규화**: 수신 JSON의 `symbol` 없으면 `.env`의 `SYMBOL` 사용

## 환경변수(.env)
```
PHEMEX_API_KEY=
PHEMEX_SECRET=
PHEMEX_TESTNET=true
SYMBOL=ETH/USDT:USDT

REDIS_URL=redis://redis:6379/0
IDEMPOTENCY_TTL=900

MAX_SLIPPAGE=0.004      # 0.4%
FEE_BUFFER=0.003        # 0.3%
RECONCILE_RETRIES=8
RECONCILE_INTERVAL=1.5  # sec

RELAY_SHARED_SECRET=changeme   # 요청 헤더 X-Relay-Secret과 일치해야 허용(없으면 비활성)
USE_MARK_PRICE=false           # 슬리피지 기준을 mark price로(기본 false=last price)
```

## 운영 팁
- 처음엔 **소액/테스트넷**으로 검증
- 이벤트(파월·CPI·SEC) 전엔 신규 진입 차단 옵션을 Relay에 추가하는 것도 방법
- 로깅/모니터링(프로메테우스, sentry 등) 연결 권장

## 보안
- 신호 토큰/거래소 키는 **공개 금지**. PR/공개 저장소 업로드 금지
- `RELAY_SHARED_SECRET` 필수 사용 권장
