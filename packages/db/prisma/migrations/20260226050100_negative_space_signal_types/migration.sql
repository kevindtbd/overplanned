-- Add negative space signal types
ALTER TYPE "SignalType" ADD VALUE IF NOT EXISTS 'preset_selected';
ALTER TYPE "SignalType" ADD VALUE IF NOT EXISTS 'preset_hovered';
ALTER TYPE "SignalType" ADD VALUE IF NOT EXISTS 'preset_all_skipped';
ALTER TYPE "SignalType" ADD VALUE IF NOT EXISTS 'pre_trip_slot_removed_reason';
