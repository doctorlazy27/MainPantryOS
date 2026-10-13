# PantryOS: manual AWS deployment with an existing pgAdmin database

This guide uses **EC2 for the application**, **RDS PostgreSQL for the
database**, and your existing PostgreSQL database as the source to migrate.
It is the simplest path for a presentation tomorrow.

## Important decision

You have two databases:

- **Source**: your existing PostgreSQL database shown in pgAdmin4.
- **Target**: a new PostgreSQL database in Amazon RDS.

Do not point PantryOS at both databases. First copy the source database into
RDS, verify it, then configure PantryOS to use only RDS.

The source database is not changed by these steps. Still, take a separate
backup before starting.

## 1. Back up the current database in pgAdmin4

1. Open pgAdmin4 and connect to the server containing PantryOS.
2. Right-click the PantryOS database and choose **Backup...**.
3. Set:
   - **Format**: `Custom`
   - **File name**: a location you can remember, such as
     `C:\Backups\pantryos-before-aws.backup`
   - **Compression**: leave the default.
4. In **Dump Options**, enable **Only data** only if the RDS schema will be
   created separately. Normally leave it disabled so both schema and data are
   copied.
5. Click **Backup** and wait for the successful message.

Record these source details from pgAdmin:

- database name
- database user
- PostgreSQL major version
- whether the database already contains the manager, warehouses, products,
  and orders you want to demonstrate

The RDS PostgreSQL major version should be the same as, or newer than, the
source version.

## 2. Create the RDS database

1. AWS Console -> **RDS** -> **Create database**.
2. Select:
   - Engine: **PostgreSQL**
   - Template: **Free tier**, if available
   - DB identifier: `pantryos-db`
   - Master username: `pantryadmin`
   - A strong password saved in a password manager
   - Initial database name: `warehouse_db`
   - Same AWS Region you will use for EC2
3. For the fastest migration from your own computer, choose **Public access:
   Yes** temporarily.
4. Create the database and wait for **Available**.
5. Copy the RDS **endpoint**, which looks like:

   `pantryos-db.xxxxx.ap-south-1.rds.amazonaws.com`

Public access does not make the database open by itself; the security group
still controls access. We will restrict port 5432 to your current IP during
the restore, and later to the EC2 security group only.

## 3. Allow pgAdmin4 to connect to RDS

1. In RDS, open the database's **Connectivity & security** tab.
2. Open its VPC security group.
3. Add an inbound rule:
   - Type: **PostgreSQL**
   - Port: `5432`
   - Source: **My IP**
4. In pgAdmin4, register a new server:
   - Host: the RDS endpoint
   - Port: `5432`
   - Maintenance database: `warehouse_db`
   - Username: `pantryadmin`
   - Password: the RDS master password
5. Click **Save** and confirm that the connection succeeds.

If it fails, check that your internet connection has not changed public IP,
that the RDS status is Available, and that the RDS security group rule uses
your current IP with `/32`.

## 4. Restore the pgAdmin backup into RDS

1. In pgAdmin4, right-click the RDS `warehouse_db`.
2. Choose **Restore...**.
3. Select the `.backup` file created in step 1.
4. In restore options, use:
   - **Clean before restore**: disabled (the new database should be empty)
   - **Owner**: disabled, if shown
   - **Privileges**: disabled, if shown
5. Start the restore and wait for it to finish.

Do not restore into the `postgres` maintenance database. Restore into
`warehouse_db`.

Afterward, open Query Tool on the RDS database and run:

```sql
SELECT COUNT(*) FROM warehouses;
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM products;
SELECT version_num FROM alembic_version;
```

Confirm that the expected data exists. If the restore reports errors about
the original database owner or privileges, repeat with **Owner** and
**Privileges** disabled. Do not ignore errors involving tables or data.

## 5. Create EC2

1. AWS Console -> **EC2** -> **Launch instance**.
2. Select:
   - Ubuntu Server 24.04 LTS
   - free-tier instance, or `t3.micro`
   - a new key pair
3. EC2 security group inbound rules:
   - SSH TCP `22` -> **My IP**
   - HTTP TCP `80` -> `0.0.0.0/0`
4. Launch the instance.
5. Allocate an Elastic IP and associate it with the instance.

The presentation URL will be:

`http://YOUR_ELASTIC_IP`

## 6. Allow EC2 to use RDS

After the EC2 security group exists:

1. Open the RDS security group inbound rules.
2. Add PostgreSQL TCP `5432`.
3. Set **Source** to the EC2 security group, not an IP address.
4. Keep the temporary **My IP** rule until the migration verification is
   complete, then remove the My IP rule.

Do not add `0.0.0.0/0` for PostgreSQL.

## 7. Install Docker on EC2

Connect with EC2 Instance Connect or SSH and run:

```bash
sudo apt-get update
sudo apt-get install -y git curl
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
newgrp docker
docker compose version
```

## 8. Copy the project to EC2

From EC2:

```bash
git clone <YOUR_REPOSITORY_URL> PantryOS
cd PantryOS
```

For a private repository, use an SSH deploy key or copy the project archive.
Never commit AWS keys, database passwords, or `.env` files.

## 9. Configure PantryOS to use RDS

From the project root, create the backend environment file:

```bash
nano backend/.env
```

Paste this, replacing every placeholder:

