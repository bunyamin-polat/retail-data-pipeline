-- =====================================================================
-- Online Retail Data Warehouse — schema DDL (PostgreSQL)
-- Star schema: 1 fact table (invoice lines) + 5 dimensions
--
-- Non-destructive and idempotent: only creates objects that do not exist
-- yet, so it is safe to run against a database that already holds data.
-- Later schema changes go into versioned migrations in sql/migrations/.
-- To wipe and rebuild a development database use sql/dev/reset_schema.sql.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS dw;
CREATE SCHEMA IF NOT EXISTS mart;

-- ---------------------------------------------------------------------
-- Customer information
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw.dim_customer (
    customer_key   SERIAL       PRIMARY KEY,
    customer_id    INTEGER      UNIQUE,            -- natural key (CustomerID); NULL = unknown
    customer_name  VARCHAR(100),                   -- not in source yet, reserved for CRM
    email          VARCHAR(150),
    first_purchase_date DATE,
    created_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- Guest / anonymous purchases (missing CustomerID) map to this row
INSERT INTO dw.dim_customer (customer_key, customer_id, customer_name)
VALUES (-1, NULL, 'Unknown customer')
ON CONFLICT (customer_key) DO NOTHING;

-- ---------------------------------------------------------------------
-- Inventory information (products / stock items)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw.dim_product (
    product_key     SERIAL       PRIMARY KEY,
    stock_code      VARCHAR(20)  NOT NULL UNIQUE,  -- natural key (StockCode)
    description     VARCHAR(255),                  -- most frequent description per code
    category        VARCHAR(100),
    stock_quantity  INTEGER      CHECK (stock_quantity >= 0),
    reorder_level   INTEGER      CHECK (reorder_level >= 0),
    is_non_product  BOOLEAN      NOT NULL DEFAULT FALSE, -- POST, M, BANK CHARGES, ...
    updated_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------
-- Seller information (company / sales channel)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw.dim_seller (
    seller_key   SERIAL       PRIMARY KEY,
    seller_name  VARCHAR(100) NOT NULL,
    channel      VARCHAR(50),                      -- e.g. 'Online store'
    country      VARCHAR(50)
);
-- Source data comes from a single online store
INSERT INTO dw.dim_seller (seller_key, seller_name, channel, country)
VALUES (1, 'Online Retail Store', 'Online store', 'United Kingdom')
ON CONFLICT (seller_key) DO NOTHING;
-- Keep the sequence ahead of the explicit key; never move it backwards
SELECT setval(pg_get_serial_sequence('dw.dim_seller', 'seller_key'),
              GREATEST((SELECT MAX(seller_key) FROM dw.dim_seller), 1));

-- ---------------------------------------------------------------------
-- Country (country is a property of the invoice, not the customer)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw.dim_country (
    country_key   SERIAL      PRIMARY KEY,
    country_name  VARCHAR(50) NOT NULL UNIQUE,
    region        VARCHAR(50)                      -- e.g. 'Western Europe', 'Non-EU'
);

-- ---------------------------------------------------------------------
-- Date dimension
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw.dim_date (
    date_key     INTEGER     PRIMARY KEY,          -- YYYYMMDD
    full_date    DATE        NOT NULL UNIQUE,
    year         SMALLINT    NOT NULL,
    quarter      SMALLINT    NOT NULL,
    month        SMALLINT    NOT NULL,
    month_name   VARCHAR(10) NOT NULL,
    day          SMALLINT    NOT NULL,
    day_of_week  SMALLINT    NOT NULL,             -- 1 = Monday ... 7 = Sunday
    day_name     VARCHAR(10) NOT NULL,
    is_weekend   BOOLEAN     NOT NULL
);

-- ---------------------------------------------------------------------
-- Transaction invoice information — one row per invoice line
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw.fact_sales (
    sales_key        BIGSERIAL     PRIMARY KEY,
    invoice_no       VARCHAR(10)   NOT NULL,       -- degenerate dimension (InvoiceNo)
    invoice_datetime TIMESTAMP     NOT NULL,       -- InvoiceDate
    date_key         INTEGER       NOT NULL REFERENCES dw.dim_date (date_key),
    customer_key     INTEGER       NOT NULL REFERENCES dw.dim_customer (customer_key),
    product_key      INTEGER       NOT NULL REFERENCES dw.dim_product (product_key),
    seller_key       INTEGER       NOT NULL DEFAULT 1 REFERENCES dw.dim_seller (seller_key),
    country_key      INTEGER       NOT NULL REFERENCES dw.dim_country (country_key),
    quantity         INTEGER       NOT NULL,       -- negative for cancellations / returns
    unit_price       NUMERIC(10,2) NOT NULL CHECK (unit_price > 0),
    line_total       NUMERIC(12,2) GENERATED ALWAYS AS (quantity * unit_price) STORED,
    is_cancelled     BOOLEAN       NOT NULL DEFAULT FALSE,
    loaded_at        TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_fact_sales_invoice  ON dw.fact_sales (invoice_no);
CREATE INDEX IF NOT EXISTS ix_fact_sales_date     ON dw.fact_sales (date_key);
CREATE INDEX IF NOT EXISTS ix_fact_sales_customer ON dw.fact_sales (customer_key);
CREATE INDEX IF NOT EXISTS ix_fact_sales_product  ON dw.fact_sales (product_key);
CREATE INDEX IF NOT EXISTS ix_fact_sales_country  ON dw.fact_sales (country_key);

-- ---------------------------------------------------------------------
-- Sales-invoice record in the standard column layout (InvoiceNo ... Country)
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.sales_invoice AS
SELECT f.invoice_no        AS "InvoiceNo",
       p.stock_code        AS "StockCode",
       p.description       AS "Description",
       f.quantity          AS "Quantity",
       f.invoice_datetime  AS "InvoiceDate",
       f.unit_price        AS "UnitPrice",
       c.customer_id       AS "CustomerID",
       co.country_name     AS "Country"
FROM dw.fact_sales   f
JOIN dw.dim_product  p  ON p.product_key  = f.product_key
JOIN dw.dim_customer c  ON c.customer_key = f.customer_key
JOIN dw.dim_country  co ON co.country_key = f.country_key;
