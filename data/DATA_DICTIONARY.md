# Pipeline data dictionary

모든 `*_raw` 정수는 Ethereum 원단위의 10진 문자열이다. uint128/uint256을
`float64`로 변환하지 않는다. WETH는 18 decimals, USDT는 6 decimals다.

## Raw snapshot

| 파일군 | 의미 |
| --- | --- |
| `position_seeds/*.parquet` | 고정 pool core Mint와 NFPM Increase를 연결해 얻은 target tokenId와 range |
| `events/*.parquet` | 고정 pool event와 target tokenId의 NFPM lifecycle만 포함한 월별 records |
| `block_daily/*.parquet` | BigQuery에서 월별로 계산한 일별 block count, base fee, gas utilization |

모든 raw query는 `selected_pool.json`의 반개구간
`[start_block, end_block_exclusive)`와 월별 UTC timestamp partition 조건을 동시에
적용한다.

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
