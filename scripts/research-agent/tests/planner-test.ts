import { runPlannerNode } from '../nodes/planner';
import { ResearchState } from '../state';

async function test() {
  const dummyState: ResearchState = {
    ticker: 'NVDA',
    companyName: 'NVIDIA Corporation',
    userQuery: 'Generate a comprehensive GeoIntelligence dossier for NVDA',
    researchPlan: '',
    searchQueries: [],
    rawExtractedData: [],
    scrapedUrls: new Set(),
    iterationCount: 0,
    isComplete: false,
    knowledgeGaps: [],
    finalIntelJson: null,
    finalReportMarkdown: null
  };

  try {
    const output = await runPlannerNode(dummyState);
    console.log('Success! Final State Planner output:');
    console.log('Plan:', output.researchPlan);
    console.log('Queries:', output.searchQueries);
  } catch (err) {
    console.error('Test Failed:', err);
  }
}

test();
