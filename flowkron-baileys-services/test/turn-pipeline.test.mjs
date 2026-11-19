import assert from "node:assert/strict";
import test from "node:test";
import { processTurn } from "../dist/turn-pipeline.js";

const base = new URL("http://operational/api/v1/ingest/whatsapp/");
const agentUrl = new URL("http://agent/api/v1/agent/internal/whatsapp/1");

function scenario(options = {}) {
  let state = options.state ?? "generating";
  const calls = [];
  let generationFailures = options.generationFailures ?? 0;
  let persistFailures = options.persistFailures ?? 0;
  let lostPrepare = options.lostPrepare ?? false;
  let lostBegin = options.lostBegin ?? false;
  let lostCompletion = options.lostCompletion ?? false;
  let savedReply;
  let sends = 0;
  const request = async (url, payload) => {
    const operation = url.href === agentUrl.href ? "agent" : url.pathname.split("/").at(-1);
    calls.push({ operation, payload });
    if (operation === "claim") return { turn_id: 9, state, claimed: ["generating", "prepared"].includes(state),
      claim_token: "original-claim-token", input_body: "Original accepted input", phone: "12025550138",
      external_thread_id: "original-thread", reply_body: savedReply };
    if (operation === "agent") {
      if (generationFailures-- > 0) throw new Error("Injected agent failure");
      return { reply: { content: "Persist this answer" }, requires_human: true };
    }
    if (operation === "prepare") {
      state = "prepared";
      savedReply = payload.reply_body;
      if (lostPrepare) { lostPrepare = false; throw new Error("Prepare response lost after commit"); }
      return { state, reply_body: savedReply };
    }
    if (operation === "begin-send") {
      state = "sending";
      if (lostBegin) throw new Error("Send permit response lost after commit");
      return { state, claimed: true };
    }
    if (operation === "complete") {
      if (persistFailures-- > 0) throw new Error("Injected persistence failure");
      state = "completed";
      if (lostCompletion) { lostCompletion = false; throw new Error("Completion response lost after commit"); }
      return { state };
    }
    if (operation === "release") {
      if (state === "sending") state = "unknown";
      return { state: state === "generating" ? "received" : state };
    }
    throw new Error(`Unexpected operation ${operation}`);
  };
  const reply = async () => {
    sends++;
    if (options.sendFailure) throw new Error("Provider timeout after accepting the send");
    return options.noAcknowledgement ? undefined : { provider_message_id: "real-outgoing-id" };
  };
  const run = () => processTurn({ body: "Changed replay input" }, reply, base, agentUrl, "1", request);
  return { run, calls, get sends() { return sends; }, get state() { return state; } };
}

test("agent failure resumes the accepted input and sends once", async () => {
  const run = scenario({ generationFailures: 1 });
  await run.run();
  assert.equal(run.sends, 1);
  const generations = run.calls.filter(call => call.operation === "agent");
  assert.equal(generations.length, 2);
  assert.ok(generations.every(call => call.payload.message.content === "Original accepted input"));
});

test("lost prepare response reuses the persisted answer without calling the model again", async () => {
  const run = scenario({ lostPrepare: true });
  await run.run();
  assert.equal(run.sends, 1);
  assert.equal(run.calls.filter(call => call.operation === "agent").length, 1);
});

test("lost send permission never causes an unconfirmed send or a blind retry", async () => {
  const run = scenario({ lostBegin: true });
  await assert.rejects(run.run());
  await assert.rejects(run.run(), /requires reconciliation/);
  assert.equal(run.sends, 0);
  assert.equal(run.state, "unknown");
});

test("provider timeout never retries a possibly accepted send", async () => {
  const run = scenario({ sendFailure: true });
  await assert.rejects(run.run());
  await assert.rejects(run.run(), /requires reconciliation/);
  assert.equal(run.sends, 1);
  assert.equal(run.state, "unknown");
});

test("missing provider acknowledgement is unknown, not a successful delivery", async () => {
  const run = scenario({ noAcknowledgement: true });
  await assert.rejects(run.run());
  assert.equal(run.state, "unknown");
  assert.equal(run.calls.filter(call => call.operation === "complete").length, 0);
});

test("completion retries preserve acknowledgement and timestamp without sending again", async () => {
  const run = scenario({ persistFailures: 2 });
  await run.run();
  const completions = run.calls.filter(call => call.operation === "complete");
  assert.equal(completions.length, 3);
  assert.ok(completions.every(call => call.payload === completions[0].payload));
  assert.equal(completions[0].payload.provider_message_id, "real-outgoing-id");
  assert.equal(run.sends, 1);
});

test("completion response lost after commit is acknowledged without another send", async () => {
  const run = scenario({ lostCompletion: true });
  await run.run();
  await run.run();
  assert.equal(run.sends, 1);
  assert.equal(run.state, "completed");
});

test("persistent completion failure leaves an observable unknown result", async () => {
  const run = scenario({ persistFailures: 3 });
  await assert.rejects(run.run());
  await assert.rejects(run.run(), /requires reconciliation/);
  assert.equal(run.sends, 1);
  assert.equal(run.state, "unknown");
});

test("cancelled and completed turns have no model or transport effects", async () => {
  for (const state of ["cancelled", "completed"]) {
    const run = scenario({ state });
    await run.run();
    assert.equal(run.sends, 0);
    assert.deepEqual(run.calls.map(call => call.operation), ["claim"]);
  }
});
