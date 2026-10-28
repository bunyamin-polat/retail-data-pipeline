# Infrastructure Requirements — On-Premises Data Platform

> **Scope.** This document lists the infrastructure required to run the **target** architecture described in [architecture.md](architecture.md) in production. The current release of the pipeline needs only one machine with Python 3.12, because SQLite stands in for the warehouse.

## 1. Constraints and Assumptions

- **No cloud:** all storage and processing run on company-owned hardware in the company's server room or data centre.
- **Central SQL repository:** a single PostgreSQL data warehouse that every employee can access, with permissions set by role.
- **Workload:** nightly batch ETL, BI dashboards, ad-hoc SQL queries, and Python analytics and data mining.
- **Users:** about 50–100 employees, of whom about 10–20 run queries at the same time. *(Assumed; adjust to actual headcount.)*

## 2. Requirements by Workflow Stage

Each stage below matches a step in the data architecture ([architecture.md](architecture.md)).

### Stage 1: Data Sources and Ingestion

- **Objective:** move invoice data reliably from the order system into the platform.
- **Requirements:**
  - Scheduled batch export of invoice data as CSV or Excel, delivered over **SFTP** to the landing zone.
  - Schema validation on arrival: required columns and data types.
  - **Idempotent** loads, so re-running a job never duplicates records. Incremental loads replace data per `InvoiceNo`, and every load runs in a single transaction.
  - Retry on failure; malformed files are moved to a quarantine folder.
  - TLS for data in transit; a least-privilege service account that can only read from the source.
- **Infrastructure:** ETL server (4–8 cores, 16 GB RAM), Python 3.12, pandas.

### Stage 2: Landing Zone (Raw Storage)

- **Objective:** keep durable, unchanged copies of every source file for audit and replay.
- **Requirements:**
  - Files are organised by source and date (`/data/raw/<source>/YYYY-MM-DD/`) and never modified after arrival.
  - Raw files are kept for at least **2 years**, then moved to the archive on the NAS.
  - Access is restricted to data engineers; the disks are encrypted.
- **Infrastructure:** about 500 GB SSD on the ETL server, plus the backup NAS for the archive.

### Stage 3: Staging and Transformation (ETL)

- **Objective:** validate, clean and conform the data according to the business rules.
- **Requirements:**
  - Cleaning rules:
    - Reject rows with missing required fields, unparseable dates or malformed numbers; bad source values never stop a run.
    - Remove credit invoices (`InvoiceNo` starting with "C").
    - Remove the non-product codes `M`, `D`, `C2` and `POST`.
    - Remove rows with no `CustomerID`.
    - Reject rows where `Quantity` or `UnitPrice` is zero or negative.
    - Remove exact duplicate rows.
  - Every rejected row is kept in a reject table together with its reason, and the number of rejected rows per reason is reported after each run.
  - Automated data-quality tests: row counts, NULL checks, `Quantity > 0`, `UnitPrice > 0`.
  - Orchestration as a dependency graph: `extract → stage → transform → load → test`.
  - Schema changes managed as versioned SQL migrations in Git, so they can be rolled back.
  - Credentials stored in Airflow Connections or a `.env` file, never in code.
- **Infrastructure:** Apache Airflow on the ETL server; the `stg` schema in PostgreSQL.

### Stage 4: Data Warehouse (Central SQL Repository)

- **Objective:** host the star schema (`dw`) and the final view `mart.sales_invoice`, which returns the standard sales-invoice columns `InvoiceNo, StockCode, Description, Quantity, InvoiceDate, UnitPrice, CustomerID, Country`.
- **Requirements:**
  - Primary keys, foreign keys and CHECK constraints in the database; indexes on the foreign keys.
  - Partitioning of the fact table by month and materialized views for frequently used queries.
  - A **streaming replica** for high availability; nightly backups plus continuous WAL archiving.
  - Role-based access control, TLS connections and disk encryption.
- **Infrastructure:** DB primary and standby servers (8 cores, 32 GB RAM, NVMe SSD in RAID 1 each), PostgreSQL 16 or later, and PgBouncer.

### Stage 5: Analytics and Presentation

- **Objective:** give employees fast, self-service access to the data.
- **Requirements:**
  - ODBC/JDBC connectivity for SQL clients; single sign-on through LDAP or Active Directory.
  - BI dashboards that read the `mart` views; pre-aggregated tables, such as daily and country totals, for speed.
  - Python notebooks for data mining, such as Apriori market-basket analysis and RFM customer segmentation.
  - Data freshness target: **daily**, with the nightly load finishing before 07:00.
- **Infrastructure:** BI and analytics server (8 cores, 32 GB RAM) running Metabase or Superset and JupyterHub.

### Stage 6: Security, Privacy and Compliance (all stages)

- **Requirements:**
  - Least-privilege roles and quarterly access reviews.
  - Multi-factor authentication on the VPN.
  - Encryption at rest (LUKS) and in transit (TLS).
  - Masking of customer identifiers in views that do not need them.
  - Access logs that cannot be altered (`pgaudit`) and GDPR-compliant retention and deletion.

### Stage 7: Monitoring and Operations (all stages)

- **Requirements:**
  - Central, structured logs from every ETL step.
  - Dashboards showing job run times, row counts, data freshness, database load and disk usage.
  - Alerts with runbooks for failed loads and failed quality checks.
  - Documentation: a data dictionary and an onboarding guide.
