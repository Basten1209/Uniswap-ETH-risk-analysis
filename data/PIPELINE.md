# WETH/USDT Uniswap V3 데이터 수집 파이프라인

이 파이프라인의 수집 대상은 다음 pool 하나로 고정한다.

| 항목 | 값 |
| --- | --- |
| Network | Ethereum Mainnet |
| Pair | WETH/USDT |
| Fee tier | 0.05% (`500`) |
| Pool | `0x11b815efb8f581194ae79006d24e0d814b7697f6` |
| V3 Factory | `0x1f98431c8ad98523631ae4a59f267346ea31f984` |
| NFPM | `0xc36442b4a4522e871399cd717abdd847ab11fe88` |

Uniswap V3는 2021-05-05에 Ethereum Mainnet에 출시되었으므로 2021년 자료가
존재한다. 그러나 수집 시작일을 출시일이나 임의의 4년 전으로 정하지 않는다. Factory의
해당 pool `PoolCreated` block부터, 실행 시 BigQuery에서 확인되는 최신 finalized
decoded-event snapshot까지 수집한다.

**수집 범위와 연구 표본 범위는 다르다.** 먼저 가능한 전체 history를 보존하고,
clean-position 수·보유기간·결측·시장 국면을 EDA한 뒤 분석 기간과 cohort를 별도
analysis config로 정한다. 원자료를 다시 받지 않고도 연구 범위를 바꿀 수 있다.

대용량 파일과 Git 규칙은 [`STORAGE_POLICY.md`](STORAGE_POLICY.md)를 따른다.

## 실행 결과 요약

| 단계 | 실행 파일 | 얻는 결과 |
| --- | --- | --- |
| Pool 검증·snapshot 고정 | `prepare_fixed_pool.py` | Factory identity, 생성 block/time, 최신 cutoff block, `selected_pool.json` |
| 원시자료 수집 | `collect_bigquery.py` | 고정 pool events, 이 pool의 NFPM tokenId lifecycle, 일별 block/gas 자료 |
| Position 재구성 | `build_clean_positions.py` | tokenId lifecycle, clean-closed 표본, 생애 fee, pool/gas 일별 자료 |
| 종료 return | `calculate_closed_returns.py` | fee-inclusive LP return과 HODL 대비 return |

외부 Oracle과 무위험수익률은 이 BigQuery 수집에 포함되지 않는다. 그 두 자료를 제외한
IL, LVR, PL 및 종료 return의 position-level 온체인 입력을 만든다.

## 1. 환경 준비

저장소 루트에서 실행한다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r data/requirements.txt

gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_PROJECT_ID

cp data/config/fixed_pool.example.json data/config/fixed_pool.local.json
```

`fixed_pool.local.json`의 `project`를 실제 Google Cloud project ID로 바꾼다. Billing을
연결하지 않은 BigQuery Sandbox project도 사용할 수 있다. credential JSON이나 access
token은 config와 Git에 넣지 않는다.
`gcloud`가 설치되어 있지 않다면 Google Cloud CLI를 먼저 설치하거나, 접근 권한이 있는
service account 파일의 **경로만** `GOOGLE_APPLICATION_CREDENTIALS`로 설정한다.

대용량 자료는 외장 SSD 또는 별도 볼륨에 둔다.

외장 디스크 없이 workspace 내부의 Git 제외 경로를 기본 저장소로 사용한다.

```bash
DATA_ROOT=data
mkdir -p "$DATA_ROOT"
```

`data/raw`, `data/processed`, `data/derived`, `data/external`은 `.gitignore`
대상이다. 코드·문서·작은 provenance metadata만 Git에서 관리한다.

## 2. 고정 pool 검증과 최신 snapshot 생성

이 단계는 pool 주소를 선택하지 않는다. 고정 주소가 canonical Factory의 WETH/USDT
0.05% pool인지 검증하고 정확한 생성 block을 가져온다. 또한 최근 decoded-events에서
최신 block을 확인하고 기본 64 blocks를 제외한 finalized cutoff를 고정한다.

먼저 무료 dry run으로 처리량을 확인한다.

```bash
python data/scripts/prepare_fixed_pool.py \
  --config data/config/fixed_pool.local.json
