// Preload with `node --require` (NODE_OPTIONS) to make any network connection fail, as
// it would offline, and append "host:port" to the file in MKCD2APP_TEST_BLOCKED_LOG. Node
// ignores HTTP_PROXY by default, so a dead proxy alone wouldn't block anything. Local
// connections and pipes are allowed, since build tools use them to talk to themselves.
const fs = require("node:fs");
const net = require("node:net");

const LOOPBACK = new Set(["localhost", "127.0.0.1", "::1"]);
const connect = net.Socket.prototype.connect;

net.Socket.prototype.connect = function (...args) {
  // net.connect() passes [options, callback] as one array, internally
  const first = Array.isArray(args[0]) ? args[0][0] : args[0];
  const options =
    typeof first === "object" ? first : { port: first, host: args[1] };
  const host = options.host ?? "localhost";
  if (options.path || LOOPBACK.has(host)) {
    return connect.apply(this, args);
  }

  fs.appendFileSync(
    process.env.MKCD2APP_TEST_BLOCKED_LOG,
    `${host}:${options.port}\n`,
  );
  const error = new Error(`Network blocked by test: ${host}:${options.port}`);
  error.code = "ENETUNREACH";
  process.nextTick(() => this.destroy(error));
  return this;
};
