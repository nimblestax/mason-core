-- One row per order, with its customer and region.
SELECT
  o.order_id,
  o.ordered_at,
  CAST(o.ordered_at AS DATE) AS order_date,
  o.customer_id,
  c.customer_name,
  r.region_name,
  o.product_id,
  o.quantity,
  o.amount
FROM sales.silver.orders AS o
LEFT JOIN shared.gold.dim_customers AS c
  ON o.customer_id = c.customer_id
LEFT JOIN sales.silver.regions AS r
  ON o.region_code = r.region_code
