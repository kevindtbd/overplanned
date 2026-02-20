import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

// 42 locked vibe tags - categorized taxonomy
const VIBE_TAGS = [
  // Dining character (8 tags)
  { slug: 'hole-in-the-wall', name: 'Hole in the Wall', category: 'dining-character', sortOrder: 1 },
  { slug: 'michelin-worthy', name: 'Michelin-Worthy', category: 'dining-character', sortOrder: 2 },
  { slug: 'local-favorite', name: 'Local Favorite', category: 'dining-character', sortOrder: 3 },
  { slug: 'tourist-trap', name: 'Tourist Trap', category: 'dining-character', sortOrder: 4 },
  { slug: 'hidden-gem', name: 'Hidden Gem', category: 'dining-character', sortOrder: 5 },
  { slug: 'instagram-worthy', name: 'Instagram-Worthy', category: 'dining-character', sortOrder: 6 },
  { slug: 'cash-only', name: 'Cash Only', category: 'dining-character', sortOrder: 7 },
  { slug: 'reservation-required', name: 'Reservation Required', category: 'dining-character', sortOrder: 8 },

  // Atmosphere (10 tags)
  { slug: 'quiet', name: 'Quiet', category: 'atmosphere', sortOrder: 9 },
  { slug: 'lively', name: 'Lively', category: 'atmosphere', sortOrder: 10 },
  { slug: 'romantic', name: 'Romantic', category: 'atmosphere', sortOrder: 11 },
  { slug: 'family-friendly', name: 'Family-Friendly', category: 'atmosphere', sortOrder: 12 },
  { slug: 'solo-friendly', name: 'Solo-Friendly', category: 'atmosphere', sortOrder: 13 },
  { slug: 'date-spot', name: 'Date Spot', category: 'atmosphere', sortOrder: 14 },
  { slug: 'work-friendly', name: 'Work-Friendly', category: 'atmosphere', sortOrder: 15 },
  { slug: 'outdoor-seating', name: 'Outdoor Seating', category: 'atmosphere', sortOrder: 16 },
  { slug: 'cozy', name: 'Cozy', category: 'atmosphere', sortOrder: 17 },
  { slug: 'minimalist', name: 'Minimalist', category: 'atmosphere', sortOrder: 18 },

  // Activity type (12 tags)
  { slug: 'hands-on', name: 'Hands-On', category: 'activity-type', sortOrder: 19 },
  { slug: 'spectator', name: 'Spectator', category: 'activity-type', sortOrder: 20 },
  { slug: 'educational', name: 'Educational', category: 'activity-type', sortOrder: 21 },
  { slug: 'physical', name: 'Physical', category: 'activity-type', sortOrder: 22 },
  { slug: 'relaxing', name: 'Relaxing', category: 'activity-type', sortOrder: 23 },
  { slug: 'adventurous', name: 'Adventurous', category: 'activity-type', sortOrder: 24 },
  { slug: 'cultural', name: 'Cultural', category: 'activity-type', sortOrder: 25 },
  { slug: 'artsy', name: 'Artsy', category: 'activity-type', sortOrder: 26 },
  { slug: 'historical', name: 'Historical', category: 'activity-type', sortOrder: 27 },
  { slug: 'modern', name: 'Modern', category: 'activity-type', sortOrder: 28 },
  { slug: 'traditional', name: 'Traditional', category: 'activity-type', sortOrder: 29 },
  { slug: 'unique', name: 'Unique', category: 'activity-type', sortOrder: 30 },

  // Timing (6 tags)
  { slug: 'early-bird', name: 'Early Bird', category: 'timing', sortOrder: 31 },
  { slug: 'late-night', name: 'Late Night', category: 'timing', sortOrder: 32 },
  { slug: 'all-day', name: 'All Day', category: 'timing', sortOrder: 33 },
  { slug: 'seasonal', name: 'Seasonal', category: 'timing', sortOrder: 34 },
  { slug: 'weekend-only', name: 'Weekend Only', category: 'timing', sortOrder: 35 },
  { slug: 'weekday-best', name: 'Weekday Best', category: 'timing', sortOrder: 36 },

  // Pace & energy (6 tags)
  { slug: 'high-energy', name: 'High Energy', category: 'pace-energy', sortOrder: 37 },
  { slug: 'low-key', name: 'Low-Key', category: 'pace-energy', sortOrder: 38 },
  { slug: 'fast-paced', name: 'Fast-Paced', category: 'pace-energy', sortOrder: 39 },
  { slug: 'slow-paced', name: 'Slow-Paced', category: 'pace-energy', sortOrder: 40 },
  { slug: 'spontaneous', name: 'Spontaneous', category: 'pace-energy', sortOrder: 41 },
  { slug: 'structured', name: 'Structured', category: 'pace-energy', sortOrder: 42 },
];

