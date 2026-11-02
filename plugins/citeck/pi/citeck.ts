import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const pluginRoot = fileURLToPath(new URL("../", import.meta.url));

// Lima exposes these guest-agent markers independently of the user's shell.
// Use wildcard binding only inside a detected Lima guest, never merely for SSH.
export function callbackEnvironment(
  env: NodeJS.ProcessEnv = process.env,
  inLima = existsSync("/run/lima-guestagent") || existsSync("/run/lima-boot-done"),
) {
  return {
    CITECK_PKCE_CALLBACK_PORT: env.CITECK_PKCE_CALLBACK_PORT ?? "19433",
    CITECK_PKCE_CALLBACK_HOST: env.CITECK_PKCE_CALLBACK_HOST ?? (inLima ? "0.0.0.0" : "127.0.0.1"),
  };
}

export default function (pi: ExtensionAPI) {
  const callback = callbackEnvironment();
  pi.registerMcpServer("citeck", {
    command: "uv",
    args: ["run", "--locked", "python", "servers/citeck_mcp.py"],
    cwd: pluginRoot,
    env: callback,
    timeout: 300,
    exposure: "deferred",
    description: "Citeck profiles, documentation, records and issue tracker. For browser login in Pi use citeck_auth, not MCP reauthenticate.",
  });

  let stopActive: (() => void) | undefined;
  pi.on("session_shutdown", async () => {
    stopActive?.();
  });

  pi.registerTool({
    name: "citeck_auth",
    label: "Citeck browser authentication",
    description: "Set up a Citeck PKCE profile or refresh its login. Shows the login URL while waiting for automatic browser callback (including Lima forwarded ports). No password or callback URL arguments. For initial setup an optional client_id selects the public OAuth client. For an existing profile use reauth=true without url or client_id. Wait for success before retrying an operation; never blindly retry a mutation with an unknown outcome.",
    parameters: Type.Object({
      profile: Type.String({ description: "Explicit target profile" }),
      url: Type.Optional(Type.String({ description: "Citeck base URL, only for initial setup" })),
      client_id: Type.Optional(Type.String({ minLength: 1, description: "Public OAuth client ID, only for initial setup" })),
      reauth: Type.Optional(Type.Boolean()),
    }),
    async execute(_id, params, signal, onUpdate, ctx) {
      if (stopActive) throw new Error("Citeck authentication is already running.");
      if (!params.profile || (!params.reauth && !params.url) || (params.reauth && (params.url !== undefined || params.client_id !== undefined))) {
        throw new Error("Provide profile and url (optionally client_id) for setup, or profile and reauth=true without url/client_id for an existing profile.");
      }
      const args = ["run", "--locked", "python", "skills/citeck-auth/scripts/setup_pkce.py", "--profile", params.profile];
      if (params.reauth) args.push("--reauth");
      else {
        args.push("--url", params.url!);
        if (params.client_id !== undefined) args.push("--client-id", params.client_id);
      }
      const child = spawn("uv", args, {
        cwd: pluginRoot,
        env: { ...process.env, ...callback, CITECK_PKCE_PROGRESS_JSON: "1" },
        stdio: ["ignore", "pipe", "pipe"],
        detached: process.platform !== "win32",
      });
      let pending = "";
      let output = "";
      const abort = () => {
        try {
          if (process.platform !== "win32" && child.pid) process.kill(-child.pid, "SIGKILL");
          else child.kill("SIGKILL");
        } catch { /* The process group may already have exited. */ }
      };
      stopActive = abort;
      signal?.addEventListener("abort", abort, { once: true });
      if (signal?.aborted) abort();
      const deadline = setTimeout(abort, 300_000);
      child.stdout?.on("data", (chunk) => { output = (output + chunk.toString()).slice(-16_384); });
      child.stderr?.on("data", (chunk) => {
        pending = (pending + chunk.toString()).slice(-32_768);
        let end: number;
        while ((end = pending.indexOf("\n")) >= 0) {
          const line = pending.slice(0, end);
          pending = pending.slice(end + 1);
          try {
            const event = JSON.parse(line);
            if (event.event === "authorization_url" && typeof event.url === "string") {
              const text = `Open this URL in the browser on your computer. The callback returns automatically through the configured port forwarding:\n${event.url}`;
              onUpdate?.({ content: [{ type: "text", text }], details: undefined });
              if (ctx.hasUI) ctx.ui.notify(text, "info");
            }
          } catch { /* Do not forward raw subprocess errors or diagnostics. */ }
        }
      });
      try {
        const code = await new Promise<number | null>((resolve, reject) => {
          child.once("error", () => reject(new Error("Cannot start Citeck authentication. Check that uv is installed and on PATH.")));
          child.once("close", resolve);
        });
        if (code !== 0) throw new Error("Citeck authentication failed, was cancelled, or timed out. Check the profile, server, callback port and Lima forwarding; no raw auth response was logged.");
        const result = JSON.parse(output);
        if (result.status !== "ok") throw new Error("Citeck authentication did not complete.");
        return {
          content: [{ type: "text", text: `Authenticated profile ${params.profile}. Verify its address with list_profiles. MCP test_connection checks only the active profile and takes no profile argument; for another profile use the auth skill's Test Connection procedure without switching shared defaults.` }],
          details: { profile: params.profile },
        };
      } finally {
        clearTimeout(deadline);
        signal?.removeEventListener("abort", abort);
        abort();
        if (stopActive === abort) stopActive = undefined;
      }
    },
  });
}
