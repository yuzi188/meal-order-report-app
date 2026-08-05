# 訂餐人數回報小程序

Telegram 小程序後台，用來顯示每日菜色並收集各單位每餐台餐 / 柬埔寨餐人數。

## 功能

- 自動依日期顯示菜單
- 單位：1001、1002-2、1002-3、68、88、3F
- 早餐、午餐、晚餐、宵夜分開回報
- 台餐 / 柬埔寨餐分開統計
- SQLite 儲存回報資料

## Railway

Start command:

```bash
python order_app_server.py
```

建議設定：

- `DATA_DIR=/data`
- Railway Volume mount 到 `/data`

