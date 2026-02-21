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
      status: 'approved',
      isCanonical: true,
      sourceCount: 3,
      convergenceScore: 0.92,
      authorityScore: 0.88,
      lastScrapedAt: new Date(),
      lastValidatedAt: new Date(),
    },
  });
  console.log(`Created sample activity node: ${sampleNode.name}`);

  // Additional Tokyo ActivityNodes
  console.log('Seeding additional Tokyo activity nodes...');

  const tokyoNodes: Array<{
    name: string;
    slug: string;
    canonicalName: string;
    neighborhood: string;
    latitude: number;
    longitude: number;
    category: string;
    priceLevel: number;
    sourceCount: number;
    convergenceScore: number;
    authorityScore: number;
    descriptionShort: string;
    vibeTags: string[];
  }> = [
    {
      name: 'Senso-ji Temple',
      slug: 'senso-ji-temple-tokyo',
      canonicalName: 'senso-ji temple',
      neighborhood: 'Asakusa',
      latitude: 35.7148,
      longitude: 139.7967,
      category: 'culture',
      priceLevel: 1,
      sourceCount: 5,
      convergenceScore: 0.95,
      authorityScore: 0.92,
      descriptionShort: 'Ancient Buddhist temple and iconic Tokyo landmark in the heart of Asakusa.',
      vibeTags: ['historical', 'cultural', 'traditional'],
    },
    {
      name: 'Meiji Jingu',
      slug: 'meiji-jingu-tokyo',
      canonicalName: 'meiji jingu',
      neighborhood: 'Shibuya',
      latitude: 35.6764,
      longitude: 139.6993,
      category: 'culture',
      priceLevel: 1,
      sourceCount: 4,
      convergenceScore: 0.93,
      authorityScore: 0.90,
      descriptionShort: 'Serene Shinto shrine surrounded by a sprawling old-growth forest in central Tokyo.',
      vibeTags: ['quiet', 'traditional', 'relaxing'],
    },
    {
      name: 'teamLab Borderless',
      slug: 'teamlab-borderless-tokyo',
      canonicalName: 'teamlab borderless',
      neighborhood: 'Odaiba',
      latitude: 35.6268,
      longitude: 139.7837,
      category: 'entertainment',
      priceLevel: 3,
      sourceCount: 4,
      convergenceScore: 0.91,
      authorityScore: 0.88,
      descriptionShort: 'Immersive digital art museum with boundary-free interactive installations.',
      vibeTags: ['modern', 'artsy', 'unique'],
    },
    {
      name: 'Shibuya Crossing',
      slug: 'shibuya-crossing-tokyo',
      canonicalName: 'shibuya crossing',
      neighborhood: 'Shibuya',
      latitude: 35.6595,
      longitude: 139.7004,
      category: 'experience',
      priceLevel: 1,
      sourceCount: 5,
      convergenceScore: 0.94,
      authorityScore: 0.85,
      descriptionShort: 'The world-famous scramble intersection where thousands cross simultaneously.',
      vibeTags: ['high-energy', 'lively', 'unique'],
    },
    {
      name: 'Shinjuku Gyoen',
      slug: 'shinjuku-gyoen-tokyo',
      canonicalName: 'shinjuku gyoen',
      neighborhood: 'Shinjuku',
      latitude: 35.6852,
      longitude: 139.7100,
      category: 'outdoors',
      priceLevel: 1,
      sourceCount: 4,
      convergenceScore: 0.90,
      authorityScore: 0.87,
      descriptionShort: 'Expansive national garden blending Japanese, English, and French landscape styles.',
      vibeTags: ['relaxing', 'quiet', 'seasonal'],
    },
    {
      name: 'Akihabara Electric Town',
      slug: 'akihabara-electric-town-tokyo',
      canonicalName: 'akihabara electric town',
      neighborhood: 'Chiyoda',
      latitude: 35.7023,
      longitude: 139.7745,
      category: 'shopping',
      priceLevel: 2,
      sourceCount: 3,
      convergenceScore: 0.88,
      authorityScore: 0.82,
      descriptionShort: 'Neon-lit district packed with electronics shops, anime stores, and gaming arcades.',
      vibeTags: ['lively', 'modern', 'unique'],
    },
    {
      name: 'Robot Restaurant',
      slug: 'robot-restaurant-tokyo',
      canonicalName: 'robot restaurant',
      neighborhood: 'Shinjuku',
      latitude: 35.6938,
      longitude: 139.7034,
      category: 'nightlife',
      priceLevel: 3,
      sourceCount: 3,
      convergenceScore: 0.78,
      authorityScore: 0.72,
      descriptionShort: 'Over-the-top neon-drenched cabaret show featuring robots and high-energy performances.',
      vibeTags: ['high-energy', 'unique', 'late-night'],
    },
    {
      name: 'Omoide Yokocho',
      slug: 'omoide-yokocho-tokyo',
      canonicalName: 'omoide yokocho',
      neighborhood: 'Shinjuku',
      latitude: 35.6934,
      longitude: 139.6988,
      category: 'dining',
      priceLevel: 1,
      sourceCount: 4,
      convergenceScore: 0.91,
      authorityScore: 0.88,
      descriptionShort: 'Atmospheric alley of tiny yakitori stalls dating back to the post-war era.',
      vibeTags: ['hole-in-the-wall', 'local-favorite', 'late-night'],
    },
    {
      name: 'Golden Gai',
      slug: 'golden-gai-tokyo',
      canonicalName: 'golden gai',
      neighborhood: 'Shinjuku',
      latitude: 35.6940,
      longitude: 139.7040,
      category: 'drinks',
      priceLevel: 2,
      sourceCount: 5,
      convergenceScore: 0.93,
      authorityScore: 0.90,
      descriptionShort: 'Labyrinth of over 200 tiny themed bars crammed into six narrow alleys.',
      vibeTags: ['hidden-gem', 'cozy', 'late-night'],
    },
    {
      name: 'Harajuku Takeshita Street',
      slug: 'harajuku-takeshita-street-tokyo',
      canonicalName: 'harajuku takeshita street',
      neighborhood: 'Shibuya',
      latitude: 35.6702,
      longitude: 139.7026,
      category: 'shopping',
      priceLevel: 2,
      sourceCount: 3,
      convergenceScore: 0.86,
      authorityScore: 0.78,
      descriptionShort: 'Colorful pedestrian street at the epicenter of Japanese youth fashion culture.',
      vibeTags: ['lively', 'modern', 'instagram-worthy'],
    },
    {
      name: 'Yanaka Ginza',
      slug: 'yanaka-ginza-tokyo',
      canonicalName: 'yanaka ginza',
      neighborhood: 'Taito',
      latitude: 35.7268,
      longitude: 139.7672,
      category: 'experience',
      priceLevel: 1,
      sourceCount: 3,
      convergenceScore: 0.85,
      authorityScore: 0.83,
      descriptionShort: 'Charming old-Tokyo shopping street with craft vendors and neighborhood cats.',
      vibeTags: ['hidden-gem', 'traditional', 'slow-paced'],
    },
    {
      name: 'Todoroki Valley',
      slug: 'todoroki-valley-tokyo',
      canonicalName: 'todoroki valley',
      neighborhood: 'Setagaya',
      latitude: 35.6077,
      longitude: 139.6452,
      category: 'outdoors',
      priceLevel: 1,
      sourceCount: 2,
      convergenceScore: 0.80,
      authorityScore: 0.76,
      descriptionShort: 'Hidden ravine garden tucked beneath residential streets with a serene walking path.',
      vibeTags: ['hidden-gem', 'quiet', 'relaxing'],
    },
    {
      name: 'Shimokitazawa',
      slug: 'shimokitazawa-tokyo',
      canonicalName: 'shimokitazawa',
      neighborhood: 'Setagaya',
      latitude: 35.6611,
      longitude: 139.6683,
      category: 'entertainment',
      priceLevel: 2,
      sourceCount: 3,
      convergenceScore: 0.87,
      authorityScore: 0.84,
      descriptionShort: 'Bohemian neighborhood of vintage shops, indie theaters, and live music venues.',
      vibeTags: ['artsy', 'low-key', 'local-favorite'],
    },
    {
      name: 'Kappabashi Kitchen Street',
      slug: 'kappabashi-kitchen-street-tokyo',
      canonicalName: 'kappabashi kitchen street',
      neighborhood: 'Taito',
      latitude: 35.7142,
      longitude: 139.7868,
      category: 'shopping',
      priceLevel: 2,
      sourceCount: 3,
      convergenceScore: 0.82,
      authorityScore: 0.79,
      descriptionShort: 'Specialist kitchenware district where restaurants source knives, ceramics, and food samples.',
      vibeTags: ['unique', 'hands-on', 'local-favorite'],
    },
    {
      name: 'Nakameguro',
      slug: 'nakameguro-tokyo',
      canonicalName: 'nakameguro',
      neighborhood: 'Meguro',
      latitude: 35.6442,
      longitude: 139.6988,
      category: 'drinks',
      priceLevel: 2,
      sourceCount: 3,
      convergenceScore: 0.84,
      authorityScore: 0.81,
      descriptionShort: 'Trendy canal-side neighborhood with craft cocktail bars, cafes, and cherry blossom walks.',
      vibeTags: ['date-spot', 'minimalist', 'seasonal'],
    },
    {
      name: 'Sumo at Ryogoku',
      slug: 'sumo-at-ryogoku-tokyo',
      canonicalName: 'sumo at ryogoku',
      neighborhood: 'Sumida',
      latitude: 35.6967,
      longitude: 139.7932,
      category: 'active',
      priceLevel: 3,
      sourceCount: 4,
      convergenceScore: 0.89,
      authorityScore: 0.87,
      descriptionShort: 'Grand sumo tournaments and training stable visits in the traditional wrestling district.',
      vibeTags: ['spectator', 'traditional', 'cultural'],
    },
    {
      name: 'Roppongi Art Triangle',
      slug: 'roppongi-art-triangle-tokyo',
      canonicalName: 'roppongi art triangle',
      neighborhood: 'Minato',
      latitude: 35.6604,
      longitude: 139.7292,
      category: 'culture',
      priceLevel: 2,
      sourceCount: 3,
      convergenceScore: 0.86,
      authorityScore: 0.83,
      descriptionShort: 'Three world-class art museums forming a walkable cultural corridor in Roppongi.',
      vibeTags: ['artsy', 'modern', 'educational'],
    },
    {
      name: 'Harmonica Yokocho',
      slug: 'harmonica-yokocho-tokyo',
      canonicalName: 'harmonica yokocho',
      neighborhood: 'Musashino',
      latitude: 35.7031,
      longitude: 139.5796,
      category: 'dining',
      priceLevel: 1,
      sourceCount: 2,
      convergenceScore: 0.79,
      authorityScore: 0.75,
      descriptionShort: 'Retro alleyway market near Kichijoji station with tiny bars and izakaya joints.',
      vibeTags: ['hole-in-the-wall', 'cozy', 'local-favorite'],
    },
    {
      name: 'Nezu Museum',
      slug: 'nezu-museum-tokyo',
      canonicalName: 'nezu museum',
      neighborhood: 'Minato',
      latitude: 35.6614,
      longitude: 139.7174,
      category: 'culture',
      priceLevel: 2,
      sourceCount: 3,
      convergenceScore: 0.83,
      authorityScore: 0.80,
      descriptionShort: 'Elegant museum of pre-modern Asian art set within a stunning bamboo-lined garden.',
      vibeTags: ['quiet', 'traditional', 'artsy'],
    },
  ];

  // Helper to look up vibe tags by slug
  const vibeTagCache: Record<string, string> = {};
  const allVibeTags = await prisma.vibeTag.findMany();
  for (const vt of allVibeTags) {
    vibeTagCache[vt.slug] = vt.id;
  }

  // Create each Tokyo node sequentially and link vibe tags
  for (const nodeData of tokyoNodes) {
    const { vibeTags: tagSlugs, ...fields } = nodeData;
    const node = await prisma.activityNode.create({
      data: {
        ...fields,
        city: 'Tokyo',
        country: 'Japan',
        status: 'approved',
        isCanonical: true,
        lastScrapedAt: new Date(),
        lastValidatedAt: new Date(),
      },
    });

    // Link vibe tags
    for (const slug of tagSlugs) {
      const tagId = vibeTagCache[slug];
      if (tagId) {
        await prisma.activityNodeVibeTag.create({
          data: {
            activityNodeId: node.id,
            vibeTagId: tagId,
            score: 0.85 + Math.random() * 0.10,
            source: 'rule_inference',
          },
        });
      }
    }

    console.log(`  Created: ${node.name} (${tagSlugs.length} tags)`);
  }
  console.log(`Created ${tokyoNodes.length} additional Tokyo activity nodes`);

  // Link vibe tags to Tsukiji node
  console.log('Linking vibe tags to Tsukiji node...');
  const tsukijiTagSlugs = ['local-favorite', 'cultural', 'early-bird'];
  for (const slug of tsukijiTagSlugs) {
    const tagId = vibeTagCache[slug];
    if (tagId) {
      await prisma.activityNodeVibeTag.create({
        data: {
          activityNodeId: sampleNode.id,
          vibeTagId: tagId,
          score: slug === 'local-favorite' ? 0.95 : slug === 'cultural' ? 0.88 : 0.92,
          source: 'rule_inference',
        },
      });
    }
  }
  console.log('Linked 3 vibe tags to Tsukiji node');

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
  console.log('  - 20 Tokyo activity nodes (Tsukiji + 19 additional)');
  console.log('  - 2-3 vibe tag associations per node');
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
