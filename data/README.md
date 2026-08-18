# 데이터 저장·접근 가이드

이 디렉터리는 Ethereum Mainnet의 Uniswap V3 WETH/USDT 0.05% pool 자료를
수집하고 검증하며 재생성하는 코드와 메타데이터를 담는다. 실제 데이터는 Git 저장소나
Conductor workspace 안이 아니라 기본적으로 `~/Data/uniswapdata`에 둔다. 이 Mac에서의
실제 경로는 `/Users/seungjun/Data/uniswapdata`다.

이 정책의 핵심은 다음과 같다.

- workspace를 archive하거나 삭제해도 실제 데이터는 남는다.
- 어느 checkout에서든 같은 외부 데이터 루트를 자동으로 찾는다.
- Git에는 코드, 고정 snapshot config, [`manifest.json`](manifest.json), 문서와 작은
  테스트 fixture만 둔다.
- raw 파일은 immutable이다. 기존 파일과 checksum이 다르면 덮어쓰지 않고 실패한다.
- BigQuery 수집은 명시한 project와 byte budget 없이는 실행하지 않는다.

출력 컬럼의 의미는 [`DATA_DICTIONARY.md`](DATA_DICTIONARY.md), 전체 연구 단계는
[`../flow.md`](../flow.md)를 참고한다.

## 1. 한 번만 준비하기

저장소 루트에서 Python 환경을 준비하고 데이터 구조를 만든다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r data/requirements.txt

python data/scripts/dataset.py init
python data/scripts/dataset.py status
```

기본 구조는 다음과 같다.

```text
~/Data/uniswapdata/
├── manifest.json
├── raw/bigquery/11b815ef_b12376751_b25779958/
│   ├── events/
│   └── block_daily/
├── processed/
├── derived/
├── external/
├── .runs/
└── .staging/
```

`manifest.json`은 Git에 있는 `data/manifest.json`과 동일한 사본이다. checkout 없이
전달본만으로도 파일별 row 수, 크기, SHA-256을 검증할 수 있다. `.runs/`는 새 수집과
가공의 로컬 실행 기록이고 `.staging/`은 검증 전 임시 파일이다.

데이터 루트 우선순위는 고정되어 있다.

1. CLI의 전역 `--data-root`
2. `UNISWAP_DATA_ROOT`
3. `Path.home() / "Data" / "uniswapdata"`

다른 위치가 필요하면 다음 중 하나를 사용한다. 전역 옵션은 subcommand 앞에 둔다.

```bash
export UNISWAP_DATA_ROOT=/Volumes/RESEARCH/uniswapdata
python data/scripts/dataset.py status

python data/scripts/dataset.py \
  --data-root /Volumes/RESEARCH/uniswapdata status
```

## 2. 현재 snapshot과 무결성

고정 dataset ID는 `11b815ef_b12376751_b25779958`이고 범위는 pool 생성 block을
포함하는 반열린 구간 `[12,376,751, 25,779,958)`이다.

| 항목 | Manifest 기준 |
| --- | ---: |
| Parquet 파일 | 128 |
| Events / block-daily rows | 14,337,903 / 1,932 |
| 전체 rows | 14,339,835 |
| Logical bytes | 1,005,914,760 |
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

## 3. 동업자에게 직접 전달하기

가장 단순한 방법은 외장 디스크나 `rsync` 가능한 로컬/마운트 디렉터리를 쓰는 것이다.
보내는 사람이 완전한 전달 디렉터리를 만든다.

```bash
python data/scripts/dataset.py verify
python data/scripts/dataset.py export \
  --destination /Volumes/TRANSFER/uniswapdata
```

받는 사람은 자신의 기본 외부 데이터 루트로 가져와 검증한다.

```bash
python data/scripts/dataset.py fetch \
  --source /Volumes/TRANSFER/uniswapdata