```

출력된 `estimated_bytes_processed`를 예산과 비교한 뒤 실행한다.

```bash
python data/scripts/prepare_fixed_pool.py \
  --config data/config/fixed_pool.local.json \
  --execute \
  --maximum-bytes-billed YOUR_BYTE_LIMIT
```

결과:

- `data/config/selected_pool.json`: pool/token/fee 검증 결과와 정확한
  `[start_block, end_block_exclusive)` snapshot
- `data/metadata/pool_snapshot/prepare_fixed_pool.sql`: 실행 SQL
- `data/metadata/pool_snapshot/{plan,run}.json`: 비용 추정, job ID, cutoff provenance

나중에 최신 snapshot으로 원자료를 새로 받을 때만 `--replace-snapshot`을 명시한다.
기존 raw snapshot을 덮어쓰지는 않는다.

## 3. 다운로드 방법

### 무료 한도에 맞춘 현재 shard 분할

전체 범위의 dry-run은 약 2,494 GiB이므로 한 Sandbox 월 한도에 들어오지 않는다.
현재 workspace에서는 다음 최신 shard를 수집한다.

- local recent: `[22,820,674, 25,779,958)`, 2025-07-01부터 snapshot 끝까지
- teammate historical: `[12,376,751, 22,820,674)`, pool 생성부터 2025-07-01까지

두 범위는 반열린 구간이므로 블록 중복과 누락이 없다. 팀원에게는
`data/config/selected_pool_historical_handoff.json`과 이 문서를 전달하고, 실행할 때
본인의 quota project를 `--project`로 지정하도록 한다. shard별 clean-closed 연구표본은
해당 shard 안에서 최초 mint와 최종 close가 모두 관찰된 token ID로 제한한다. 경계를
가로지르는 포지션까지 분석하려면 두 shard의 position seed를 합친 뒤 NFPM 이벤트를
다시 회수해야 한다.

### 방법 A — 월별 Parquet을 로컬 또는 외장 SSD에 저장

현재 코드가 처음부터 끝까지 자동화하는 기본 방법이다. BigQuery Sandbox에서는
Cloud-side 저장공간을 쓰지 않는 이 방식을 권장한다. 먼저 모든 월별 쿼리를 dry run한다.

```bash
python data/scripts/collect_bigquery.py \
  --config data/config/selected_pool_recent.json \
  --data-root "$DATA_ROOT" \
  --metadata-root data/metadata
```

전체 예상 처리량을 확인한 뒤 총 dry-run byte 수 이상의 budget을 주고 실행한다.

```bash
python data/scripts/collect_bigquery.py \
  --config data/config/selected_pool_recent.json \
  --data-root "$DATA_ROOT" \
  --metadata-root data/metadata \
  --execute \
  --budget-bytes YOUR_TOTAL_BYTE_LIMIT