async function main() {
  console.log('🌱 Starting database seed...');

  // Clean existing data in development
  if (process.env.NODE_ENV !== 'production') {
    console.log('🧹 Cleaning existing seed data...');
    await prisma.behavioralSignal.deleteMany();
    await prisma.intentionSignal.deleteMany();
    await prisma.rawEvent.deleteMany();
    await prisma.qualitySignal.deleteMany();
    await prisma.activityNodeVibeTag.deleteMany();
    await prisma.activityAlias.deleteMany();
    await prisma.vibeTag.deleteMany();
    await prisma.activityNode.deleteMany();
    await prisma.itinerarySlot.deleteMany();
    await prisma.tripMember.deleteMany();
    await prisma.sharedTripToken.deleteMany();
    await prisma.inviteToken.deleteMany();
    await prisma.trip.deleteMany();
    await prisma.auditLog.deleteMany();
    await prisma.pivotEvent.deleteMany();
    await prisma.modelRegistry.deleteMany();
    await prisma.session.deleteMany();
    await prisma.account.deleteMany();
    await prisma.user.deleteMany();
  }

  // Seed vibe tags
  console.log('🏷️  Seeding vibe tags...');
  for (const tag of VIBE_TAGS) {
    await prisma.vibeTag.create({
      data: tag,
    });
  }
  console.log(`✅ Created ${VIBE_TAGS.length} vibe tags`);

  // Seed test users
  console.log('👤 Seeding test users...');

  const testUser = await prisma.user.create({
    data: {
      email: 'test@overplanned.app',
      name: 'Test User',
      emailVerified: new Date(),
      subscriptionTier: 'beta',
      systemRole: 'user',
      onboardingComplete: true,
      lastActiveAt: new Date(),
    },
  });
  console.log(`✅ Created test user: ${testUser.email}`);

  const adminUser = await prisma.user.create({
    data: {
      email: 'admin@overplanned.app',
      name: 'Admin User',
      emailVerified: new Date(),
      subscriptionTier: 'lifetime',
      systemRole: 'admin',
      onboardingComplete: true,
      lastActiveAt: new Date(),
    },
  });
  console.log(`✅ Created admin user: ${adminUser.email}`);

  // Seed a sample trip for test user
  console.log('✈️  Seeding sample trip...');
  const sampleTrip = await prisma.trip.create({
    data: {
      userId: testUser.id,
      mode: 'solo',
      status: 'planning',
      destination: 'Tokyo, Japan',
      city: 'Tokyo',
      country: 'Japan',
      timezone: 'Asia/Tokyo',
      startDate: new Date('2026-06-01'),
      endDate: new Date('2026-06-07'),
      memberCount: 1,
      planningProgress: 0.3,
      personaSeed: {
        pace: 'moderate',
        morningPreference: 'early_bird',
        foodChips: ['local-favorite', 'hole-in-the-wall'],
        interests: ['culture', 'dining', 'hidden-gem'],
      },
      members: {
        create: {
          userId: testUser.id,
          role: 'organizer',
          status: 'joined',
          joinedAt: new Date(),
        },
      },
    },
  });
  console.log(`✅ Created sample trip: ${sampleTrip.destination}`);

  // Seed a sample activity node
  console.log('📍 Seeding sample activity node...');
  const sampleNode = await prisma.activityNode.create({
    data: {
      name: 'Tsukiji Outer Market',
      slug: 'tsukiji-outer-market-tokyo',
      canonicalName: 'tsukiji outer market',
      city: 'Tokyo',
      country: 'Japan',
      neighborhood: 'Tsukiji',
      latitude: 35.6654,
      longitude: 139.7707,
      category: 'dining',
      subcategory: 'market',
      priceLevel: 2,
      address: '5 Chome-2-1 Tsukiji, Chuo City, Tokyo 104-0045, Japan',
      descriptionShort: 'Famous seafood and produce market with street food stalls',
      descriptionLong: 'The Tsukiji Outer Market continues to thrive as a bustling hub of fresh seafood, produce, and street food. While the wholesale market has moved, the outer market offers an authentic local experience with traditional food stalls, fresh sushi, and Japanese culinary culture.',
      status: 'active',
      isCanonical: true,
      sourceCount: 3,
      convergenceScore: 0.92,
      authorityScore: 0.88,
      lastScrapedAt: new Date(),
      lastValidatedAt: new Date(),
    },
  });
  console.log(`✅ Created sample activity node: ${sampleNode.name}`);

  // Link vibe tags to sample node
  console.log('🔗 Linking vibe tags to activity node...');
  const localFavoriteTag = await prisma.vibeTag.findUnique({
    where: { slug: 'local-favorite' },
  });
  const culturalTag = await prisma.vibeTag.findUnique({
    where: { slug: 'cultural' },
  });
  const earlyBirdTag = await prisma.vibeTag.findUnique({
    where: { slug: 'early-bird' },
  });

  if (localFavoriteTag && culturalTag && earlyBirdTag) {
    await prisma.activityNodeVibeTag.createMany({
      data: [
        {
          activityNodeId: sampleNode.id,
          vibeTagId: localFavoriteTag.id,
          score: 0.95,
          source: 'rule_inference',
        },
        {
          activityNodeId: sampleNode.id,
          vibeTagId: culturalTag.id,
          score: 0.88,
          source: 'rule_inference',
        },
        {
          activityNodeId: sampleNode.id,
          vibeTagId: earlyBirdTag.id,
          score: 0.92,
          source: 'rule_inference',
        },
      ],
    });
    console.log('✅ Linked 3 vibe tags to activity node');
  }

  // Seed sample quality signal
  console.log('⭐ Seeding sample quality signal...');
  await prisma.qualitySignal.create({
    data: {
      activityNodeId: sampleNode.id,
      sourceName: 'The Infatuation Tokyo',
      sourceUrl: 'https://www.theinfatuation.com/tokyo/reviews/tsukiji-market',
      sourceAuthority: 0.92,
      signalType: 'recommendation',
      rawExcerpt: 'A must-visit for fresh seafood and authentic Tokyo food culture.',
      extractedAt: new Date(),
    },
  });
  console.log('✅ Created sample quality signal');

  // Seed embedding model in registry
  console.log('🤖 Seeding model registry...');
  await prisma.modelRegistry.create({
    data: {
      modelName: 'nomic-embed-text',
      modelVersion: '1.5.0',
      stage: 'production',
      modelType: 'embedding',
      description: 'nomic-embed-text-v1.5 for activity node embeddings (768 dim)',
      artifactPath: 'sentence-transformers/nomic-embed-text-v1.5',
      configSnapshot: {
        dimensions: 768,
        license: 'Apache 2.0',
        matryoshka: true,
        truncation_dims: [512, 256],
      },
      metrics: {
        mteb_avg: 0.628,
        retrieval_avg: 0.537,
      },
      evaluatedAt: new Date(),
      promotedAt: new Date(),
      promotedBy: 'auto_eval',
    },
  });
  console.log('✅ Created embedding model registry entry');

  console.log('');
  console.log('🎉 Database seed completed successfully!');
  console.log('');
  console.log('Summary:');
  console.log(`  - ${VIBE_TAGS.length} vibe tags`);
  console.log('  - 2 test users (1 user, 1 admin)');
  console.log('  - 1 sample trip (Tokyo)');
  console.log('  - 1 sample activity node (Tsukiji Market)');
  console.log('  - 3 vibe tag associations');
  console.log('  - 1 quality signal');
  console.log('  - 1 model registry entry');
}

main()
  .catch((e) => {
    console.error('❌ Seed failed:', e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
