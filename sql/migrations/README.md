# Schema Migrations

`sql/create_schema.sql` creates the initial schema (version 001). Every later change to a database that holds data goes into a new, numbered migration file in this folder. Each file is applied once and in order:

```text
V002__add_category_to_dim_product.sql
V003__partition_fact_sales_by_month.sql
```

Rules:

- Change the schema without losing data: use `ALTER TABLE ... ADD COLUMN`, backfill the values, and only then add constraints. Do not drop and recreate tables.
- Wrap each migration in `BEGIN; ... COMMIT;` so that it is applied completely or not at all.
- Never edit a migration that has already been applied; write a new one instead.
- `sql/dev/reset_schema.sql` deletes all data and is for development databases only.
