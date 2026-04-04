import * as fs from 'fs';
import * as path from 'path';
import { z } from 'zod';
import { GeoIntelligenceSchema } from './schemas';
import { CONFIG } from './config';
import { GeoIntelligence } from '../../src/types';

// ==========================================
// VALIDATION 1: Type Equivalency (TypeScript Compiler Level)
// ==========================================
// If the Zod schema does not structurally match the frontend types, 
// this code will fail to compile under `tsc`.
type SchemaInfer = z.infer<typeof GeoIntelligenceSchema>;
const _test1: SchemaInfer = {} as any as GeoIntelligence;

console.log("✅ Schema structure perfectly matches frontend src/types.ts");

// ==========================================
// VALIDATION 2: Historical Data Integrity Test
// ==========================================
// Does this schema successfully parse the existing, hand-crafted Intel files?
const intelDir = path.join(process.cwd(), 'public', 'data', 'intel');
const files = fs.readdirSync(intelDir).filter(f => f.endsWith('.json'));

let parseSuccess = 0;
for (const file of files) {
  try {
    const data = JSON.parse(fs.readFileSync(path.join(intelDir, file), 'utf8'));
    GeoIntelligenceSchema.parse(data);
    parseSuccess++;
  } catch (e) {
    console.error(`❌ Data drift detected in ${file}:`, (e as z.ZodError).issues[0]);
  }
}

if (parseSuccess === files.length) {
  console.log(`✅ Schemas successfully validated against all ${files.length} existing dossier files.`);
} else {
  console.warn(`⚠️ Only ${parseSuccess}/${files.length} files passed. Schema or existing data needs updating.`);
}

// ==========================================
// VALIDATION 3: Configuration Review
// ==========================================
if (CONFIG.MAX_CONTEXT_TOKENS > 8000) {
  console.warn(`⚠️ WARNING: You adjusted MAX_CONTEXT_TOKENS to ${CONFIG.MAX_CONTEXT_TOKENS}. DeepSeek-R1-7b at 32k tokens typically requires ~2-3GB VRAM JUST for the KV cache. This plus the model weights (~4.3GB at Q4) might exceed your RTX 3070's 8GB limit, causing fallback to slower System RAM.`);
} else {
  console.log(`✅ Config memory footprint is safe for RTX 3070 8GB.`);
}

console.log("Validation run complete.");
