#!/usr/bin/env tsx
/**
 * Prisma → JSON Schema Generator
 *
 * Converts Prisma schema models to JSON Schema files.
 * Single source of truth: prisma/schema.prisma
 *
 * Usage: tsx scripts/prisma-to-jsonschema.ts
 */

import { getSchema } from '@mrleebo/prisma-ast';
import fs from 'fs';
import path from 'path';

const SCHEMA_PATH = path.join(process.cwd(), 'prisma/schema.prisma');
const OUTPUT_DIR = path.join(process.cwd(), 'packages/schemas');

type PrismaFieldType = string;

interface JSONSchemaProperty {
  type: string | string[];
  format?: string;
  enum?: string[];
  items?: JSONSchemaProperty;
  default?: any;
}

interface JSONSchema {
  $schema: string;
  title: string;
  type: string;
  properties: Record<string, JSONSchemaProperty>;
  required: string[];
}

/**
 * Map Prisma field types to JSON Schema types
 */
function mapPrismaTypeToJSONSchema(
  fieldType: string,
  isOptional: boolean,
  defaultValue?: string,
  enumValues?: string[]
): JSONSchemaProperty {
  let baseType: JSONSchemaProperty;

  // Handle arrays
  if (fieldType.endsWith('[]')) {
    const itemType = fieldType.slice(0, -2);
    const items = mapPrismaTypeToJSONSchema(itemType, false);
    baseType = {
      type: 'array',
      items,
    };
  }
  // Handle enums
  else if (enumValues && enumValues.length > 0) {
    baseType = {
      type: 'string',
      enum: enumValues,
    };
  }
  // Handle scalar types
  else {
    switch (fieldType) {
      case 'String':
        baseType = { type: 'string' };
        break;
      case 'Int':
        baseType = { type: 'integer' };
        break;
      case 'Float':
        baseType = { type: 'number' };
        break;
      case 'Boolean':
        baseType = { type: 'boolean' };
        break;
      case 'DateTime':
        baseType = { type: 'string', format: 'date-time' };
        break;
      case 'Json':
        baseType = { type: 'object' };
        break;
      default:
        // Unknown type or relation - skip
        return { type: 'object' };
    }
  }

  // Add default value if present
  if (defaultValue !== undefined) {
    // Parse default values
    if (defaultValue === 'true') baseType.default = true;
    else if (defaultValue === 'false') baseType.default = false;
    else if (!isNaN(Number(defaultValue))) baseType.default = Number(defaultValue);
    else if (defaultValue.startsWith('"') || defaultValue.startsWith("'")) {
      baseType.default = defaultValue.slice(1, -1);
    } else {
      // Enum value or other
      baseType.default = defaultValue;
    }
  }

  // Handle optionals
  if (isOptional) {
    baseType.type = Array.isArray(baseType.type)
      ? [...baseType.type, 'null']
      : [baseType.type, 'null'];
  }

  return baseType;
}

/**
 * Parse Prisma schema and generate JSON Schema files
 */
async function generateJSONSchemas() {
  // Read Prisma schema
  const schemaContent = fs.readFileSync(SCHEMA_PATH, 'utf-8');
  const schema = getSchema(schemaContent);

  // Ensure output directory exists
  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  }

  // Extract enums
  const enums: Record<string, string[]> = {};
  schema.list
    .filter((item) => item.type === 'enum')
    .forEach((enumItem: any) => {
      enums[enumItem.name] = enumItem.enumerators.map((e: any) => e.name);
    });

  // Process each model
  const models = schema.list.filter((item) => item.type === 'model');

  for (const model of models as any[]) {
    const modelName = model.name;
    const properties: Record<string, JSONSchemaProperty> = {};
    const required: string[] = [];

    // Process each field
    for (const field of model.properties) {
      if (field.type !== 'field') continue;

      const fieldName = field.name;
      const fieldType = field.fieldType;
      const isOptional = field.optional === true;
      const isArray = field.array === true;

      // Skip relation fields (identified by capitalized type names not in enum or scalar types)
      const scalarTypes = ['String', 'Int', 'Float', 'Boolean', 'DateTime', 'Json'];
      if (
        !scalarTypes.includes(fieldType) &&
        !enums[fieldType] &&
        !isArray
      ) {
        continue;
      }

      // Extract default value
      let defaultValue: string | undefined;
      if (field.attributes) {
        const defaultAttr = field.attributes.find((a: any) => a.name === 'default');
        if (defaultAttr && defaultAttr.args && defaultAttr.args.length > 0) {
          defaultValue = defaultAttr.args[0].value;
        }
      }

      // Get enum values if applicable
      const enumValues = enums[fieldType];

      // Map type
      const actualFieldType = isArray ? `${fieldType}[]` : fieldType;
      properties[fieldName] = mapPrismaTypeToJSONSchema(
        actualFieldType,
        isOptional,
        defaultValue,
        enumValues
      );

      // Mark as required if not optional
      if (!isOptional) {
        required.push(fieldName);
      }
    }

    // Generate JSON Schema
    const jsonSchema: JSONSchema = {
      $schema: 'http://json-schema.org/draft-07/schema#',
      title: modelName,
      type: 'object',
      properties,
      required,
    };

    // Write to file
    const outputPath = path.join(OUTPUT_DIR, `${modelName}.json`);
    fs.writeFileSync(outputPath, JSON.stringify(jsonSchema, null, 2));
    console.log(`✓ Generated ${modelName}.json`);
  }

  console.log(`\n✓ Generated ${models.length} JSON Schema files`);
}

// Run
generateJSONSchemas().catch((err) => {
  console.error('Error generating JSON schemas:', err);
  process.exit(1);
});
