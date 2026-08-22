# Pipeline data dictionary

모든 `*_raw` 정수는 Ethereum 원단위의 10진 문자열이다. uint128/uint256을
`float64`로 변환하지 않는다. WETH는 18 decimals, USDT는 6 decimals다.

## Raw snapshot

| 파일군 | 의미 |
| --- | --- |
| `events/*.parquet` | 고정 pool 핵심 event와 canonical NFPM lifecycle event를 담은 월별 raw logs |
| `block_daily/*.parquet` | BigQuery에서 월별로 계산한 일별 block count, base fee, gas utilization |
| `transactions/*.parquet` | 고정 pool Mint/Burn transaction의 block metadata, sender, 호출 대상 |

모든 raw query는 선택한 shard config의 반개구간
`[start_block, end_block_exclusive)`와 월별 UTC timestamp partition 조건을 동시에
적용한다. NFPM raw logs에는 다른 V3 pool의 token ID도 포함되며, processed layer에서
고정 pool `Mint`와 같은 transaction의 `IncreaseLiquidity`를 금액·유동성·log 순서로
연결해 target token ID만 결정한다.

## Operation-pair dataset

`processed/pool_liquidity_operations.parquet`은 Pool Mint/Burn에 transaction
sender를 `lp_wallet`, Pool event owner를 `manager_address`로 결합한다. Pair key는
`(lp_wallet, manager_address, tick_lower, tick_upper, abs(liquidity_raw))`이며 Burn을
가장 오래된 미사용 Mint와 FIFO로 연결한다.

| 파일·컬럼군 | 의미 |
| --- | --- |
| `all_pairs.parquet` | exact key로 연결된 전체 operation pair; EDA 분석 모집단 |
| `same_block_pairs.parquet` | entry와 exit의 block number가 같은 pair; JIT/MEV 후보 operational proxy |
| `non_same_block_pairs.parquet` | 동일 block pair를 제외한 primary full-period risk 표본 |
| `strict_pairs.parquet` | multi-block 조건에 ambiguity와 중간 same-range liquidity 제외를 추가한 sensitivity 표본 |
| `operation_id`, `entry_event_id`, `exit_event_id` | pair 및 재사용되지 않는 원천 Mint/Burn 식별자 |
| `lp_wallet`, `manager_address` | transaction sender와 Pool liquidity owner/manager |
| `tick_lower`, `tick_upper`, `liquidity_raw` | exact pair를 구성하는 range와 유동성 깊이 |
| `is_same_block` | Mint와 Burn의 block number가 같은지 여부 |
| `analysis_cohort` | `same_block_jit_mev_candidate` 또는 `multi_block_lp_position` |
| `entry_*`, `exit_*` | 양쪽 operation의 block, transaction, log 순서, timestamp, token amount |
| `holding_seconds` | block timestamp 차이; 같은 block에서는 event 순서가 있어도 0초 |
| `is_ambiguous`, `has_intervening_same_range_liquidity_event` | strict sensitivity 표본의 추가 제외 근거 |

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

## `non_same_block_pair_returns.parquet`

`derived/returns/non_same_block_pair_returns.parquet`은 10,806개 multi-block operation
pair 중 fee identity 구간이 겹치는 11개를 비례 배분 없이 제외한 10,795개
fee/return 분석 표본이다. 제외 operation ID와 사유는
`.runs/processing/build_pair_returns_qc.json`에 기록한다.

| 컬럼 | 의미 |
| --- | --- |
| `fee_analysis_included` | main output은 모두 `true`; build 단계의 포함 판정 증거 |
| `fee_exclusion_reason` | main output은 모두 null; 제외된 11개의 사유는 QC JSON에 기록 |
| `fee_attribution_source` | `nfpm_token` 또는 `pool_position`; Collect를 찾는 on-chain identity |
| `interim_collect_count` | entry 뒤부터 exit transaction 전까지 귀속된 실제 Collect 수 |
| `exit_collect_count` | matched Burn 뒤 같은 exit transaction에서 귀속된 Collect 수 |
| `exit_collect_observed` | 위 exit Collect가 관측되었는지 여부 |
| `exit_collect_covers_principal` | exit Collect가 두 token 모두의 matched Burn principal 이상인지 여부 |
| `realized_fee{0,1}_raw` | interim Collect 합계와 exit Collect에서 principal을 뺀 realized fee의 원단위 합계 |
| `fee_complete_exact` | 기존 보수적 clean-closed token과 직접 일치하는 검증 subset 표시; 별도 fee 계산식이 아님 |
| `token{0,1}_price_usdt_{entry,exit}` | 각 event timestamp보다 엄격히 이전인 Binance 1초 close |
| `initial_wealth_usdt` | entry token amounts를 entry 가격으로 평가한 예치 가치 |
| `principal_exit_value_usdt` | matched Burn token amounts를 exit 가격으로 평가한 가치 |
| `realized_fee_value_usdt` | 두 token의 realized fee를 exit 가격으로 평가한 가치 |
| `lp_exit_value_realized_fee_usdt` | exit principal과 realized fee의 합 |
| `hodl_exit_value_usdt` | 최초 예치 token을 그대로 보유했을 때의 exit 가치 |
| `lp_total_return_realized_fee` | `(LP exit value - initial wealth) / initial wealth` |
| `lp_excess_return_vs_hodl_realized_fee` | `(LP exit value - HODL exit value) / HODL exit value` |
| `fee_return_on_initial_wealth` | exit 가격으로 평가한 realized fee / initial wealth |
| `holding_days` | `holding_seconds / 86,400` |
| `realized_daily_log_return` | `log(1 + total return) / holding_days` |
| `realized_daily_return_geometric` | `exp(realized_daily_log_return) - 1` |
| `realized_daily_return_simple` | `total return / holding_days`; 단순 일할 환산 민감도 지표 |

