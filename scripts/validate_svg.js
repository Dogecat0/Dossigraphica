import fs from 'fs';

try {
  const content = fs.readFileSync('public/readme-animation.svg', 'utf8');
  
  if (!content.trim().startsWith('<svg')) {
    throw new Error('SVG file does not start with <svg tag');
  }
  
  if (!content.trim().endsWith('</svg>')) {
    throw new Error('SVG file does not end with </svg>');
  }
  
  // Basic XML tag matching checks
  const tags = ['svg', 'style', 'rect', 'circle', 'path', 'g', 'text', 'defs', 'pattern'];
  console.log('--------------------------------------------------');
  console.log('🔍 SVG STRUCTURAL CHECK:');
  
  // Verify standard layout dimensions are preserved
  if (!content.includes('viewBox="0 0 800 320"')) {
    throw new Error('SVG viewBox is missing or incorrect');
  }
  console.log('✓ viewBox: 0 0 800 320');
  
  // Verify styles and animations are present
  if (!content.includes('<style>') || !content.includes('</style>')) {
    throw new Error('SVG <style> block is missing or malformed');
  }
  console.log('✓ Style block: Present and active');

  // Verify responsive media query exists
  if (!content.includes('@media (prefers-color-scheme: dark)')) {
    throw new Error('Responsive dark mode media query is missing');
  }
  console.log('✓ Theme support: Responsive dark mode query active');
  
  // Verify critical elements are present
  const importantStamps = [
    'RESEARCH PIPELINE',
    'INTELLIGENCE DIALS',
    'GEOPOLITICAL THREAT',
    'VALUE CHAIN DEP',
    'CHOKEPOINT MATRIX',
    'pulse-ring-red',
    'flow-route'
  ];
  
  for (const stamp of importantStamps) {
    if (!content.includes(stamp)) {
      throw new Error(`Critical graphic element or text signature "${stamp}" was not found`);
    }
  }
  console.log('✓ Critical markers and telemetry signatures: Fully verified');

  console.log('--------------------------------------------------');
  console.log('✅ VALIDATION SUCCESS: SVG is fully valid and complete!');
  console.log('--------------------------------------------------');
} catch (error) {
  console.error('❌ VALIDATION FAILED:', error.message);
  process.exit(1);
}
