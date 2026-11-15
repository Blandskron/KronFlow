import { readFileSync } from "node:fs";
import { WhatsAppConnection } from "./connection.js";
import { createHttpServer } from "./http.js";
import { operationalIngest } from "./ingest.js";

process.umask(0o077);
const connection = new WhatsAppConnection(
  process.env.BAILEYS_SESSIONS_DIR || "./sessions",
  operationalIngest(process.env)
);
const tokenFile = process.env.BAILEYS_INTERNAL_TOKEN_FILE;
const token = process.env.BAILEYS_INTERNAL_TOKEN || (tokenFile ? readFileSync(tokenFile, "utf8").trim() : "");
const server = createHttpServer(connection, token);
server.listen(Number(process.env.PORT || 3001), process.env.BAILEYS_BIND_HOST || "127.0.0.1");
