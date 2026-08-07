import os
import time


os.environ["TZ"] = "Asia/Taipei"
if hasattr(time, "tzset"):
    time.tzset()


from order_app_server import main


if __name__ == "__main__":
    main()
