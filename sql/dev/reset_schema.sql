-- =====================================================================
-- DEVELOPMENT ONLY — drops the dw and mart schemas with ALL their data,
-- then rebuilds them from create_schema.sql.
--
-- Refuses to run unless the caller confirms with the database name:
--   psql -d retail_dw_dev -v confirm_reset=retail_dw_dev -f sql/dev/reset_schema.sql
-- Never use this for production changes; write a migration instead.
-- =====================================================================

\set ON_ERROR_STOP on

\if :{?confirm_reset}
\else
    \echo 'Refusing to reset: pass -v confirm_reset=<database name>'
    \quit
\endif

SELECT current_database() = :'confirm_reset' AS confirmed \gset
\if :confirmed
\else
    \echo 'Refusing to reset: confirm_reset does not match the connected database'
    \quit
\endif

DROP SCHEMA IF EXISTS mart CASCADE;
DROP SCHEMA IF EXISTS dw   CASCADE;

\ir ../create_schema.sql
