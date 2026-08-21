# 데이터 저장·접근 가이드

이 디렉터리는 Ethereum Mainnet의 Uniswap V3 WETH/USDT 0.05% pool 자료를
수집하고 검증하며 재생성하는 코드와 메타데이터를 담는다. 대용량 artifact는 Git에
커밋하지 않고, 사용자가 선택한 별도의 데이터 루트에 저장한다.

이 정책의 핵심은 다음과 같다.

- repository checkout을 교체하거나 삭제해도 실제 데이터는 남는다.
- 어느 checkout에서든 같은 외부 데이터 루트를 자동으로 찾는다.
- Git에는 코드, 고정 snapshot config, [`manifest.json`](manifest.json), 문서와 작은
  테스트 fixture만 둔다.
- raw 파일은 immutable이다. 기존 파일과 checksum이 다르면 덮어쓰지 않고 실패한다.
- BigQuery 수집은 명시한 project와 byte budget 없이는 실행하지 않는다.

출력 컬럼의 의미는 [`DATA_DICTIONARY.md`](DATA_DICTIONARY.md), 전체 연구 단계는
[`../flow.md`](../flow.md)를 참고한다.

## 1. 데이터 디렉터리 설정

데이터 루트는 repository checkout 밖의 지속적인 로컬 디스크나 외장 디스크에 둔다.
임시 디렉터리, CI checkout, 자동으로 정리되는 workspace는 사용하지 않는다. 위치를
명시하려면 `UNISWAP_DATA_ROOT`를 설정한다.

macOS 또는 Linux 예시:

```bash
export UNISWAP_DATA_ROOT="${HOME}/Data/uniswapdata"
mkdir -p "${UNISWAP_DATA_ROOT}"
```

Windows PowerShell 예시:

```powershell
$env:UNISWAP_DATA_ROOT = "$HOME\Data\uniswapdata"
New-Item -ItemType Directory -Force $env:UNISWAP_DATA_ROOT
```

외장 디스크나 별도 볼륨을 사용한다면 해당 mount 경로를 지정한다.

```bash
export UNISWAP_DATA_ROOT="/path/to/persistent-storage/uniswapdata"
```

지속적으로 사용할 경로라면 환경변수 설정을 shell profile이나 개발환경의 로컬 설정에
추가한다. 개인별 절대 경로는 Git에 커밋하지 않는다.

데이터 루트 우선순위는 다음과 같다.

1. CLI의 전역 `--data-root`
2. `UNISWAP_DATA_ROOT`
3. 환경변수가 없을 때의 fallback: `Path.home() / "Data" / "uniswapdata"`

한 번의 명령에만 다른 위치를 사용하려면 전역 옵션을 subcommand 앞에 둔다.

```bash
python data/scripts/dataset.py \
  --data-root /path/to/persistent-storage/uniswapdata status
```

## 2. 환경 준비와 초기화

저장소 루트에서 Python 환경을 준비하고 데이터 구조를 만든다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r data/requirements.txt

python data/scripts/dataset.py init
python data/scripts/dataset.py status
```

초기화된 구조는 다음과 같다.

```text
<DATA_ROOT>/
├── manifest.json
├── raw/bigquery/11b815ef_b12376751_b25779958/
│   ├── events/
│   ├── block_daily/
│   └── transactions/
├── processed/
├── derived/
├── external/
├── .runs/
└── .staging/
```

`manifest.json`은 Git에 있는 `data/manifest.json`과 동일한 사본이다. checkout 없이
전달본만으로도 파일별 row 수, 크기, SHA-256을 검증할 수 있다. `.runs/`는 새 수집과
가공의 로컬 실행 기록이고 `.staging/`은 검증 전 임시 파일이다.

## 3. 현재 snapshot과 무결성

고정 dataset ID는 `11b815ef_b12376751_b25779958`이고 범위는 pool 생성 block을
포함하는 반열린 구간 `[12,376,751, 25,779,958)`이다.

| 항목 | Manifest 기준 |
| --- | ---: |
| Parquet 파일 | 192 |
| Events / block-daily / transaction rows | 14,337,903 / 1,932 / 103,561 |
| 전체 rows | 14,443,396 |
| Logical bytes | 1,011,093,566 |
| 허용 partial 파일 | 0 |

빠른 보유 현황은 `status`, 모든 Parquet footer·크기·hash 검사는 `verify`로 확인한다.

```bash
python data/scripts/dataset.py status
python data/scripts/dataset.py verify
```

`verify`가 성공하기 전에는 전달본이나 분석 입력을 완전한 snapshot으로 취급하지 않는다.
`data/manifest.json`은 과거 273개 분할 메타데이터의 128개 job ID, row 수, output hash,
처리·청구 bytes, maximum budget, SQL digest, QC, processing 결과와 폐기한 시도를 한 파일로
통합한다. Billing project 이름은 재현 provenance일 뿐 기본 실행값이 아니다.

## 4. 다른 연구자에게 직접 전달하기

가장 단순한 방법은 외장 디스크나 `rsync` 가능한 로컬/마운트 디렉터리를 쓰는 것이다.
보내는 사람이 완전한 전달 디렉터리를 만든다.

```bash
python data/scripts/dataset.py verify
python data/scripts/dataset.py export \
  --destination /path/to/transfer/uniswapdata
