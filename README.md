# OFA Meal Order Report

Telegram WebApp / Railway app for daily meal count reporting.

## Run

```bash
python order_app_server.py
```

## Railway Persistence

The app stores reports in SQLite. Railway deploys use an ephemeral filesystem unless a Volume is mounted.

To keep statistics after redeploys:

- Add a Railway Volume.
- Mount it to a path such as `/data`.
- Set `DATA_DIR=/data`, or rely on Railway's `RAILWAY_VOLUME_MOUNT_PATH` when available.

Without a Railway Volume, report data can disappear after a new deploy.
