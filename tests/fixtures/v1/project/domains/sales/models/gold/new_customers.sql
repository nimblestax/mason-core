-- Each customer as they arrive, with their country's VAT.
SELECT c.customer_id, n.vat_rate
FROM STREAM(sales.silver.customers) AS c
JOIN sales.silver.countries AS n
  ON c.country = n.code