```env
DATABASE_URL=postgresql+psycopg://pantryadmin:YOUR_RDS_PASSWORD@YOUR_RDS_ENDPOINT:5432/warehouse_db
JWT_SECRET_KEY=YOUR_LONG_RANDOM_JWT_SECRET
CORS_ORIGINS=http://YOUR_ELASTIC_IP,https://YOUR_FRONTEND_DOMAIN,https://localhost,http://localhost
ENABLE_LOCAL_EXPIRY_LOOP=true
ENABLE_LOCAL_INVENTORY_AI_LOOP=true
INTERNAL_JOB_SECRET=YOUR_LONG_RANDOM_JOB_SECRET
AI_API_URL=https://openrouter.ai/api/v1/chat/completions
AI_API_KEY=YOUR_FREE_TIER_PROVIDER_KEY
AI_MODEL=YOUR_FREE_CHAT_MODEL_ID
AWS_REGION=ap-south-1
```

`CORS_ORIGINS` is a comma-separated list of exact browser origins, including scheme and port when present. Keep the deployed frontend origin and `https://localhost` for the Capacitor Android WebView. Replace `YOUR_FRONTEND_DOMAIN` with the origin where the web app is actually served; do not use a wildcard.

Generate secrets on EC2 with:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

If the RDS password contains `@`, `:`, `/`, `#`, or spaces, URL-encode it
before placing it in `DATABASE_URL`.

Choose a currently free-tier model supported by the configured OpenAI-compatible
chat-completions endpoint. Free quotas and model availability can change. The
AI key belongs only in `backend/.env`; never put it in a `VITE_*` variable or in
the Android package. With no key/model configured, invoice summaries and AI Help
use local deterministic fallbacks. The local inventory suggestion job runs once
daily; disable it when using more than one backend replica and schedule the
authenticated internal inventory-intelligence job from one external scheduler.

`AWS_REGION` enables the optional delivery-document parser at
`POST /purchase-orders/{purchase_order_id}/parse-document`. The backend uses
Textract `AnalyzeExpense` for PDF/JPEG/PNG/TIFF documents up to 5 MB. Attach an
EC2 instance profile with `textract:AnalyzeExpense` permission in this region;
use the role's temporary credentials rather than storing AWS access keys in
`backend/.env`. Extracted fields are suggestions only and the worker must verify
them against the physical delivery before receiving stock. Lot and expiry fields
may not be present in every supplier document, so those values remain editable.

## 10. Do not overwrite the restored database

Because the database was restored from pgAdmin, do **not** run a migration
that recreates or drops the schema.

First check the migration version in pgAdmin:

```sql
SELECT version_num FROM alembic_version;
```

If it returns the latest repository revision (`0012_warehouse_workflow`),
start the application directly.

If the table is missing or the version is older, stop and make a backup of
RDS before running any migration. Then run the migration only if you know the
source database was created by this repository's Alembic migrations:

```bash
docker compose -f docker-compose.production.yml run --rm backend alembic upgrade head
```

The backend does not automatically create or upgrade the schema. Keep schema
changes under Alembic migrations and review the current revision before applying
any migration to the restored database.

## 11. Build and start the application

From the project root on EC2:

```bash
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d
docker compose -f docker-compose.production.yml ps
```

Both `backend` and `frontend` should show `Up`.

Test the API:

```bash
curl http://localhost/api/health
```

Expected response:

```json
{"status":"healthy","database":"connected"}
```

Open `http://YOUR_ELASTIC_IP` in a browser and log in with a user that
already existed in the pgAdmin database.

## 12. Verify migrated data

Confirm in the application that:

1. Existing manager login works.
2. Existing warehouses are visible.
3. Existing products and inventory are visible.
4. Existing orders and customers are visible.
5. Creating a test product or order changes the RDS database.
6. Refreshing the browser preserves the new data.

If the API does not start:

```bash
docker compose -f docker-compose.production.yml logs --tail=100 backend
docker compose -f docker-compose.production.yml logs --tail=100 frontend
```

## 13. If the source database has no manager

Only do this if the restored database contains no usable manager. Generate a
password hash:

```bash
docker compose -f docker-compose.production.yml exec backend python -c \
'from app.auth.security import hash_password; print(hash_password("CHANGE_THIS_PASSWORD"))'
```

Use pgAdmin connected to RDS and run:

```sql
INSERT INTO warehouses (name, location)
VALUES ('Main Warehouse', 'College Demo')
RETURNING warehouse_id;
```

Use the returned ID in this statement:

```sql
INSERT INTO users
(username, full_name, role, password_hash, warehouse_id)
VALUES
('manager', 'Demo Manager', 'manager', 'PASTE_HASH_HERE', 1);
```

Replace `1` with the actual returned warehouse ID. Log in with the password
used to create the hash.

## 14. Final security cleanup

After confirming the restore and app:

1. Remove the RDS security group rule whose source is **My IP**.
2. Keep only the EC2 security group as the RDS PostgreSQL source.
3. Keep SSH restricted to **My IP**.
4. Do not expose port 5432 publicly.
5. Do not upload `.env` or the pgAdmin backup to GitHub.

## Presentation-day checklist

```bash
docker compose -f docker-compose.production.yml ps
curl http://localhost/api/health
```

Then test manager login, dashboard loading, one product, one customer, and
one order. Keep the EC2 instance running and keep the Elastic IP attached.

## After the presentation

RDS and EC2 can incur charges. Take a final RDS snapshot, then stop or
terminate resources you no longer need. Release the Elastic IP after
disassociating it; an unattached Elastic IP can incur a charge.
