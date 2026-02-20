#!/usr/bin/env tsx
/**
 * JSON Schema → Qdrant Payload Schema Generator
 *
 * Reads ActivityNode.json and generates Qdrant payload schema config.
 *
 * Usage: tsx scripts/jsonschema-to-qdrant.ts
 */

import fs from 'fs';
import path from 'path';

const SCHEMA_PATH = path.join(process.cwd(), 'packages/schemas/ActivityNode.json');
const OUTPUT_PATH = path.join(process.cwd(), 'services/api/config/qdrant_schema.json');

/**
 * Map JSON Schema types to Qdrant payload types
 */
function mapJSONSchemaTypeToQdrant(property: any): string {
  const type = Array.isArray(property.type) ? property.type[0] : property.type;

  switch (type) {
    case 'string':
      return 'keyword';
    case 'integer':
      return 'integer';
    case 'number':
      return 'float';
    case 'boolean':
      return 'bool';
    default:
      return 'keyword'; // Default fallback
  }
}

/**
 * Generate Qdrant payload schema from ActivityNode JSON Schema
 */
async function generateQdrantSchema() {
  // Read ActivityNode schema
  if (!fs.existsSync(SCHEMA_PATH)) {
    console.error(`Error: ActivityNode.json not found at ${SCHEMA_PATH}`);
    console.error('Run prisma-to-jsonschema.ts first');
    process.exit(1);
  }

  const activityNodeSchema = JSON.parse(fs.readFileSync(SCHEMA_PATH, 'utf-8'));
  const properties = activityNodeSchema.properties || {};

  const qdrantSchema: Record<string, { type: string }> = {};

  // Map JSON Schema properties to Qdrant payload types
  for (const [fieldName, property] of Object.entries(properties)) {
    const qdrantType = mapJSONSchemaTypeToQdrant(property);
    qdrantSchema[fieldName] = { type: qdrantType };
  }

  // Ensure output directory exists
  const outputDir = path.dirname(OUTPUT_PATH);
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  // Write Qdrant schema
  fs.writeFileSync(OUTPUT_PATH, JSON.stringify(qdrantSchema, null, 2));
  console.log(`✓ Generated qdrant_schema.json`);
}

// Run
generateQdrantSchema().catch((err) => {
  console.error('Error generating Qdrant schema:', err);
  process.exit(1);
});
