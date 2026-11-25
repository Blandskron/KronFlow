export type SendText = (text: string, providerMessageId?: string) => Promise<{ provider_message_id?: string } | void>;
export type TurnRequest = <T>(url: URL, payload?: object) => Promise<T>;

export interface TurnSnapshot {
  turn_id: number | null;
  state: "received" | "generating" | "prepared" | "sending" | "completed" | "unknown" | "cancelled" | "legacy_untracked";
  claimed: boolean;
  claim_token: string | null;
  input_body: string | null;
  phone: string | null;
  external_thread_id: string | null;
  reply_body: string | null;
}

interface AgentResult { reply?: { content?: unknown }; requires_human?: boolean }

/** Resume only stages whose external outcome is known to be safe to repeat. */
export async function processTurn(
  message: object,
  reply: SendText,
  base: URL,
  agentUrl: URL,
  tenant: string,
  request: TurnRequest,
  canReply = () => true
) {
  for (let attempt = 0; attempt < 3; attempt++) {
    if (!canReply()) return;
    const turn = await request<TurnSnapshot>(new URL("turns/claim", base), message);
    if (!turn.claimed) {
      if (["unknown", "legacy_untracked"].includes(turn.state)) throw new Error("WhatsApp turn requires reconciliation");
      return; // completed, cancelled, or held by another invocation
    }
    const failure = await advanceTurn(turn, reply, base, agentUrl, tenant, request, canReply);
    if (!failure) return;
    if (!failure.retryable || attempt >= 2) throw failure.error;
    await delay(250 * 2 ** attempt);
  }
}

export async function advanceTurn(
  turn: TurnSnapshot,
  reply: SendText,
  base: URL,
  agentUrl: URL,
  tenant: string,
  request: TurnRequest,
  canReply: () => boolean,
  providerMessageId?: string
): Promise<{ error: unknown; retryable: boolean } | undefined> {
  const token = { claim_token: turn.claim_token };
  const action = (name: string) => new URL(`turns/${turn.turn_id}/${name}`, base);
  const release = () => request<TurnSnapshot>(action("release"), token);
  let releaseOnError = true;
  try {
    let prepared = turn;
    if (turn.state !== "prepared" && canReply()) {
      const result = await request<AgentResult>(agentUrl, {
        tenant_id: tenant,
        channel: "whatsapp",
        conversation_id: turn.external_thread_id,
        customer: { external_id: turn.phone, phone: turn.phone },
        message: { content: turn.input_body }
      });
      const response = result.reply?.content;
      if (typeof response !== "string" || !response.trim()) throw new Error("Agent returned no WhatsApp reply");
      if (canReply()) {
        prepared = await request<TurnSnapshot>(action("prepare"), {
          ...token, reply_body: response.slice(0, 4000), requires_human: result.requires_human === true
        });
      }
    }
    if (!canReply()) {
      releaseOnError = false;
      await release();
      return;
    }
    if (prepared.state !== "prepared") return;
    if (typeof prepared.reply_body !== "string" || !prepared.reply_body.trim()) throw new Error("Prepared turn has no reply");
    const permit = await request<TurnSnapshot>(action("begin-send"), {
      ...token, provider_message_id: providerMessageId
    });
    if (!permit.claimed || permit.state !== "sending") return;
    if (!canReply()) throw new Error("WhatsApp send interrupted");
    const sent = await reply(prepared.reply_body, providerMessageId);
    if (!sent?.provider_message_id) throw new Error("WhatsApp send returned no provider acknowledgement");
    if (providerMessageId && sent.provider_message_id !== providerMessageId) {
      throw new Error("WhatsApp returned a different message identity");
    }
    const completed = { ...token, provider_message_id: sent.provider_message_id, sent_at: new Date().toISOString() };
    for (let persistAttempt = 0; ; persistAttempt++) {
      try {
        await request(action("complete"), completed);
        return;
      } catch (error) {
        if (persistAttempt >= 2) throw error;
        await delay(250 * 2 ** persistAttempt);
      }
    }
  } catch (error) {
    // A started send can only become unknown. Release never permits a resend.
    if (!releaseOnError) return { error, retryable: false };
    try {
      const released = await release();
      return { error, retryable: ["received", "prepared"].includes(released.state) };
    } catch {
      return { error, retryable: false };
    }
  }
}

function delay(ms: number) { return new Promise(resolve => setTimeout(resolve, ms)); }
