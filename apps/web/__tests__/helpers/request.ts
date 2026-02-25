import { NextRequest } from "next/server";

export function createRequest(
  method: string,
  url: string,
  body?: Record<string, unknown>,
  headers?: Record<string, string>
): NextRequest {
  const init: RequestInit = {
    method,
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
  };
  if (body) {
    init.body = JSON.stringify(body);
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return new NextRequest(new URL(url, "http://localhost:3000"), init as any);
}
