---
name: cron
description: "Use when the user asks to schedule recurring tasks, one-off reminders, timers, or cron-style jobs through the OpenSquilla cron tool."
always: false
triggers:
  - schedule
  - recurring
  - timer
  - cron
  - every
  - reminder
  - remind
  - 提醒
  - 每分钟
  - 每5分钟
  - 每天
  - 定时
provenance:
  origin: openclaw-derived
  license: MIT
  upstream_url: https://github.com/openclaw/openclaw
  maintained_by: OpenSquilla
metadata:
  opensquilla:
    requires_tools:
      - cron
---

# Cron Skill

When the user asks to schedule something, set up a recurring task, create a timer, or create a reminder, use the `cron` tool.

- To create a schedule: call `cron(action="add", schedule="<cron-or-natural-time>", task="<task text>")`.
- For reminders such as "remind me to drink water every minute" or "每分钟提醒我喝水", call `cron(action="add", schedule="<schedule>", task="<reminder text>", job_kind="system_event", session_target="main")`.
- To list schedules: call `cron(action="list")`.
- To trigger a schedule immediately: call `cron(action="run", job_id="<job id>")`.
- To cancel a schedule: call `cron(action="remove", job_id="<job id>")`.

Cron expression format: `minute hour day month weekday` (e.g. `0 9 * * 1-5` = weekdays at 9am).
