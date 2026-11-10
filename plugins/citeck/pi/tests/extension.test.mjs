import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, readFileSync, rmSync, mkdirSync } from "node:fs";
import { setTimeout as delay } from "node:timers/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { execFileSync } from "node:child_process";

// Uses the installed Pi runtime, not a second bundled host API.
const install = process.env.PI_INSTALL_DIR || join(
  execFileSync("npm", ["root", "-g"], { encoding: "utf8" }).trim(),
  "@earendil-works/pi-coding-agent",
);
const { createJiti } = await import(pathToFileURL(join(install, "node_modules/jiti/lib/jiti.mjs")).href);
const jiti = createJiti(import.meta.url, {
  alias: { typebox: join(install, "node_modules/typebox/build/index.mjs") },
});
const { default: extension, callbackEnvironment } = await jiti.import(new URL("../citeck.ts", import.meta.url).pathname);

test("callback defaults require no shell configuration and detect only Lima", () => {
  assert.deepEqual(callbackEnvironment({}, false), {
    CITECK_PKCE_CALLBACK_PORT: "19433", CITECK_PKCE_CALLBACK_HOST: "127.0.0.1",
  });
  assert.deepEqual(callbackEnvironment({}, true), {
    CITECK_PKCE_CALLBACK_PORT: "19433", CITECK_PKCE_CALLBACK_HOST: "0.0.0.0",
  });
  assert.equal(callbackEnvironment({ SSH_CONNECTION: "remote" }, false).CITECK_PKCE_CALLBACK_HOST, "127.0.0.1");
  assert.deepEqual(callbackEnvironment({
    CITECK_PKCE_CALLBACK_PORT: "20500", CITECK_PKCE_CALLBACK_HOST: "127.0.0.1",
  }, true), {
    CITECK_PKCE_CALLBACK_PORT: "20500", CITECK_PKCE_CALLBACK_HOST: "127.0.0.1",
  });
});

