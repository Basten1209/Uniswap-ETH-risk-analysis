SELECT
  block_number,
  block_timestamp,
  transaction_hash,
  transaction_index,
  log_index,
  address,
  event_signature,
  TO_JSON_STRING(args) AS args_json
FROM `bigquery-public-data.blockchain_analytics_ethereum_mainnet_us.decoded_events`
WHERE block_timestamp >= TIMESTAMP('2021-12-01')
  AND block_timestamp < TIMESTAMP('2022-01-01')
  AND block_number >= 12376751
  AND block_number < 25779958
  AND (
    (
      address = '0x11b815efb8f581194ae79006d24e0d814b7697f6'
      AND event_signature IN (
      'Initialize(uint160,int24)',
      'Mint(address,address,int24,int24,uint128,uint256,uint256)',
      'Burn(address,int24,int24,uint128,uint256,uint256)',
      'Swap(address,address,int256,int256,uint160,uint128,int24)',
      'Collect(address,address,int24,int24,uint128,uint128)'
      )
    )
    OR
    (
      address = '0xc36442b4a4522e871399cd717abdd847ab11fe88'
      AND (
        (
          event_signature IN (
          'IncreaseLiquidity(uint256,uint128,uint256,uint256)',
      'DecreaseLiquidity(uint256,uint128,uint256,uint256)',
      'Collect(uint256,address,uint256,uint256)'
          )
          AND STRING(args[0]) IN UNNEST(@target_token_ids)
        )
        OR
        (
          event_signature = 'Transfer(address,address,uint256)'
          AND STRING(args[2]) IN UNNEST(@target_token_ids)
        )
      )
    )
  )
ORDER BY block_number, transaction_index, log_index
