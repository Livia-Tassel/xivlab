"""Scheduled background jobs (cron-style).

Each module here exposes a single ``run_<name>()`` async entrypoint that
APScheduler (T22) calls on its schedule. Jobs are also runnable directly
from a script for backfill / debugging.
"""
