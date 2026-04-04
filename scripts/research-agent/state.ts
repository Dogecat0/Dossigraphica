import { GeoIntelligence } from "../../src/types";

export interface ExtractedFact {
  fact: string;
  sourceUrl: string;
  sourceTitle: string;
}

export interface ResearchState {
  // Input
  ticker: string;
  companyName: string;
  userQuery: string;

  // Planning
  researchPlan: string;
  searchQueries: string[];

  // Data accumulation
  rawExtractedData: ExtractedFact[];
  scrapedUrls: Set<string>;

  // Control flow
  iterationCount: number;
  isComplete: boolean;
  knowledgeGaps: string[];

  // Output
  finalIntelJson: GeoIntelligence | null;
  finalReportMarkdown: string | null;
}