종료 transaction의 Collect가 없을 때 `realized_fee{0,1}_raw`에는 그 시점에 새로
실현된 fee를 0으로 더한다. 이는 미수령 accrued fee를 추정하거나 0이라고 가정하는
처리가 아니다. 금액 컬럼은 gas cost를 제외하며 fee는 exit 가격으로 mark한다.

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

## SOFR snapshot

`external/rates/sofr_daily/sofr_daily.parquet`은 FRED SOFR effective-date 관측치를
분석기간의 UTC calendar day로 forward-fill한 고정 snapshot이다. `date`와 percent p.a.
단위의 `sofr_percent`만 저장하며, 같은 디렉터리의 `manifest.json`이 source, retrieval
time, coverage, row count, bytes와 SHA-256을 기록한다. PL에서는 일별
`1 + r/360`을 기준으로 partial day를 복리 보간하며 USD risk-free rate를 USDT의 proxy로
사용한다.

## Risk-measure outputs (`derived/risk_metrics/v1/`)

`position_lifetime_metrics.parquet`은 return dataset의 10,795개 operation을 그대로
보존하면서 다음 컬럼을 추가한다.

| 컬럼군 | 의미 |
| --- | --- |
| `pool_price_{entry,exit}_usdt` | event order 직전 exact `sqrt_price_x96` 상태 |
| `theoretical_{entry,exit}_{weth,usdt}` | range와 liquidity로 복원한 fee-exclusive inventory |
| `*_inventory_reconciliation_usdt` | 이론 inventory와 실제 Mint/Burn amount의 평가액 차이 |
| `il_signed_vs_hodl` | `(principal - HODL) / HODL`; 논문 표준 부호 |
| `il_loss_usdt`, `il_loss_on_initial` | `HODL - principal`; loss-positive dollar 및 initial-capital 비율 |
| `lvr_rebalancing_*` | 각 Swap inventory 변화를 strict-prior Binance 가격에서 거래한 self-financing gap; 실증값은 clipping하지 않음 |
| `lvr_qv_{1s,5s,1m}_*` | CEX 가격경로와 CEX in-range 판정의 non-negative QV sensitivity |
| `pl_convexity_cost_*` | 논문 용어 Convexity Cost: exact internal-price convexity gap의 합 |
| `pl_opportunity_cost_*` | 이미 발생한 PL gap에 SOFR를 적용한 Opportunity Cost |
| `pl_loss_*`, `pl_signed_*` | loss-positive `Convexity Cost + Opportunity Cost` 및 논문 부호의 음수 PL |
| `expected_pl_r0_30d_*` | 진입 전 30일 일별 변동성을 사용하는 기대식 robustness; primary realized PL이 아님 |

`capital_weighted_position_daily.parquet`은 각 UTC 날짜와 half-open lifetime이 겹치는
position을 `min(exit, day-end)`에서 평가한다. `*_usdt`는 해당 날짜 dollar numerator,
`capital_weighted_*_pct`는 `100 * numerator / sum(initial capital)`이다. 이것은 표본
구성이 변하는 사후 position-day 대표값이지 investable portfolio가 아니다.

`representative_positions.parquet`은 보유기간 ETH return 상·하위 25%와 전체 lifetime
하·상위 25%의 네 교집합에서 robust medoid로 선택한 operation과 선정 threshold를
기록한다. `representative_position_paths.parquet`은 1일 이하 position의 1초 grid,
장기 position의 1분 grid, 모든 Swap과 entry/exit를 합친 시계열이다. `row_kind`, exact
event order, 외부·내부가격, inventory, LP/HODL value, IL/LVR/PL 누적값을 포함한다.

`run_manifest.json`은 공식 버전, repository revision, 모든 input hash, 표본 수,
계산 convention, 대표 operation ID와 output별 row/bytes/hash를 기록한다.
