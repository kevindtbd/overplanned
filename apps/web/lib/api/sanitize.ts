/** Strip control chars and HTML tags from user input */
export function sanitize(input: string, maxLen = 5000): string {
  return input
    .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, "")
    .replace(/<[^>]*>/g, "")
    .trim()
    .slice(0, maxLen);
}
