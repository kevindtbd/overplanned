import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

const VIBE_TAGS = [
  // Dining character
  { slug: 'hole-in-the-wall', name: 'Hole in the Wall', category: 'dining-character', sortOrder: 1 },
  { slug: 'michelin-worthy', name: 'Michelin Worthy', category: 'dining-character', sortOrder: 2 },
  { slug: 'local-favorite', name: 'Local Favorite', category: 'dining-character', sortOrder: 3 },
  { slug: 'tourist-trap', name: 'Tourist Trap', category: 'dining-character', sortOrder: 4 },
  { slug: 'hidden-gem', name: 'Hidden Gem', category: 'dining-character', sortOrder: 5 },

  // Atmosphere
  { slug: 'quiet', name: 'Quiet', category: 'atmosphere', sortOrder: 6 },
  { slug: 'lively', name: 'Lively', category: 'atmosphere', sortOrder: 7 },
  { slug: 'romantic', name: 'Romantic', category: 'atmosphere', sortOrder: 8 },
  { slug: 'casual', name: 'Casual', category: 'atmosphere', sortOrder: 9 },
  { slug: 'upscale', name: 'Upscale', category: 'atmosphere', sortOrder: 10 },
  { slug: 'cozy', name: 'Cozy', category: 'atmosphere', sortOrder: 11 },
  { slug: 'trendy', name: 'Trendy', category: 'atmosphere', sortOrder: 12 },
  { slug: 'historic', name: 'Historic', category: 'atmosphere', sortOrder: 13 },
  { slug: 'modern', name: 'Modern', category: 'atmosphere', sortOrder: 14 },

  // Activity type
  { slug: 'hands-on', name: 'Hands-On', category: 'activity-type', sortOrder: 15 },
  { slug: 'photo-op', name: 'Photo Op', category: 'activity-type', sortOrder: 16 },
  { slug: 'educational', name: 'Educational', category: 'activity-type', sortOrder: 17 },
  { slug: 'relaxing', name: 'Relaxing', category: 'activity-type', sortOrder: 18 },
  { slug: 'adventurous', name: 'Adventurous', category: 'activity-type', sortOrder: 19 },
  { slug: 'cultural', name: 'Cultural', category: 'activity-type', sortOrder: 20 },

  // Timing
  { slug: 'early-bird', name: 'Early Bird', category: 'timing', sortOrder: 21 },
  { slug: 'late-night', name: 'Late Night', category: 'timing', sortOrder: 22 },
  { slug: 'sunset', name: 'Sunset', category: 'timing', sortOrder: 23 },
  { slug: 'quick-stop', name: 'Quick Stop', category: 'timing', sortOrder: 24 },
  { slug: 'all-day', name: 'All Day', category: 'timing', sortOrder: 25 },

  // Crowd
  { slug: 'off-beaten-path', name: 'Off Beaten Path', category: 'crowd', sortOrder: 26 },
  { slug: 'popular', name: 'Popular', category: 'crowd', sortOrder: 27 },
  { slug: 'skip-the-line', name: 'Skip the Line', category: 'crowd', sortOrder: 28 },

  // Pace
  { slug: 'fast-paced', name: 'Fast Paced', category: 'pace', sortOrder: 29 },
  { slug: 'leisurely', name: 'Leisurely', category: 'pace', sortOrder: 30 },

  // Group dynamics
  { slug: 'group-friendly', name: 'Group Friendly', category: 'group-dynamics', sortOrder: 31 },
  { slug: 'intimate', name: 'Intimate', category: 'group-dynamics', sortOrder: 32 },
  { slug: 'solo-friendly', name: 'Solo Friendly', category: 'group-dynamics', sortOrder: 33 },

  // Special considerations
  { slug: 'kid-friendly', name: 'Kid Friendly', category: 'special', sortOrder: 34 },
  { slug: 'accessible', name: 'Accessible', category: 'special', sortOrder: 35 },
  { slug: 'instagram-worthy', name: 'Instagram Worthy', category: 'special', sortOrder: 36 },
  { slug: 'locals-only', name: 'Locals Only', category: 'special', sortOrder: 37 },
  { slug: 'seasonal', name: 'Seasonal', category: 'special', sortOrder: 38 },

  // Energy
  { slug: 'high-energy', name: 'High Energy', category: 'energy', sortOrder: 39 },
  { slug: 'chill', name: 'Chill', category: 'energy', sortOrder: 40 },
  { slug: 'meditative', name: 'Meditative', category: 'energy', sortOrder: 41 },
  { slug: 'active', name: 'Active', category: 'energy', sortOrder: 42 },
];

async function main() {
  console.log('Starting seed...');

  // Seed vibe tags
  console.log('Seeding vibe tags...');
  for (const tag of VIBE_TAGS) {
    await prisma.vibeTag.upsert({
      where: { slug: tag.slug },
      update: {},
      create: tag,
    });
  }
  console.log(`✓ Seeded ${VIBE_TAGS.length} vibe tags`);

  // Create test beta user
  console.log('Creating test beta user...');
  const testUser = await prisma.user.upsert({
    where: { email: 'test@overplanned.app' },
    update: {},
    create: {
      email: 'test@overplanned.app',
      name: 'Test User',
      subscriptionTier: 'beta',
      systemRole: 'user',
      onboardingComplete: true,
      emailVerified: new Date(),
    },
  });
  console.log(`✓ Created test user: ${testUser.email}`);

  // Create test admin user
  console.log('Creating test admin user...');
  const adminUser = await prisma.user.upsert({
    where: { email: 'admin@overplanned.app' },
    update: {},
    create: {
      email: 'admin@overplanned.app',
      name: 'Admin User',
      subscriptionTier: 'lifetime',
      systemRole: 'admin',
      onboardingComplete: true,
      emailVerified: new Date(),
    },
  });
  console.log(`✓ Created admin user: ${adminUser.email}`);

  // Create sample trip for testing
  console.log('Creating sample trip...');
  const trip = await prisma.trip.create({
    data: {
      userId: testUser.id,
      mode: 'solo',
      status: 'draft',
      destination: 'Tokyo, Japan',
      city: 'Tokyo',
      country: 'Japan',
      timezone: 'Asia/Tokyo',
      startDate: new Date('2026-04-01'),
      endDate: new Date('2026-04-07'),
      presetTemplate: 'foodie_weekend',
      personaSeed: {
        pace: 'leisurely',
        morningPreference: 'early_bird',
        foodChips: ['authentic', 'adventurous', 'hole-in-the-wall'],
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
  console.log(`✓ Created sample trip: ${trip.destination}`);

  // Register embedding model
  console.log('Registering embedding model...');
  await prisma.modelRegistry.upsert({
    where: {
      modelName_modelVersion: {
        modelName: 'nomic-embed-text',
        modelVersion: 'v1.5',
      },
    },
    update: {},
    create: {
      modelName: 'nomic-embed-text',
      modelVersion: 'v1.5',
      stage: 'production',
      modelType: 'embedding',
      description: 'Nomic Embed Text v1.5 - 768 dimensional embeddings, Apache 2.0, local inference',
      configSnapshot: {
        dimensions: 768,
        distance: 'cosine',
        matryoshka: true,
        license: 'Apache-2.0',
      },
      metrics: {
        mteb_average: 0.628,
      },
      promotedBy: 'foundation_seed',
      promotedAt: new Date(),
    },
  });
  console.log('✓ Registered embedding model');

  console.log('Seed completed successfully!');
}

main()
  .catch((e) => {
    console.error('Seed failed:', e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