- **Infrastructure:** Prometheus and Grafana; a Git repository for code, migrations and documentation.

## 3. Data Volume and Growth Estimate

| Item | Current | Planning basis (5 years) |
| --- | --- | --- |
| Source records | ~540k invoice lines/year (≈ 24 MB Excel) | ×3 business growth plus new sources (CRM, inventory, web logs) |
| Warehouse size (data + indexes) | ~0.3 GB/year | ~10 GB |
| Raw file archive (landing zone) | ~50 MB/year | ~1 GB |
| Backups (30-day retention + WAL) | — | ~150 GB |

The data volume is small, so the hardware is sized for **reliability, concurrency and growth headroom**, not raw volume. Storage needs are dominated by backups and logs.

## 4. Server Roles and Hardware

| # | Server | Role | CPU | RAM | Storage |
| --- | --- | --- | --- | --- | --- |
| 1 | **DB server (primary)** | PostgreSQL 16 data warehouse (`stg`, `dw`, `mart`) | 8 cores | 32 GB | 2 × 1 TB NVMe SSD, RAID 1 |
| 2 | **DB server (standby)** | Streaming replica, for failover and read-only reporting | 8 cores | 32 GB | 2 × 1 TB NVMe SSD, RAID 1 |
| 3 | **ETL & orchestration server** | Python ETL, Apache Airflow, landing zone, Git | 4–8 cores | 16 GB | 500 GB SSD |
| 4 | **BI & analytics server** | Metabase or Superset, JupyterHub for analysts | 8 cores | 32 GB | 500 GB SSD |
| 5 | **Backup server / NAS** | `pg_dump` and WAL archive, raw-file archive | 4 cores | 8 GB | 4 × 4 TB HDD, RAID 6 |

- Servers 3 and 4 can run as **virtual machines** on one physical host (VMware ESXi or Proxmox) to cut hardware cost. The database servers should stay on dedicated hardware.
- **Minimum viable setup** (pilot or small team): one server with 8 cores, 32 GB RAM and 1 TB SSD in RAID 1, running everything in Docker containers, plus an external NAS for backups.

## 5. Software Stack (open source, self-hosted)

| Layer | Software |
| --- | --- |
| Operating system | Ubuntu Server 24.04 LTS |
| Database | PostgreSQL 16 or later, with streaming replication |
| Connection pooling | PgBouncer |
| ETL | Python 3.12 (pandas, SQLAlchemy, psycopg) |
| Orchestration | Apache Airflow |
| BI / reporting | Metabase or Apache Superset |
| Analytics | JupyterHub, scikit-learn, mlxtend |
| Containers | Docker / Docker Compose |
| Version control | Gitea or GitLab CE |
| Monitoring | Prometheus, Grafana, postgres_exporter |

## 6. Network and Security

- **Network:** 1 Gbps internal LAN (10 Gbps between the DB and backup servers is recommended). The platform sits in its own **VLAN** behind the company firewall and is not exposed to the internet.
- **Remote access:** employees outside the office connect through the company **VPN** only.
- **Authentication:** employees log in with their existing company accounts through **LDAP or Active Directory**, used for both PostgreSQL and the BI tool.
- **Authorisation:** role-based access in the database (`role_reader` → `mart` only; `role_analyst` → `dw` and `mart`; `role_engineer` → all schemas).
- **Encryption:** TLS for all database and BI connections; disk encryption (LUKS) on the database and backup servers.
- **GDPR:** customer identifiers are restricted to authorised roles, every access is logged with `pgaudit`, and the company has a documented data-retention policy.

## 7. Backup, Availability and Disaster Recovery

| Requirement | Solution |
| --- | --- |
| Daily backup | Nightly `pg_dump` to the backup server, kept for 30 days |
| Point-in-time recovery | Continuous WAL archiving; **RPO ≤ 15 min** (at most 15 minutes of data can be lost) |
| High availability | Streaming replica (server 2) with manual or Patroni failover; **RTO ≤ 1 hour** (service restored within 1 hour) |
| Off-site copy | A weekly encrypted backup copied to a second company site or stored offline (tape or disk) — no cloud |
| Restore test | A restore from backup is tested every month |
| Power | UPS on all servers, plus a generator if the server room has one |

## 8. Operations and Monitoring

- **Monitoring:** Grafana dashboards for CPU, RAM, disk, database connections, slow queries, replication lag and ETL run status.
- **Alerting:** e-mail or Teams alerts when an ETL run fails, a data-quality check fails, disk usage exceeds 80%, or replication lag grows.
- **Maintenance:** weekly `VACUUM ANALYZE`, monthly OS and security patching, and a quarterly review of capacity growth.
- **Staff:** one data engineer (owns the pipelines and the warehouse) plus part-time support from the IT or system administration team (hardware, network, backups).

## 9. Scalability Path

1. **Grow vertically:** add RAM and SSD capacity to the database server (enough for many years at the current volume).
2. **Partition** `fact_sales` by month and use **materialized views** for heavy dashboards.
3. **Add read replicas** for BI traffic if query concurrency grows.
4. If the data reaches the terabyte scale, consider an on-premises columnar engine (for example **ClickHouse** or **Greenplum**) alongside PostgreSQL.
