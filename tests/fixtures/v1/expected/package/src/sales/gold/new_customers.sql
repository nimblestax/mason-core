CREATE OR REFRESH STREAMING TABLE ${catalog_sales_gold}.${schema_sales_gold}.new_customers AS
-- Each customer as they arrive, with their country's VAT.
SELECT c.customer_id, n.vat_rate
FROM STREAM(${catalog_sales_silver}.${schema_sales_silver}.customers) AS c
JOIN ${catalog_sales_silver}.${schema_sales_silver}.countries AS n
  ON c.country = n.code
