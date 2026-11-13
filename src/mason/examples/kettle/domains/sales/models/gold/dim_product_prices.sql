-- Each product's prices, and the dates each one applied. The current price has no valid_to.
SELECT
  product_id,
  product_name,
  price,
  CAST(effective_from AS DATE) AS valid_from,
  CAST(
    LEAD(effective_from) OVER (PARTITION BY product_id ORDER BY effective_from) AS DATE
  ) AS valid_to
FROM sales.silver.product_prices
