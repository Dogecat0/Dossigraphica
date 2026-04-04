export function extractJsonFromReasoning(raw: string): string {
  const thinkClose = raw.lastIndexOf('</think>');
  let content = raw;
  if (thinkClose !== -1) {
    content = raw.slice(thinkClose + '</think>'.length).trim();
  }

  // Handle markdown code block wrap if it exists
  const codeBlockMatch = content.match(/```json\s*([\s\S]*?)```/);
  if (codeBlockMatch) {
    return codeBlockMatch[1].trim();
  }

  return content.trim();
}
