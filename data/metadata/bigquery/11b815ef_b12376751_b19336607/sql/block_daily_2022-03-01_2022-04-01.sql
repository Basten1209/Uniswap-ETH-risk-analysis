SELECT
  DATE(block_timestamp) AS date,
  COUNT(*) AS block_count,
  MIN(block_number) AS first_block,
  MAX(block_number) AS last_block,
  CAST(AVG(CAST(base_fee_per_gas AS BIGNUMERIC)) AS STRING) AS mean_base_fee_per_gas_wei,
  CAST(APPROX_QUANTILES(CAST(base_fee_per_gas AS BIGNUMERIC), 2)[OFFSET(1)] AS STRING) AS median_base_fee_per_gas_wei,
  CAST(AVG(CAST(gas_used AS BIGNUMERIC)) AS STRING) AS mean_gas_used,
  CAST(AVG(CAST(gas_limit AS BIGNUMERIC)) AS STRING) AS mean_gas_limit,
  CAST(AVG(SAFE_DIVIDE(CAST(gas_used AS BIGNUMERIC), CAST(gas_limit AS BIGNUMERIC))) AS STRING) AS mean_block_gas_utilization
FROM `bigquery-public-data.goog_blockchain_ethereum_mainnet_us.blocks`
WHERE block_timestamp >= TIMESTAMP('2022-03-01')
  AND block_timestamp < TIMESTAMP('2022-04-01')
  AND block_number >= 12376751
  AND block_number < 19336607
GROUP BY date
ORDER BY date