for (const [label, source] of [
  ["root Git bridge", new URL("../../../../", import.meta.url)],
  ["nested Pi package", new URL("../../", import.meta.url)],
]) test(`Pi resource loader discovers ${label} without host configuration`, async () => {
  const directory = mkdtempSync(join(tmpdir(), "citeck package loader "));
  try {
    const agentDir = join(directory, "agent");
    const cwd = join(directory, "workspace");
    mkdirSync(agentDir);
    mkdirSync(cwd);
    writeFileSync(join(agentDir, "settings.json"), JSON.stringify({
      packages: [resolve(source.pathname)],
    }));
    const { DefaultResourceLoader } = await import(pathToFileURL(join(install, "dist/index.js")).href);
    const loader = new DefaultResourceLoader({ cwd, agentDir });
    await loader.reload();
    assert.deepEqual(loader.getExtensions().errors, []);
    assert.equal(loader.getSkills().skills.filter(s => s.name.startsWith("citeck-")).length, 6);
    assert.ok(loader.getExtensions().extensions.some(e => e.tools.has("citeck_auth")));
    const registration = loader.getExtensions().runtime.mcpServers.get("citeck");
    assert.equal(registration.config.cwd, resolve(new URL("../../", import.meta.url).pathname) + "/");
    assert.equal(loader.getExtensions().runtime.mcpServers.list().length, 1);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("shutdown terminates an active auth process and its descendant", {
  timeout: 10_000, skip: process.platform === "win32",
}, async (t) => {
  const directory = mkdtempSync(join(tmpdir(), "citeck shutdown "));
  const previous = { ...process.env };
  let pids = [];
  let waiting;
  let shutdown;
  t.after(async () => {
    await shutdown?.();
    for (const pid of pids) {
      try { process.kill(pid, "SIGKILL"); } catch { /* Already exited. */ }
    }
    await waiting?.catch(() => {});
    process.env = previous;
    rmSync(directory, { recursive: true, force: true });
  });
  writeFileSync(join(directory, "uv"), `#!${process.execPath}\n` + `
const {spawn} = require('node:child_process');
const {writeFileSync} = require('node:fs');
const child = spawn(process.execPath, ['-e', 'setInterval(()=>{},1000)'], {stdio:'ignore'});
child.once('spawn', () => {
  writeFileSync(process.env.CITECK_TEST_PIDS, JSON.stringify([process.pid, child.pid]));
  process.stderr.write(JSON.stringify({event:'authorization_url',url:'https://id.invalid/auth'})+'\\n');
});
setInterval(()=>{},1000);
`, { mode: 0o700 });
  process.env.PATH = directory + ":" + previous.PATH;
  process.env.HOME = directory;
  process.env.CITECK_TEST_PIDS = join(directory, "pids.json");
  let tool;
  extension({
    registerMcpServer() {},
    registerTool(value) { tool = value; },
    on(event, handler) { if (event === "session_shutdown") shutdown = handler; },
  });
  const progress = Promise.withResolvers();
  waiting = tool.execute("shutdown", {profile:"fixture",reauth:true}, undefined,
    () => progress.resolve(), {hasUI:false});
  await Promise.race([progress.promise, waiting]);
  pids = JSON.parse(readFileSync(process.env.CITECK_TEST_PIDS, "utf8"));
  for (const pid of pids) assert.doesNotThrow(() => process.kill(pid, 0));
  await shutdown();
  await assert.rejects(waiting, /cancelled/);
  const running = (pid) => {
    try {
      process.kill(pid, 0);
      // A zombie is terminated and merely awaiting reaping by the guest init.
      if (process.platform === "linux") return !/\) Z /.test(readFileSync(`/proc/${pid}/stat`, "utf8"));
      return true;
    } catch (error) {
      if (error.code === "ESRCH" || error.code === "ENOENT") return false;
      throw error;
    }
  };
  for (let attempt = 0; attempt < 80 && pids.some(running); attempt++) await delay(25);
  assert.ok(pids.every(pid => !running(pid)), "auth parent and descendant must both be terminated");
});

test("registration, auth progress, redaction, mutual exclusion and cancellation", { timeout: 10_000 }, async () => {
  const directory = mkdtempSync(join(tmpdir(), "citeck pi with spaces "));
  const previous = { ...process.env };
  try {
    const fake = join(directory, "uv");
    writeFileSync(fake, `#!${process.execPath}\n` + `
if (process.argv.includes('--url') && (
    process.argv[process.argv.indexOf('--client-id') + 1] !== 'custom-client')) process.exit(3);
if (process.argv.includes('failure')) {
  process.stderr.write('sensitive-server-response'); process.exit(1);
}
if (process.env.CITECK_PKCE_CALLBACK_PORT !== '19433' ||
    !['127.0.0.1','0.0.0.0'].includes(process.env.CITECK_PKCE_CALLBACK_HOST)) process.exit(2);
process.stderr.write(JSON.stringify({event:'authorization_url',url:'https://id.invalid/auth?state=synthetic'})+'\\n');
if (process.argv.includes('waiting')) setInterval(()=>{}, 1000);
else process.stdout.write(JSON.stringify({status:'ok'}));
`, { mode: 0o700 });
    process.env.PATH = directory + ":" + previous.PATH;
    process.env.HOME = directory;
    delete process.env.CITECK_PKCE_CALLBACK_PORT;
    delete process.env.CITECK_PKCE_CALLBACK_HOST;
    let registration, tool;
    const hooks = {};
    extension({
      registerMcpServer(name, config) { registration = { name, config }; },
      registerTool(value) { tool = value; },
      on(event, handler) { hooks[event] = handler; },
    });
    assert.equal(registration.name, "citeck");
    assert.equal(registration.config.exposure, "deferred");
    assert.equal(registration.config.timeout, 300);
    assert.deepEqual(registration.config.env, callbackEnvironment({}));
    assert.equal(registration.config.cwd, resolve(new URL("../../", import.meta.url).pathname) + "/");
    const updates = [];
    const context = { hasUI: false };
    const result = await tool.execute("a", {profile:"fixture",url:"https://fixture.invalid",client_id:"custom-client"}, undefined,
      (value) => updates.push(value), context);
    assert.equal(result.details.profile, "fixture");
    assert.match(updates[0].content[0].text, /https:\/\/id.invalid\/auth/);
    await assert.rejects(tool.execute("b", {profile:"failure",reauth:true}, undefined, undefined, context),
      (error) => !error.message.includes("sensitive-server-response"));
    await assert.rejects(tool.execute("bad", {profile:"fixture",reauth:true,client_id:"other"}, undefined, undefined, context), /without url\/client_id/);
    const controller = new AbortController();
    let received;
    const progress = new Promise((resolve) => { received = resolve; });
    const waiting = tool.execute("c", {profile:"waiting",reauth:true}, controller.signal,
      () => received(), context);
    await Promise.race([progress, waiting]);
    await assert.rejects(tool.execute("d", {profile:"fixture",reauth:true}, undefined, undefined, context), /already running/);
    controller.abort();
    await assert.rejects(waiting, /cancelled/);
    await hooks.session_shutdown();
  } finally {
    process.env = previous;
    rmSync(directory, { recursive: true, force: true });
  }
});
