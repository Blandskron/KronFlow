import { readFileSync } from "node:fs";
import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { WhatsAppConnection } from "./connection.js";
import { createHttpServer } from "./http.js";
import { operationalIngest, tenantIngest } from "./ingest.js";

process.umask(0o077);
const directory = process.env.BAILEYS_SESSIONS_DIR || "./sessions";
const tokenFile = process.env.BAILEYS_INTERNAL_TOKEN_FILE;
const token = process.env.BAILEYS_INTERNAL_TOKEN || (tokenFile ? readFileSync(tokenFile, "utf8").trim() : "");
const operational = process.env.OPERATIONAL_SERVICE_URL || "http://flowkron-operational-service:8001";
const agent = process.env.AGENT_CORE_URL || "http://flowkron-agent-core:8002";
const legacy = new WhatsAppConnection(directory, operationalIngest(process.env));
const sessions = new Map<string, WhatsAppConnection>();
function tenantSession(id: string) {
  let session = sessions.get(id);
  if (!session) {
    session = new WhatsAppConnection(join(directory, `tenant-${id}`), tenantIngest(id, token, operational, agent));
    sessions.set(id, session);
  }
  return session;
}

const server = createHttpServer(legacy, token, tenantSession);
server.listen(Number(process.env.PORT || 3001), process.env.BAILEYS_BIND_HOST || "127.0.0.1");

async function restoreSessions() {
  const names = await readdir(directory).catch(() => []);
  for (const name of names) {
    const tenant = /^tenant-([1-9][0-9]{0,14})$/.exec(name);
    if (!tenant) continue;
    try {
      const state = JSON.parse(await readFile(join(directory, name, "creds.json"), "utf8"));
      if (state.registered === true) await tenantSession(tenant[1]).start();
    } catch {
      console.warn("Could not restore a WhatsApp session");
    }
  }
}

void restoreSessions();