```

받는 사람은 자신의 기본 외부 데이터 루트로 가져와 검증한다.

```bash
python data/scripts/dataset.py fetch \
  --source /path/to/transfer/uniswapdata
python data/scripts/dataset.py verify
```

네트워크 디렉터리도 같은 방식으로 사용할 수 있다. 먼저 `rsync`로 전달 디렉터리를
복제하고 `fetch`한다.

```bash
rsync -a --partial --info=progress2 \
  researcher@example.org:/srv/share/uniswapdata/ /path/to/transfer/uniswapdata/
python data/scripts/dataset.py fetch \
  --source /path/to/transfer/uniswapdata
```

`export`와 `fetch`는 manifest에 열거된 파일만 복사한다. 각 파일을 staging에 쓴 뒤
row 수·크기·SHA-256이 모두 맞을 때만 atomic rename한다. 중단 후 다시 실행하면 이미
검증된 파일은 건너뛴다. 목적지에 이름은 같지만 내용이 다른 파일이 있으면 절대
덮어쓰지 않는다.

## 5. BigQuery에서 재현하기

Google credential은 파일이나 Git에 넣지 않는다. Application Default Credentials를
사용하고 billing/quota project는 실행 때마다 명시한다.

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

먼저 dry run으로 전체 처리량을 확인한다. `--budget-bytes`를 넘으면 실행 전 실패한다.

```bash
python data/scripts/dataset.py collect \
  --project YOUR_PROJECT_ID \
  --budget-bytes YOUR_TOTAL_BYTE_LIMIT \
  --dry-run
```

비용을 승인한 뒤에만 실제 수집을 실행한다.

```bash
python data/scripts/dataset.py collect \
  --project YOUR_PROJECT_ID \
  --budget-bytes YOUR_TOTAL_BYTE_LIMIT
```

수집기는 월별로 고정 pool log, canonical NFPM lifecycle log, 일별 block/gas 집계를
만든다. query는 `data/config/selected_pool.json`, collector code와 manifest의 SQL
SHA-256으로 재현한다. `decoded_events`에는 canonical NFPM `IncreaseLiquidity`가 빠진
실제 사례가 있어 lifecycle 원천으로 쓰지 않고 raw `logs` topic/data를 로컬에서
디코딩한다. 기존 raw month는 immutable하게 건너뛴다.

고정 pool의 Mint/Burn transaction sender는 별도 월별 query로 수집한다. 전체 실행이
성공하면 64개 transaction artifact를 repository와 runtime manifest에 등록한다.

```bash
python data/scripts/dataset.py collect-transactions \
  --project YOUR_PROJECT_ID \
  --budget-bytes YOUR_TOTAL_BYTE_LIMIT \
  --dry-run

python data/scripts/dataset.py collect-transactions \
  --project YOUR_PROJECT_ID \
  --budget-bytes YOUR_TOTAL_BYTE_LIMIT
