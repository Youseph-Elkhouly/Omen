const configuredBase = process.env.NEXT_PUBLIC_API_URL;

export function apiUrl(path: string): string {
  if (!configuredBase) throw new Error('NEXT_PUBLIC_API_URL is required.');
  return new URL(path.replace(/^\//, ''), configuredBase.endsWith('/') ? configuredBase : `${configuredBase}/`).toString();
}