python data/scripts/dataset.py verify
```

네트워크 디렉터리도 같은 방식으로 사용할 수 있다. 먼저 `rsync`로 전달 디렉터리를
복제하고 `fetch`한다.

```bash
rsync -a --partial --info=progress2 \
  teammate:/srv/share/uniswapdata/ /Volumes/TRANSFER/uniswapdata/
python data/scripts/dataset.py fetch \
  --source /Volumes/TRANSFER/uniswapdata
```

`export`와 `fetch`는 manifest에 열거된 파일만 복사한다. 각 파일을 staging에 쓴 뒤
row 수·크기·SHA-256이 모두 맞을 때만 atomic rename한다. 중단 후 다시 실행하면 이미
검증된 파일은 건너뛴다. 목적지에 이름은 같지만 내용이 다른 파일이 있으면 절대
덮어쓰지 않는다.

## 4. BigQuery에서 재현하기

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

## 5. Processed·derived 재생성

전체 raw snapshot이 검증된 뒤 다음 명령으로 position 자료를 다시 만든다.

```bash
python data/scripts/dataset.py build
```

이 단계는 같은 resolver를 사용하므로 workspace 아래 `data/raw`를 만들지 않는다.
주요 출력은 다음과 같다.

| 외부 데이터 루트의 경로 | 내용 |
| --- | --- |
| `processed/position_links/pool_mint_nfpm_links.parquet` | pool Mint와 NFPM token ID의 연결 증거 |
| `processed/position_events/target_nfpm_events.parquet` | target token ID lifecycle |
| `processed/pool_daily/pool_daily.parquet` | 일별 swap·거래량·tick·liquidity |
| `processed/block_daily/block_daily.parquet` | 일별 base fee·gas utilization |
| `derived/positions/all_target_positions.parquet` | 식별된 전체 target positions |
| `derived/positions/clean_closed_positions.parquet` | 보수적인 clean-closed 표본 |

`is_clean_closed`는 단일 initial increase, 단일 full decrease, NFT mint와 burn, 소유권
이전 없음, 단일 tick range, snapshot 내부의 생성·인출·정산, 음수가 아닌 계산 fee를
모두 요구한다. 생애 fee는 아래 identity로 계산한다.

```text
fee_amount0 = sum(NFPM Collect.amount0) - sum(NFPM DecreaseLiquidity.amount0)
fee_amount1 = sum(NFPM Collect.amount1) - sum(NFPM DecreaseLiquidity.amount1)
```

외부 Oracle은 `external/` 아래에 놓고 종료 return을 계산할 수 있다.

```bash
python data/scripts/calculate_closed_returns.py \
  --prices "$HOME/Data/uniswapdata/external/oracle/weth_usdt.parquet"
```

## 6. Git과 Conductor 규칙

- 실제 raw, processed, derived, external 파일은 Git에 추가하지 않는다.
- Conductor의 **Files to copy**나 `.worktreeinclude`에 대용량 데이터 경로를 넣지 않는다.
- workspace에 symlink를 만들 필요도 없다. 새 workspace는 기본 외부 경로를 자동으로
  찾는다.
- workspace archive/delete, branch reset, repository 삭제 또는 이 변경의 revert가
  `/Users/seungjun/Data/uniswapdata`를 자동 삭제하지 않는다.
- 외부 데이터 루트를 지우는 작업은 별도의 명시적 운영 작업이며 저장소 스크립트는 이를
  수행하지 않는다.
- raw와 external은 immutable하게 보존하고, processed는 raw·config·code가 기록된 경우
  재생성할 수 있다. 논문에 사용한 derived output은 별도 백업한다.

Git에 들어가는 단일 `data/manifest.json`과 데이터 사전은 review 대상이다. 런타임
실행 기록은 외부 데이터 루트의 `.runs/`에 남는다. 일반 `git status`에는 대용량 파일이
나타나지 않아야 한다.

## 7. 연구 데이터 범위

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
