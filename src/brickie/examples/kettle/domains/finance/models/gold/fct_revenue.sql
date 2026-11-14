-- Revenue per day and region, from the orders the sales domain exports.
SELECT
  d.date_day,
  o.region_code,
  SUM(o.amount) AS revenue,
  COUNT(*) AS orders
FROM sales.silver.orders AS o
JOIN shared.gold.dim_date AS d
  ON CAST(o.ordered_at AS DATE) = d.date_day
GROUP BY d.date_day, o.region_code
