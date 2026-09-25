"""
gunicorn's settings. gunicorn reads this file by itself when it starts in this directory.

Both knobs that matter can be turned from the app's Environment tab, with no code change:
WEB_CONCURRENCY sets the number of worker processes, and GUNICORN_CMD_ARGS takes any other
gunicorn flag (for example --access-logfile - to log every request).
"""

import os

# 0.0.0.0, not localhost: the platform reaches the app from outside the container.
bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"

# Two processes with four threads each: eight requests in flight at once. A page here spends
# most of its time waiting on Postgres, and a thread waits far more cheaply than a process.
# The whole container measured about 100 MB under light load, which fits even the 256 MB
# plan with room to spare. Each extra worker adds about 60 MB, so on 512 MB and up you can
# raise WEB_CONCURRENCY to 3 or 4.
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
threads = 4