```

각 월의 `maximum_bytes_billed`는 dry-run 추정치의 110%이며, 재실행 시에는 이미
완료된 query와 남은 query maximum을 합산해 전체 byte budget을 검사한다.

### 아직 보존된 job result 복구

이미 완료된 BigQuery job 결과가 보존되어 있다면 새 query를 만들지 않고 복구할 수
있다. 이 명령은 `jobs.get`과 기존 result read만 수행하며 `client.query`를 호출하지
않는다.

```bash
python data/scripts/dataset.py recover --project JOB_OWNER_PROJECT_ID
```

권한이 없거나 result가 만료되면 즉시 실패하고 owning Google 계정으로 인증하라고
알린다. 이때 `collect`로 대신 재실행하지 않는다. 별도 비용 승인을 받은 뒤에만 위의
dry-run/collect 절차로 진행한다.

## 6. Processed·derived 재생성

전체 raw snapshot이 검증된 뒤 다음 명령으로 position 자료를 다시 만든다.

```bash
python data/scripts/dataset.py build
```

이 단계는 같은 resolver를 사용하므로 repository 아래 `data/raw`를 만들지 않는다.
주요 출력은 다음과 같다.

| 외부 데이터 루트의 경로 | 내용 |
| --- | --- |
| `processed/position_links/pool_mint_nfpm_links.parquet` | pool Mint와 NFPM token ID의 연결 증거 |
| `processed/position_events/target_nfpm_events.parquet` | target token ID lifecycle |
| `processed/pool_daily/pool_daily.parquet` | 일별 swap·거래량·tick·liquidity |
| `processed/block_daily/block_daily.parquet` | 일별 base fee·gas utilization |
| `derived/positions/all_target_positions.parquet` | 식별된 전체 target positions |
| `derived/positions/clean_closed_positions.parquet` | 보수적인 clean-closed 표본 |
| `processed/transaction_senders.parquet` | Pool Mint/Burn transaction별 LP wallet과 호출 대상 |
| `processed/pool_liquidity_operations.parquet` | Pool Mint/Burn에 wallet·manager·NFPM 연결 정보를 결합한 operation |
| `derived/operation_pairs/all_pairs.parquet` | 동일 wallet·manager·range·liquidity를 FIFO로 연결한 전체 exact pair |
| `derived/operation_pairs/same_block_pairs.parquet` | EDA에서 JIT/MEV 후보군으로 분류하는 동일 block pair |
| `derived/operation_pairs/non_same_block_pairs.parquet` | pool 전 기간 risk 분석의 기본 표본 |
| `derived/operation_pairs/strict_pairs.parquet` | ambiguity와 중간 same-range operation까지 제거한 민감도 표본 |
| `derived/returns/non_same_block_pair_returns.parquet` | non-same-block pair의 observed realized fee와 fee-inclusive return |
| `external/rates/sofr_daily/` | Predictable Loss용 동결 SOFR calendar-day snapshot과 manifest |
| `derived/risk_metrics/v1/` | position lifetime, capital-weighted daily, 대표 position 경로와 run manifest |

operation-pair 자료는 다음 명령으로 재생성한다.

```bash
python data/scripts/dataset.py build-operation-pairs
```

현재 snapshot에서 `all_pairs`는 41,671개다. EDA는 전체 pair를 사용하되 동일 block에서
Mint와 Burn이 모두 발생한 30,865개를 `same_block_jit_mev_candidate`로 별도 보고한다.
이 분류는 연구의 operational proxy이며 행위자의 의도를 직접 입증하지 않는다. Pool
전체 기간의 primary risk 분석은 이 cohort를 제외한 `non_same_block_pairs` 10,806개를
사용한다. 추가 pair 품질 조건을 적용한 `strict_pairs`는 10,723개이며 sensitivity
analysis에 사용한다.

10,806개 non-same-block pair의 realized fee와 return은 다음 명령으로 재생성한다.

```bash
python data/scripts/dataset.py build-pair-returns
```

fee attribution은 연결이 일관된 경우 NFPM token ID를, 그렇지 않은 경우 Pool의
`(manager, tick_lower, tick_upper)` identity를 사용한다. 보유 중 실제 `Collect`는
realized fee이고, 종료 transaction에서는 matched `Burn` 뒤의 `Collect`에서 Burn
principal을 뺀 금액을 realized fee로 잡는다. 종료 `Collect`가 없으면 종료 시점에
실현된 fee를 0으로 기록하며, 이는 미수령 accrued fee가 0이라는 뜻이 아니다. fee는
종료 ETHUSDT 가격으로 평가하고 gas cost는 포함하지 않는다.

동일 fee identity의 보유 구간이 겹쳐 개별 `Collect`를 유일하게 귀속할 수 없는 11개
pair에는 비례 배분을 하지 않고 return dataset에서 제외한다. 제외 operation ID와 사유는
`.runs/processing/build_pair_returns_qc.json`에 기록한다. 따라서 현재 fee/return 출력과
분석 표본은 10,795개다. 이 중 기존의 보수적인 clean-closed 조건까지 충족한 548개에는
`fee_complete_exact = true`가 붙지만, 계산식은 나머지 포함 표본과 동일하다.

`is_clean_closed`는 단일 initial increase, 단일 full decrease, NFT mint와 burn, 소유권
이전 없음, 단일 tick range, snapshot 내부의 생성·인출·정산, 음수가 아닌 계산 fee를
모두 요구한다. 생애 fee는 아래 identity로 계산한다.

```text
fee_amount0 = sum(NFPM Collect.amount0) - sum(NFPM DecreaseLiquidity.amount0)
fee_amount1 = sum(NFPM Collect.amount1) - sum(NFPM DecreaseLiquidity.amount1)
```

외부 Oracle은 `external/` 아래에 놓고 종료 return을 계산할 수 있다. 현재 지원하는
표준 입력은 Binance spot ETHUSDT 1초봉을 UTC 월별 partition으로 정제한 dataset이다.

원본은 repository 밖의 지속적인 경로에 보존하고 다음 명령으로 변환한다. 출력 기본값은
`$UNISWAP_DATA_ROOT/external/oracle/binance_ethusdt_1s/`이다.

```bash
python data/scripts/prepare_binance_oracle.py \
  --source-root "$HOME/Data/Binance_ETHUSDT_1s"