```

수집기는 다음의 2단계를 사용한다.

1. 고정 pool의 core `Mint`와 같은 transaction의 NFPM `IncreaseLiquidity`를 정확한
   liquidity·amount·log 순서로 연결하여 이 pool의 tokenId만 찾는다.
2. pool events와 그 tokenId들의 NFPM Increase/Decrease/Collect/Transfer만 월별로
   받는다.

따라서 canonical NFPM의 모든 pool 자료를 내려받지 않는다. 월별 파일은 immutable이며
중단 후 다시 실행하면 이미 완료된 파일을 건너뛴다.

### 방법 B — BigQuery `EXPORT DATA`로 GCS에 직접 저장

로컬 연결이나 용량이 불안하면 `data/metadata/bigquery/.../sql/`의 월별 SQL을
destination table 또는 `EXPORT DATA`의 `SELECT`로 사용해 GCS Parquet shard를 만든다.
tokenId parameter 때문에 position seed를 먼저 materialize한 뒤 server-side join해야
한다. 이 방식은 대량 수집에 가장 견고하지만 GCS bucket과 사용자 dataset 권한이
추가로 필요하다. Billing 없는 Sandbox에서는 저장공간·기능 제약 때문에 방법 A를 먼저
사용한다. 예시는 [`STORAGE_POLICY.md`](STORAGE_POLICY.md)에 있다.

### 방법 C — BigQuery destination table 후 `bq extract`

월별 결과를 expiration이 설정된 사용자 BigQuery table에 저장한 뒤 `bq extract`로
GCS Parquet을 만들 수 있다. 쿼리 재시도와 공유는 쉽지만 중간 table 저장비용이 든다.

세 방법 모두 `selected_pool.json`의 동일한 block snapshot을 사용해야 한다.

## 4. 실제 다운로드 결과

`RUN_ID`는 pool 앞 8자리와 정확한 block 범위를 포함한다.

```text
$DATA_ROOT/raw/bigquery/RUN_ID/
├── position_seeds/  # 고정 pool Mint와 연결된 tokenId 근거
├── events/          # 고정 pool + 해당 tokenId의 NFPM lifecycle
└── block_daily/     # 일별 block/base-fee/gas 집계

data/metadata/bigquery/RUN_ID/
├── sql/             # 실행한 월별 parameterized SQL
├── query_plans/     # 실행 전 처리량과 전체 budget
└── query_runs/      # job ID, row 수, byte 수, SHA-256
```

`events`에는 다음 자료가 있다.

| Contract | Events | 용도 |
| --- | --- | --- |
| 고정 pool | Initialize, Mint, Burn, Swap, Collect | 가격/tick/liquidity 경로, 거래량, pool-position 연결 |
| NFPM의 target tokenId만 | Transfer, IncreaseLiquidity, DecreaseLiquidity, Collect | 소유권, 예치, 인출, 수령액, 생애 fee |

전체 Ethereum block 원본을 받지 않고 BigQuery에서 일별 gas regime으로 집계해 파일
용량을 줄인다. 정확한 event ordering에는 pool/NFPM events의 block,
transaction index, log index가 보존된다.

## 5. clean-closed position 재구성

```bash
python data/scripts/build_clean_positions.py \
  --config data/config/selected_pool.json \
  --data-root "$DATA_ROOT" \
  --metadata-root data/metadata
```

`is_clean_closed`는 다음을 모두 만족하는 보수적 표본이다.

1. 고정 pool과 연결된 `IncreaseLiquidity` 한 번
2. `DecreaseLiquidity` 한 번으로 전 liquidity 제거
3. NFT 생성 한 번과 burn 한 번
4. 중간 소유권 이전 없음
5. 한 개의 tick range
6. 생성·인출·최종 정산이 수집 snapshot 내부
7. 계산된 두 토큰 fee가 음수가 아님

생애 fee는 다음처럼 계산한다.

```text
fee_amount0 = sum(NFPM Collect.amount0) - sum(NFPM DecreaseLiquidity.amount0)
fee_amount1 = sum(NFPM Collect.amount1) - sum(NFPM DecreaseLiquidity.amount1)
```

결과:

| 파일 | 내용 |
| --- | --- |
| `processed/position_links/pool_mint_nfpm_links.parquet` | pool Mint↔tokenId 연결 증거 |
| `processed/position_events/target_nfpm_events.parquet` | target tokenId 전체 lifecycle |
| `derived/positions/all_target_positions.parquet` | 식별된 모든 canonical NFPM position |
| `derived/positions/clean_closed_positions.parquet` | clean-closed 후보, 예치·원금·총 fee·range·기간 |
| `processed/pool_daily/pool_daily.parquet` | 일별 Swap 수·거래량·tick·active liquidity |
| `processed/block_daily/block_daily.parquet` | 일별 base fee·gas utilization |
| `data/metadata/processing/build_clean_positions_qc.json` | 표본 수, 제외 사유, output hash |

Parquet은 `$DATA_ROOT`, 작은 QC metadata만 저장소 아래에 생긴다.

## 6. EDA 뒤 연구 표본 범위 결정

이 수집 config에는 “연구 시작일/종료일”이 없다. `clean_closed_positions.parquet`로
다음을 먼저 EDA한다.

- 일·월별 신규/종료 position 수와 clean share
- holding period와 position size 분포
- fee, tick range, 거래량, 변동성의 시계열 coverage
- Oracle 결측과 LVR 계산에 필요한 가격 경로 해상도
- 시작·종료 경계에서 잘리는 position 수

그 뒤 분석 기간, 최소 보유기간, cohort 빈도, outlier rule을 별도의 versioned analysis
config로 고정한다. 동일한 position subset과 valuation date에서 IL, LVR, PL, LP return을
비교해야 한다.

## 7. 외부 Oracle과 종료 return

Oracle CSV/Parquet은 다음 컬럼을 사용한다.

```csv
timestamp,token0_price_usdt,token1_price_usdt
2024-01-01T00:00:00Z,2500.12,1.0001
```

```bash
python data/scripts/calculate_closed_returns.py \
  --config data/config/selected_pool.json \
  --data-root "$DATA_ROOT" \
  --metadata-root data/metadata \
  --prices "$DATA_ROOT/external/oracle/weth_usdt.csv" \
  --max-price-age-seconds 60
