WITH pool_created AS (
  SELECT
    block_number AS creation_block,
    block_timestamp AS creation_timestamp,
    LOWER(STRING(args[0])) AS factory_token0,
    LOWER(STRING(args[1])) AS factory_token1,
    CAST(STRING(args[2]) AS INT64) AS factory_fee_tier,
    CAST(STRING(args[3]) AS INT64) AS tick_spacing,
    LOWER(STRING(args[4])) AS factory_pool_address
  FROM `bigquery-public-data.blockchain_analytics_ethereum_mainnet_us.decoded_events`
  WHERE block_timestamp >= TIMESTAMP('2021-05-05')
    AND block_timestamp < TIMESTAMP('2021-05-06')
    AND block_number = 12376751
    AND address = '0x1f98431c8ad98523631ae4a59f267346ea31f984'
    AND event_signature = 'PoolCreated(address,address,uint24,int24,address)'
    AND LOWER(STRING(args[4])) = '0x11b815efb8f581194ae79006d24e0d814b7697f6'
), latest_decoded AS (
  SELECT MAX(block_number) AS latest_decoded_block
  FROM `bigquery-public-data.blockchain_analytics_ethereum_mainnet_us.decoded_events`
  WHERE block_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 14 DAY)
), cutoff AS (
  SELECT AS VALUE ARRAY_AGG(
    STRUCT(b.block_number, b.block_timestamp)
    ORDER BY b.block_number DESC
    LIMIT 1
  )[OFFSET(0)]
  FROM `bigquery-public-data.goog_blockchain_ethereum_mainnet_us.blocks` AS b
  CROSS JOIN latest_decoded AS d
  WHERE b.block_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 14 DAY)
    AND b.block_number <= d.latest_decoded_block - 64
)
SELECT
  p.*,
  d.latest_decoded_block,
  c.block_number AS snapshot_end_block_inclusive,
  c.block_timestamp AS snapshot_end_timestamp
FROM pool_created AS p
CROSS JOIN latest_decoded AS d
CROSS JOIN cutoff AS c
