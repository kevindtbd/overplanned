"""
Nightly batch jobs for Overplanned ML pipeline.

These run as standalone Python scripts via cron / Cloud Scheduler,
NOT inside the FastAPI process.

Usage:
    python -m services.api.jobs.training_extract
    python -m services.api.jobs.write_back
    python -m services.api.jobs.persona_updater

Schedule (UTC):
    03:00  training_extract  — BPR Parquet export from BehavioralSignal
    03:15  write_back        — Aggregate signals back to ActivityNode
    03:30  persona_updater   — EMA update of PersonaDimension from signals
"""