```

각 월별 Parquet은 `timestamp`, `price`, `volume` 세 컬럼만 가진다. `timestamp`는
1초 candle의 UTC `open_time`, `price`는 `close`, `volume`은 USDT 단위
`quote_volume`이다. 원본에 없는 초는 미래 값을 사용하지 않고 직전 price로 채우며
volume은 0으로 둔다. 전체 보간 구간과 파일별 checksum은 Oracle dataset의
`manifest.json`에 기록된다.

SOFR는 분석 노트북에서 실시간으로 받지 않는다. 다음 명령을 한 번 실행해 effective-date
관측치를 calendar day로 forward-fill하고 hash가 있는 snapshot으로 고정한다.

```bash
python analysis/scripts/prepare_sofr.py
```

10,795개 return-comparable multi-block pair의 IL, external-price LVR, CEX QV
sensitivity, Predictable Loss와 차트 원자료는 다음 명령으로 재생성한다.

```bash
python analysis/scripts/build_risk_metrics.py
```

이 빌드는 fee와 gas를 세 위험지표에서 제외하고, event보다 정확히 1초 이전 Binance
가격과 exact pool `sqrt_price_x96`/blockchain log order를 사용한다. SOFR는 전체 WETH
inventory가 아니라 이미 누적된 PL replication gap에만 적용한다.

기존 결과를 전체 SHA-256까지 다시 검사하려면 다음 명령을 사용한다.

```bash
python data/scripts/prepare_binance_oracle.py \
  --source-root "$HOME/Data/Binance_ETHUSDT_1s" \
  --verify-only
```

종료 return 계산기는 단일 CSV/Parquet 가격 파일과 월별 Oracle 디렉터리를 모두
지원한다. 디렉터리 입력은 필요한 월만 순서대로 읽고, event timestamp와 같은 초의
candle은 아직 완료되지 않은 것으로 보아 엄격히 이전 초의 close를 사용한다.

```bash
python data/scripts/calculate_closed_returns.py \
  --prices "$UNISWAP_DATA_ROOT/external/oracle/binance_ethusdt_1s"
```

## 7. Git과 여러 checkout 운영

- 실제 raw, processed, derived, external 파일은 Git에 추가하지 않는다.
- worktree 복사 설정이나 workspace별 파일 복제 기능에 대용량 데이터 경로를 넣지 않는다.
- checkout마다 symlink를 만들 필요가 없다. 모든 checkout에서 같은
  `UNISWAP_DATA_ROOT`를 사용한다.
- branch reset이나 repository checkout 삭제는 외부 데이터 루트를 자동으로 삭제하지
  않는다.
- 외부 데이터 루트를 지우는 작업은 별도의 명시적 운영 작업이며 저장소 스크립트는 이를
  수행하지 않는다.
- raw와 external은 immutable하게 보존하고, processed는 raw·config·code가 기록된 경우
  재생성할 수 있다. 논문에 사용한 derived output은 별도 백업한다.

Git에 들어가는 단일 `data/manifest.json`과 데이터 사전은 review 대상이다. 런타임
실행 기록은 외부 데이터 루트의 `.runs/`에 남는다. 일반 `git status`에는 대용량 파일이
나타나지 않아야 한다.

## 8. 연구 데이터 범위

| Dimension | Fixed requirement |
| --- | --- |
| Network | Ethereum Mainnet |
| Protocol | Uniswap V3 |
| Pool | WETH/USDT 0.05%, `0x11b815ef…97f6` |
| Collection interval | `PoolCreated` block부터 고정 finalized snapshot까지 |
| Observation unit | 실제 on-chain LP position |
| Planned outcomes | Realized return, IL, LVR, PL, market-regime variables |

수집 범위와 연구 표본 범위는 다르다. 가능한 전체 history를 먼저 보존하고 clean-position
수, 보유기간, 결측과 시장 국면을 EDA한 다음 분석 기간·cohort·outlier rule을 별도
analysis config로 고정한다. 그래야 원자료를 다시 받지 않고도 연구 설계를 변경할 수
있다.
