#!/usr/bin/env tsx
/**
 * migrate-vote-state.ts
 *
 * Migrates voteState.narrativeHint to ownerTip field on ItinerarySlot.
 * Run with: npx tsx scripts/migrate-vote-state.ts
 *
 * PREREQUISITE: ownerTip field must exist in schema (added via M-001 migration)
 */

import { Prisma, PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

async function migrateVoteState() {
  console.log("[migrate-vote-state] Starting migration...");

  try {
    // Find all slots with voteState containing narrativeHint
    const slotsWithHints = await prisma.itinerarySlot.findMany({
      where: {
        voteState: {
          not: Prisma.DbNull,
        },
      },
      select: {
        id: true,
        voteState: true,
      },
    });

    console.log(`[migrate-vote-state] Found ${slotsWithHints.length} slots with voteState`);

    // Filter to only those with narrativeHint
    const slotsToMigrate = slotsWithHints.filter(slot => {
      const voteState = slot.voteState as { narrativeHint?: string } | null;
      return voteState && typeof voteState === 'object' && 'narrativeHint' in voteState;
    });

    console.log(`[migrate-vote-state] Found ${slotsToMigrate.length} slots with narrativeHint to migrate`);

    if (slotsToMigrate.length === 0) {
      console.log("[migrate-vote-state] No slots to migrate. Exiting.");
      return;
    }

    // Migrate in a transaction
    const updates = slotsToMigrate.map(slot => {
      const voteState = slot.voteState as { narrativeHint: string };
      return prisma.itinerarySlot.update({
        where: { id: slot.id },
        data: {
          ownerTip: voteState.narrativeHint,
          voteState: Prisma.DbNull,
        },
      });
    });

    await prisma.$transaction(updates);

    console.log(`[migrate-vote-state] Successfully migrated ${slotsToMigrate.length} slots`);
    console.log("[migrate-vote-state] Migration complete!");

  } catch (error) {
    console.error("[migrate-vote-state] Migration failed:", error);
    process.exit(1);
  } finally {
    await prisma.$disconnect();
  }
}

migrateVoteState();
