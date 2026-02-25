const DISCORD_WEBHOOK_URL = process.env.DISCORD_WEBHOOK_URL;
const RATE_LIMIT_MS = 5_000;
let lastSent = 0;

export async function reportError(
  error: unknown,
  context?: Record<string, string>,
) {
  if (!DISCORD_WEBHOOK_URL) return;

  // Simple rate limit — don't flood Discord
  const now = Date.now();
  if (now - lastSent < RATE_LIMIT_MS) return;
  lastSent = now;

  const err =
    error instanceof Error ? error : new Error(String(error));

  const fields = Object.entries(context || {}).map(([name, value]) => ({
    name,
    value: value.slice(0, 256),
    inline: true,
  }));

  try {
    await fetch(DISCORD_WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        embeds: [
          {
            title: err.message.slice(0, 200),
            description: `\`\`\`\n${err.stack?.slice(0, 1500) ?? "no stack"}\n\`\`\``,
            color: 0xc4694f,
            fields,
            timestamp: new Date().toISOString(),
          },
        ],
      }),
    });
  } catch {
    // Never throw from the error reporter
  }
}
