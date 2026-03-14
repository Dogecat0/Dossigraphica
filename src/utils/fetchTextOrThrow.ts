export type FetchErrorType = 'MISSING_FILE' | 'NETWORK_OFFLINE' | 'CAPTIVE_PORTAL' | 'UNKNOWN';

export class FetchError extends Error {
  type: FetchErrorType;
  constructor(message: string, type: FetchErrorType) {
    super(message);
    this.name = 'FetchError';
    this.type = type;
  }
}

/**
 * Fetches text content from a URL, explicitly throwing categorized errors
 * to prevent silent failures or parsing of captive portal HTML pages.
 */
export async function fetchTextOrThrow(url: string, expectedType: 'text/markdown' | 'application/json' = 'text/markdown'): Promise<string> {
  if (!navigator.onLine) {
    throw new FetchError(`Network is offline. Cannot fetch ${url}`, 'NETWORK_OFFLINE');
  }

  let response: Response;
  try {
    response = await fetch(url);
  } catch (error) {
     throw new FetchError(`Network error fetching ${url}`, 'NETWORK_OFFLINE');
  }

  if (response.status === 404) {
    throw new FetchError(`File not found at ${url}`, 'MISSING_FILE');
  }

  if (!response.ok) {
     throw new FetchError(`HTTP error ${response.status} fetching ${url}`, 'UNKNOWN');
  }

  const contentType = response.headers.get('content-type');
  
  // Guard against captive portals which return HTML 200 OK
  if (contentType?.includes('text/html')) {
     throw new FetchError(`Expected ${expectedType} but received HTML. Possible captive portal or misconfigured server at ${url}`, 'CAPTIVE_PORTAL');
  }

  return response.text();
}
