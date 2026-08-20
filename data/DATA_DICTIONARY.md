# Pipeline data dictionary

모든 `*_raw` 정수는 Ethereum 원단위의 10진 문자열이다. uint128/uint256을
`float64`로 변환하지 않는다. WETH는 18 decimals, USDT는 6 decimals다.

## Raw snapshot

| 파일군 | 의미 |
| --- | --- |
| `events/*.parquet` | 고정 pool 핵심 event와 canonical NFPM lifecycle event를 담은 월별 raw logs |
| `block_daily/*.parquet` | BigQuery에서 월별로 계산한 일별 block count, base fee, gas utilization |

모든 raw query는 선택한 shard config의 반개구간
`[start_block, end_block_exclusive)`와 월별 UTC timestamp partition 조건을 동시에
적용한다. NFPM raw logs에는 다른 V3 pool의 token ID도 포함되며, processed layer에서
고정 pool `Mint`와 같은 transaction의 `IncreaseLiquidity`를 금액·유동성·log 순서로
연결해 target token ID만 결정한다.

## `clean_closed_positions.parquet`

| 컬럼군 | 의미 |
| --- | --- |
| `token_id`, `initial_owner` | NFPM position 식별자와 최초 NFT 수령자 |
| `tick_lower`, `tick_upper` | position price range |
| `entry_*` | target pool Mint/NFPM Increase 시점 |
| `exit_*` | 전 liquidity를 제거한 DecreaseLiquidity 시점 |
| `settlement_*` | 모든 owed token 정산 후 NFT burn 시점 |
| `liquidity_*_raw` | 증가, 감소, 잔여 liquidity |
| `deposit_amount{0,1}_raw` | IncreaseLiquidity에서 실제 투입된 토큰 |
| `withdraw_principal{0,1}_raw` | DecreaseLiquidity에서 산출된 원금 |
| `collected_amount{0,1}_raw` | 모든 NFPM Collect의 합계; 원금과 fee 포함 |
| `fee_amount{0,1}_raw` | Collect 합계에서 Decrease 원금을 뺀 생애 fee |
| `*_count`, `is_*`, `has_*` | clean-position 선정과 검증 증거 |

## `clean_closed_returns.parquet`

| 컬럼 | 의미 |
| --- | --- |
| `initial_wealth_usdt` | entry Oracle 가격으로 평가한 최초 예치가치 |
| `principal_exit_value_usdt` | exit 가격으로 평가한 종료 principal |
| `fee_exit_value_usdt` | exit 가격으로 평가한 생애 fee |
| `lp_exit_value_usdt` | principal과 fee의 합 |
| `hodl_exit_value_usdt` | 최초 예치 토큰을 그대로 보유한 exit 가치 |
| `lp_total_return_close_marked` | 초기 예치가치 대비 fee-inclusive LP return |
| `lp_excess_return_vs_hodl_close` | 논문 방식의 HODL 대비 fee-inclusive 초과수익률 |
| `il_return_vs_hodl_fee_exclusive` | fee 제외 principal의 HODL 대비 차이; 손실은 음수 |

## Binance ETHUSDT 1초 Oracle

`external/oracle/binance_ethusdt_1s/`에는 UTC 월별 Parquet과 변환
`manifest.json`이 있다. Binance spot ETHUSDT는 중앙화 거래소의 외부 reference
price이며 온체인 Oracle로 해석하지 않는다.

| 컬럼 | 타입·단위 | 의미 |
| --- | --- | --- |
| `timestamp` | `timestamp[us, UTC]` | 1초 candle의 `open_time`; 온체인 event에는 같은 초가 아닌 strict-prior 행을 연결 |
| `price` | `float64`, USDT/ETH | 해당 1초 candle의 `close`; 결측 초는 직전 관측값으로 forward-fill |
| `volume` | `float64`, USDT | 해당 초의 `quote_volume`; 결측으로 생성한 초는 0 |

출력은 최초 source timestamp부터 snapshot의 마지막 timestamp까지 정확히 1초 간격이며
null과 중복 timestamp를 허용하지 않는다. 보간 여부는 데이터 컬럼을 늘리지 않고
manifest의 월별 `imputed_rows`와 `gaps`에 기록한다.
