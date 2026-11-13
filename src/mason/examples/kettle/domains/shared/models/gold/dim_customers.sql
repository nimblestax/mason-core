-- Each customer as they are now. A customer who was deleted isn't here.
SELECT
  customer_id,
  name AS customer_name,
  email,
  city,
  region_code
FROM sales.silver.customers
WHERE __END_AT IS NULL
