WITH pool_mints AS (
  SELECT
    block_number,
    block_timestamp,
    transaction_hash,
    transaction_index,
    log_index,
    CAST(STRING(args[2]) AS INT64) AS tick_lower,
    CAST(STRING(args[3]) AS INT64) AS tick_upper,
    STRING(args[4]) AS liquidity_raw,
    STRING(args[5]) AS amount0_raw,
    STRING(args[6]) AS amount1_raw
  FROM `bigquery-public-data.blockchain_analytics_ethereum_mainnet_us.decoded_events`
  WHERE block_timestamp >= TIMESTAMP('2025-03-01')
    AND block_timestamp < TIMESTAMP('2025-04-01')
    AND block_number >= 12376751
    AND block_number < 25779958
    AND address = '0x11b815efb8f581194ae79006d24e0d814b7697f6'
    AND event_signature = 'Mint(address,address,int24,int24,uint128,uint256,uint256)'
    AND LOWER(STRING(args[1])) = '0xc36442b4a4522e871399cd717abdd847ab11fe88'
), nfpm_increases AS (
  SELECT
    block_number,
    block_timestamp,
    transaction_hash,
    transaction_index,
    log_index,
    STRING(args[0]) AS token_id,
    STRING(args[1]) AS liquidity_raw,
    STRING(args[2]) AS amount0_raw,
    STRING(args[3]) AS amount1_raw
  FROM `bigquery-public-data.blockchain_analytics_ethereum_mainnet_us.decoded_events`
  WHERE block_timestamp >= TIMESTAMP('2025-03-01')
    AND block_timestamp < TIMESTAMP('2025-04-01')
    AND block_number >= 12376751
    AND block_number < 25779958
    AND address = '0xc36442b4a4522e871399cd717abdd847ab11fe88'
    AND event_signature = 'IncreaseLiquidity(uint256,uint128,uint256,uint256)'
)
SELECT
  n.token_id,
  n.block_number,
  n.block_timestamp,
  n.transaction_hash,
  n.transaction_index,
  p.log_index AS pool_mint_log_index,
  n.log_index AS nfpm_increase_log_index,
  p.tick_lower,
  p.tick_upper,
  n.liquidity_raw,
  n.amount0_raw,
  n.amount1_raw
FROM nfpm_increases AS n
JOIN pool_mints AS p
  ON n.transaction_hash = p.transaction_hash
  AND p.log_index < n.log_index
  AND p.liquidity_raw = n.liquidity_raw
  AND p.amount0_raw = n.amount0_raw
  AND p.amount1_raw = n.amount1_raw
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY n.transaction_hash, n.log_index
  ORDER BY p.log_index DESC
) = 1
ORDER BY block_number, transaction_index, nfpm_increase_log_index
