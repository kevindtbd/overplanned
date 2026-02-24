-- V2 ML Schema CHECK constraints (not expressible in Prisma schema)
-- Applied alongside prisma db push for the v2_ml_schema changes
-- Date: 2026-02-24

-- signal_weight is SERVER-ONLY: bounds damage from any bug that writes out-of-range values
ALTER TABLE "BehavioralSignal" ADD CONSTRAINT behavioral_signal_weight_range
  CHECK (signal_weight >= -1.0 AND signal_weight <= 3.0);

-- ArbitrationEvent context_snapshot must be under 64KB (no unbounded JSONB)
ALTER TABLE "ArbitrationEvent" ADD CONSTRAINT arbitration_context_snapshot_size
  CHECK (pg_column_size("contextSnapshot") < 65536);
