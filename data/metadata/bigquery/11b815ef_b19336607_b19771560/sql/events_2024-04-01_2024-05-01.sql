SELECT
  block_number,
  block_timestamp,
  transaction_hash,
  transaction_index,
  log_index,
  address,
  TO_JSON_STRING(topics) AS topics_json,
  data,
  removed
FROM `bigquery-public-data.goog_blockchain_ethereum_mainnet_us.logs`
WHERE block_timestamp >= TIMESTAMP('2024-04-01')
  AND block_timestamp < TIMESTAMP('2024-05-01')
  AND block_number >= 19336607
  AND block_number < 19771560
  AND removed IS NOT TRUE
  AND (
    (
      address = '0x11b815efb8f581194ae79006d24e0d814b7697f6'
      AND topics[SAFE_OFFSET(0)] IN (
      '0x98636036cb66a9c19a37435efc1e90142190214e8abeb821bdba3f2990dd4c95',
      '0x7a53080ba414158be7ec69b987b5fb7d07dee101fe85488f0853ae16239d0bde',
      '0x0c396cd989a39f4459b5fa1aed6a9a8dcdbc45908acfd67e028cd568da98982c',
      '0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67',
      '0x70935338e69775456a85ddef226c395fb668b63fa0115f5f20610b388e6ca9c0'
      )
    )
    OR
    (
      address = '0xc36442b4a4522e871399cd717abdd847ab11fe88'
      AND topics[SAFE_OFFSET(0)] IN (
      '0x3067048beee31b25b2f1681f88dac838c8bba36af25bfb2b7cf7473a5847e35f',
      '0x26f6a048ee9138f2c0ce266f322cb99228e8d619ae2bff30c67f8dcf9d2377b4',
      '0x40d0efd1a53d60ecbf40971b9daf7dc90178c3aadc7aab1765632738fa8b8f01',
      '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
      )
    )
  )
ORDER BY block_number, transaction_index, log_index
