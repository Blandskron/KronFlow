export type SendText = (text: string) => Promise<{ provider_message_id?: string } | void>;
export type TurnRequest = <T>(url: URL, payload?: object) => Promise<T>;

interface TurnSnapshot {
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
  request: TurnRequest
) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const turn = await request<TurnSnapshot>(new URL("turns/claim", base), message);
    if (!turn.claimed) {
      if (["unknown", "legacy_untracked"].includes(turn.state)) throw new Error("WhatsApp turn requires reconciliation");
      return; // completed, cancelled, or held by another invocation
    }
    const token = { claim_token: turn.claim_token };
    const action = (name: string) => new URL(`turns/${turn.turn_id}/${name}`, base);
    try {
      let prepared = turn;
      if (turn.state !== "prepared") {
        const result = await request<AgentResult>(agentUrl, {
          tenant_id: tenant,
          channel: "whatsapp",
          conversation_id: turn.external_thread_id,
          customer: { external_id: turn.phone, phone: turn.phone },
          message: { content: turn.input_body }
        });
        const response = result.reply?.content;
        if (typeof response !== "string" || !response.trim()) throw new Error("Agent returned no WhatsApp reply");
        prepared = await request<TurnSnapshot>(action("prepare"), {
          ...token, reply_body: response.slice(0, 4000), requires_human: result.requires_human === true
        });
      }
      if (prepared.state !== "prepared") return; // consent was withdrawn
      if (typeof prepared.reply_body !== "string" || !prepared.reply_body.trim()) throw new Error("Prepared turn has no reply");
      const permit = await request<TurnSnapshot>(action("begin-send"), token);
      if (!permit.claimed || permit.state !== "sending") return;
      const sent = await reply(prepared.reply_body);
      if (!sent?.provider_message_id) throw new Error("WhatsApp send returned no provider acknowledgement");
      // The acknowledgement and timestamp are frozen for all completion retries.
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
      // Server state decides whether this is recoverable. A started send can
      // only become unknown, never reset to prepared for an automatic resend.
      let released;
      try { released = await request<TurnSnapshot>(action("release"), token); } catch { throw error; }
      if (!["received", "prepared"].includes(released.state) || attempt >= 2) throw error;
      await delay(250 * 2 ** attempt);
    }
  }
}

function delay(ms: number) { return new Promise(resolve => setTimeout(resolve, ms)); }
