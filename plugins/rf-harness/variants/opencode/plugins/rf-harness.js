// rf-harness hooks for OpenCode (ported from the measured v3.2 prototype plugin, hookpkg32 install.py OPENCODE_PLUGIN).
// Every event goes to the same launcher as the other agents: python3 -S <..>/rf-harness/bin/rfh-launch <Event>
// --agent opencode, which finds the project's Python and runs rf_harness.runtime.hook there.
//   plugin init -> SessionStart (its setup hint / context is added to the first prompt)
//   chat.message -> UserPromptSubmit (first prompt only: project context appended to the prompt text)
//   tool.execute.before -> PreToolUse (deny = throw; rewrite = mutate output.args; the Python side turns a repeated
//     denial into allow + warning after 2)
//   tool.execute.after -> PostToolUse (context PREPENDED to the tool output so a weak model reads it first)
//   assistant message finished -> Stop gate (OpenCode has no blocking stop: a noReply prompt keeps `opencode run` going)
//   dispose -> SessionEnd
// OpenCode has no hook timeout: every call is bounded here. The launcher path is resolved relative to this file
// (<root>/plugins/rf-harness.js -> <root>/rf-harness/bin/rfh-launch); RF_HARNESS_LAUNCHER overrides it and
// RF_HARNESS_LAUNCHER_PYTHON the interpreter that runs it (default: python3, on Windows `py -3`).
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const LAUNCH = process.env.RF_HARNESS_LAUNCHER || fileURLToPath(new URL("../rf-harness/bin/rfh-launch", import.meta.url));
const WIN = process.platform === "win32";
const PY = process.env.RF_HARNESS_LAUNCHER_PYTHON || (WIN ? "py" : "python3");
const PY_ARGS = process.env.RF_HARNESS_LAUNCHER_PYTHON || !WIN ? ["-S"] : ["-3", "-S"];
const LAUNCH_ARGS = [/*rf-harness:launch-args*/];
const EDIT = new Set(["write", "edit", "multiedit", "patch", "apply_patch"]);
const READ = new Set(["read", "view"]);
const RF = /\.(robot|resource)\b/;
const SHELL_PRE = /(^|[\s;&|(\/'"])(robot|robotcode|pip3?|uv|playwright|rfbrowser|npm|npx|PYTHONPATH=|cat|less)\b|PYTHONPATH|\.rf\/docs\/kw\//;
const ROBOT = /(^|[\s;&|(\/])(robot|robotcode)\s/;

// The model id goes into every payload (output profile lean|rich): `opencode run -m <provider/model>` from argv,
// OPENCODE_MODEL, then the model of the first chat message.
function argvModel() {
  const a = (typeof process !== "undefined" && process.argv) || [];
  for (let i = 0; i < a.length; i++) {
    if (a[i] === "-m" || a[i] === "--model") return String(a[i + 1] || "");
    if (String(a[i]).startsWith("--model=")) return String(a[i]).slice(8);
  }
  return (typeof process !== "undefined" && process.env && process.env.OPENCODE_MODEL) || "";
}
let MODEL = argvModel();
function modelOf(m) {
  if (!m) return "";
  if (typeof m === "string") return m;
  const id = m.modelID || m.modelId || m.id || "";
  const prov = m.providerID || m.providerId || "";
  return id ? (prov && !String(id).startsWith(prov + "/") ? prov + "/" + id : String(id)) : "";
}

// async spawn (round-5 finding: spawnSync blocked OpenCode's event loop for the whole hook, ~5 s per edit)
function call(event, payload, ms) {
  if (MODEL && payload && !payload.model) payload.model = MODEL;
  if (payload) payload.ts = Date.now();
  return new Promise((resolve) => {
    let out = "", done = false;
    const finish = (v) => { if (!done) { done = true; clearTimeout(timer); resolve(v); } };
    let p;
    try {
      p = spawn(PY, [...PY_ARGS, LAUNCH, event, "--agent", "opencode", ...LAUNCH_ARGS],
        { cwd: payload.cwd, stdio: ["pipe", "pipe", "ignore"], windowsHide: true });
    } catch (e) { return finish({}); }
    const timer = setTimeout(() => { try { p.kill("SIGKILL"); } catch (e) {} finish({}); }, ms);
    p.stdout.on("data", (d) => { out += d; });
    p.on("error", () => finish({}));
    p.on("close", () => { try { finish(out.trim() ? JSON.parse(out.trim().split("\n").pop()) : {}); } catch (e) { finish({}); } });
    try { p.stdin.end(JSON.stringify(payload)); } catch (e) {}
  });
}

export const RfHarness = async ({ directory, client }) => {
  const start = await call("SessionStart", { hook_event_name: "SessionStart", cwd: directory }, 30000);
  let sessionNote = (start && start.text) || "";
  const notes = new Map();
  let lastStopAt = 0;
  let prompted = false;
  return {
    "chat.message": async (input, output) => {
      const m = modelOf((input && input.model) || (output && output.message && output.message.model));
      if (m) MODEL = m;
      if (prompted) return;
      prompted = true;
      const res = await call("UserPromptSubmit", { hook_event_name: "UserPromptSubmit", cwd: directory,
        session_id: input && input.sessionID }, 10000);
      const tp = output && output.parts && output.parts.find((p) => p.type === "text");
      const text = [sessionNote, res.text].filter(Boolean).join("\n\n");
      sessionNote = "";
      if (text && tp) tp.text += "\n\n" + text;
    },
    "tool.execute.before": async (input, output) => {
      const tool = String(input.tool || "").toLowerCase();
      const args = output.args || {};
      const s = JSON.stringify(args);
      const want = (EDIT.has(tool) && RF.test(s)) || (tool === "bash" && SHELL_PRE.test(" " + (args.command || "")))
        || (READ.has(tool) && (/\.(xml|html?|json|log|txt|yaml|jpe?g|png)\b/.test(s) || /\.rf\/docs\/kw\//.test(s)));
      if (!want) return;
      const res = await call("PreToolUse", { hook_event_name: "PreToolUse", tool_name: input.tool, tool_input: args,
        cwd: directory, session_id: input.sessionID, call_id: input.callID }, 20000);
      if (res.action === "deny") throw new Error(res.text || "refused by the Robot Framework hook");
      if (res.action === "rewrite" && res.args) Object.assign(output.args, res.args);
      if (res.text) notes.set(input.callID, res.text);
    },
    "tool.execute.after": async (input, output) => {
      const tool = String(input.tool || "").toLowerCase();
      const args = input.args || {};
      const s = JSON.stringify(args);
      let text = notes.get(input.callID) || "";
      notes.delete(input.callID);
      if ((EDIT.has(tool) && RF.test(s)) || (tool === "bash" && ROBOT.test(" " + (args.command || "")))) {
        const res = await call("PostToolUse", { hook_event_name: "PostToolUse", tool_name: input.tool, tool_input: args,
          tool_response: output && output.output, cwd: directory, session_id: input.sessionID, call_id: input.callID },
          180000);
        text = [res.text, text].filter(Boolean).join("\n\n");
      }
      if (text && output && typeof output.output === "string")
        output.output = "[Robot Framework hook]\n" + text + "\n[/hook]\n\n" + output.output;
    },
    event: async ({ event }) => {
      const info = event.properties && event.properties.info;
      if (event.type === "message.updated" && info && info.role === "assistant" && info.finish
          && info.finish !== "tool-calls" && Date.now() - lastStopAt > 5000) {
        lastStopAt = Date.now();
        const res = await call("Stop", { hook_event_name: "Stop", cwd: directory, session_id: info.sessionID }, 90000);
        if (res.action === "block" && res.text) {
          try {
            await client.session.prompt({ path: { id: info.sessionID }, body: { noReply: true,
              parts: [{ type: "text", text: res.text }] } });
          } catch (e) {}
        }
      }
    },
    dispose: async () => { await call("SessionEnd", { hook_event_name: "SessionEnd", cwd: directory }, 5000); },
  };
};