```

`derived/returns/clean_closed_returns.parquet`에는 생애 fee,
`lp_total_return_close_marked`, `lp_excess_return_vs_hodl_close`,
`fee_return_on_initial_wealth`, `il_return_vs_hodl_fee_exclusive`가 생긴다. 정확한
position 내부 일별 fee-inclusive return에는 fee-growth state replay가 추가로 필요하지만,
종료 position cohort의 IL/LVR/PL/return 대표값 시계열은 이 자료로 구성할 수 있다.

## 8. 내가 직접 실행하려면 필요한 것

다음 네 가지가 준비되면 이 workspace에서 dry run부터 실제 다운로드까지 실행할 수 있다.

1. **Google Cloud project ID** — billing 없는 BigQuery Sandbox project도 가능하다.
2. **Application Default Credentials** — 이 Mac/Conductor 환경에서
   `gcloud auth application-default login`을 완료하거나 service account 경로를 환경변수로
   설정한다. credential 내용을 채팅이나 Git에 붙이지 않는다.
3. **저장 위치** — 쓰기 가능한 외장 SSD 절대경로 또는 GCS bucket URI와 충분한 용량.
4. **비용 승인 한도** — 먼저 dry run 결과를 보고 pool snapshot query와 전체 수집 query의
   maximum bytes를 각각 승인한다.

선택적으로 finality를 기본 64 blocks가 아닌 값으로 쓸지, 로컬 Parquet과 GCS 중 어느
방식을 canonical raw 저장소로 쓸지도 알려주면 된다. 연구 분석기간은 지금 제공할 필요가
없으며 EDA 후 정한다.

BigQuery Sandbox의 무료 한도는 다운로드 파일 크기가 아니라 매월 처리한 query bytes로
계산된다. 서로 다른 Google 계정이나 project를 하나의 작업처럼 사용해 무료 한도를
우회하지 않는다. 한 project의 dry-run 합계를 기준으로 월별 작업량을 정하고, 한도에
도달하면 다음 월에 immutable collection을 이어서 실행한다.

## 공식 근거

- [Uniswap V3 Ethereum Mainnet launch — 2021-05-05](https://blog.uniswap.org/launch-uniswap-v3)
- [Uniswap V3 Factory `PoolCreated` interface](https://github.com/Uniswap/v3-core/blob/main/contracts/interfaces/IUniswapV3Factory.sol)
- [Google Cloud Ethereum Mainnet BigQuery examples](https://docs.cloud.google.com/blockchain-analytics/docs/example-ethereum)
