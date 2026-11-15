import { WhatsAppConnection } from "./connection.js";
import { createHttpServer } from "./http.js";
import { operationalIngest } from "./ingest.js";

process.umask(0o077);
const connection = new WhatsAppConnection(
  process.env.BAILEYS_SESSIONS_DIR || "./sessions",
  operationalIngest(process.env)
);
const server = createHttpServer(connection, process.env.BAILEYS_INTERNAL_TOKEN || "");
server.listen(Number(process.env.PORT || 3001), process.env.BAILEYS_BIND_HOST || "127.0.0.1");
