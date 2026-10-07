# LifeLine PostgreSQL Setup

## 1. Install PostgreSQL

Install PostgreSQL on Windows and remember the password you set for the `postgres` user.
The default PostgreSQL port is `5432`.

You can use pgAdmin or SQL Shell (psql).

## 2. Create the LifeLine database

In pgAdmin Query Tool or psql, run:

```sql
CREATE DATABASE lifeline_db;
```

Do not create the LifeLine tables manually. `backend/database.py` creates them automatically when Flask starts.

## 3. Configure `.env`

Open the `.env` file in the project root and set:

```env
DATABASE_URL=postgresql://postgres:YOUR_POSTGRES_PASSWORD@localhost:5432/lifeline_db
```

Replace `YOUR_POSTGRES_PASSWORD` with your actual PostgreSQL password.

If your PostgreSQL username, host, or port is different, change those values accordingly.

## 4. Create a fresh Python environment

From the project root:

```powershell
python -m venv venv
.env\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backendequirements.txt
```

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.env\Scripts\Activate.ps1
```

## 5. Start LifeLine

From the project root:

```powershell
python run.py
```

Open:

```text
http://localhost:5000
```

On the first startup, the backend creates these PostgreSQL tables:

- users
- ambulances
- hospitals
- requests
- emergencies

There is no SQLite database and the application does not read/write `sample.json`.

## 6. Important: existing SQLite accounts

The old `backend/lifeline.db` is intentionally removed from this version.

Existing accounts stored only in that SQLite file are not automatically copied. Register those accounts again through the LifeLine registration pages.

If you need to preserve the old accounts, keep a backup of the old project before deleting the SQLite file and ask for a one-time migration script.

## 7. Check the database

In pgAdmin, open:

```text
Databases
  → lifeline_db
      → Schemas
          → public
              → Tables
```

You should see the LifeLine tables after starting the Flask application.

## 8. Production deployment

For a real deployment, use the PostgreSQL connection string supplied by your cloud PostgreSQL provider instead of localhost.

Never commit real database passwords or API credentials to GitHub.
