# OFA Meal Order Report

Telegram WebApp / Railway app for daily meal count reporting.

## Run

```bash
python order_app_server.py
```

## URLs

- Order report app: `/`
- Cost admin: `/admin`

## Admin Login

Default admin login:

- Username: `ofa5153`
- Password: `585858`

For production, set Railway variables:

- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `ADMIN_SESSION_SECRET`

## Railway Persistence

The app stores reports in SQLite. Railway deploys use an ephemeral filesystem unless a Volume is mounted.

To keep statistics after redeploys:

- Add a Railway Volume.
- Mount it to a path such as `/data`.
- Set `DATA_DIR=/data`, or rely on Railway's `RAILWAY_VOLUME_MOUNT_PATH` when available.

Without a Railway Volume, report data can disappear after a new deploy.
