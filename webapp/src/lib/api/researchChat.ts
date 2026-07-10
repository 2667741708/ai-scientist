import type {
  ResearchChatCapabilitiesResponse,
  ResearchChatConfirmRequest,
  ResearchChatProgressEvent,
  ResearchChatSessionResponse,
  ResearchChatSessionsResponse,
  ResearchChatStreamEvent,
  ResearchChatTurnRequest,
  ResearchChatTurnResponse,
} from "../../types/research-chat";
import { parseApiError } from "../formatters/workbench";
import { authHeaders } from "./auth";
import { getApiBase } from "./client";

function apiFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  return globalThis["fetch"](input, {
    ...init,
    headers: authHeaders(init.headers),
  });
}

async function postJson<TResponse>(path: string, payload?: unknown) {
  const response = await apiFetch(`${getApiBase()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(parseApiError(body));
  }
  return (await response.json()) as TResponse;
}

export async function fetchResearchChatCapabilities() {
  const response = await apiFetch(`${getApiBase()}/api/research-chat/capabilities`);
  if (!response.ok) throw new Error(`research_chat_capabilities_failed_${response.status}`);
  return (await response.json()) as ResearchChatCapabilitiesResponse;
}

export async function listResearchChatSessions({ run_id, limit = 30 }: { run_id?: string | null; limit?: number } = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (run_id) params.set("run_id", run_id);
  const response = await apiFetch(`${getApiBase()}/api/research-chat/sessions?${params.toString()}`);
  if (!response.ok) throw new Error(`research_chat_sessions_failed_${response.status}`);
  return (await response.json()) as ResearchChatSessionsResponse;
}

export async function fetchResearchChatSession(sessionId: string) {
  const response = await apiFetch(`${getApiBase()}/api/research-chat/sessions/${encodeURIComponent(sessionId)}`);
  if (!response.ok) throw new Error(`research_chat_session_failed_${response.status}`);
  return (await response.json()) as ResearchChatSessionResponse;
}

export async function sendResearchChatTurn(request: ResearchChatTurnRequest) {
  return postJson<ResearchChatTurnResponse>("/api/research-chat/turn", request);
}

function parseSseBlock(block: string): ResearchChatStreamEvent | null {
  const lines = block.split(/\r?\n/);
  const event = lines.find((line) => line.startsWith("event:"))?.slice("event:".length).trim();
  const dataLines = lines.filter((line) => line.startsWith("data:")).map((line) => line.slice("data:".length).trim());
  if (!event || !dataLines.length) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) } as ResearchChatStreamEvent;
  } catch {
    return null;
  }
}

export async function streamResearchChatTurn(
  request: ResearchChatTurnRequest,
  handlers: {
    onSession?: (sessionId: string) => void;
    onProgress?: (event: ResearchChatProgressEvent) => void;
  } = {},
) {
  const response = await apiFetch(`${getApiBase()}/api/research-chat/turn/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok || !response.body) {
    const body = await response.text();
    throw new Error(parseApiError(body));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResponse: ResearchChatTurnResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (value) buffer += decoder.decode(value, { stream: !done });
    let separatorIndex = buffer.indexOf("\n\n");
    while (separatorIndex >= 0) {
      const block = buffer.slice(0, separatorIndex).trim();
      buffer = buffer.slice(separatorIndex + 2);
      const parsed = parseSseBlock(block);
      if (parsed?.event === "session") {
        handlers.onSession?.(parsed.data.session_id);
      } else if (parsed?.event === "progress") {
        handlers.onProgress?.(parsed.data);
      } else if (parsed?.event === "final") {
        finalResponse = parsed.data;
      } else if (parsed?.event === "error") {
        throw new Error(parsed.data.message || "研究聊天流式请求失败。");
      }
      separatorIndex = buffer.indexOf("\n\n");
    }
    if (done) break;
  }

  if (!finalResponse) throw new Error("研究聊天流结束但没有返回最终结果。");
  return finalResponse;
}

export async function confirmResearchChatAction(actionId: string, request: ResearchChatConfirmRequest) {
  return postJson<ResearchChatTurnResponse>(`/api/research-chat/actions/${encodeURIComponent(actionId)}/confirm`, request);
}

export async function cancelResearchChatAction(actionId: string) {
  return postJson<ResearchChatTurnResponse>(`/api/research-chat/actions/${encodeURIComponent(actionId)}/cancel`);
}
