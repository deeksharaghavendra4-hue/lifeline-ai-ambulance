# LifeLine AI Ambulance

Real-time ambulance dispatch and hospital coordination application built with Flask, JavaScript, AI-based dispatch logic, maps, and PostgreSQL.

## Database

This version uses **PostgreSQL** as the only runtime database.

SQLite has been removed.

Persistent application data is stored in PostgreSQL:

- Users: patients, drivers, hospital administrators
- Ambulances
- Hospitals
- Ambulance requests
- Emergency records

The backend no longer reads or writes `data/sample.json`.

## Project structure

```text
AI_Ambulance/
├── backend/
│   ├── app.py
│   ├── ai.py
│   ├── database.py
│   ├── models.py
│   └── requirements.txt
├── frontend/
├── .env
├── POSTGRES_SETUP.md
├── reset_demo.py
├── run.py
└── RUN_LIFELINE.bat
```

## Start the project

1. Install PostgreSQL.
2. Create a database named `lifeline_db`.
3. Set `DATABASE_URL` in `.env`.
4. Create/activate a Python virtual environment.
5. Install `backend/requirements.txt`.
6. Run `python run.py`.

See **POSTGRES_SETUP.md** for exact Windows commands.

## PostgreSQL connection

Example:

```env
DATABASE_URL=postgresql://postgres:YOUR_POSTGRES_PASSWORD@localhost:5432/lifeline_db
```

Do not commit a real password or API credentials to GitHub.

## What happens on first startup?

`backend/database.py` automatically creates the required PostgreSQL tables:

```text
users
ambulances
hospitals
requests
emergencies
```

No manual table creation is required.

## Existing SQLite data

The old `backend/lifeline.db` file is not included in this version.

Existing accounts that were stored only in SQLite need to be registered again in PostgreSQL. Keep a backup of the old project if you need those accounts.

## Reset demo operational data

After PostgreSQL is configured:

```powershell
python reset_demo.py
```

This removes requests and emergency records and makes all stored ambulances available. It does not delete registered users.

## Production deployment

For deployment, use a managed/cloud PostgreSQL connection string instead of the local `localhost` connection.

The same Flask application can connect to the cloud PostgreSQL database by changing only `DATABASE_URL`.

