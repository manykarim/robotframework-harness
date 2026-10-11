// OpenCode 1.15 probe plugin: logs every plugin hook + bus event to $HOOK_CELL/hooks.jsonl and emulates the
// harness behaviours (context marker, PreToolUse rewrite/deny, Stop-continue, helper start/stop).
// Copy to <project>/.opencode/plugins/ (auto-loaded) — behaviour from $HOOK_CELL/behavior.json (same keys as hooklog.py).
import { appendFileSync, readFileSync, existsSync, writeFileSync } from "fs"
import { spawn } from "child_process"
import path from "path"

const CELL = process.env.HOOK_CELL || process.cwd()
const LOG = path.join(CELL, "hooks.jsonl")
const HELPER = process.env.HOOK_HELPER
let B = {}
try { B = JSON.parse(readFileSync(path.join(CELL, "behavior.json"), "utf8")) } catch (e) {}
const rnd = () => Math.random().toString(16).slice(2, 6)
const log = (event, rec) => appendFileSync(LOG, JSON.stringify({ wall: Date.now() / 1000, agent: "opencode", event, src: "plugin", pid: process.pid, ...rec }) + "\n")
const short = (v, n = 1500) => { try { const s = typeof v === "string" ? v : JSON.stringify(v); return s && s.length > n ? s.slice(0, n) + "…" : s } catch (e) { return String(v) } }
const sleep = (s) => new Promise((r) => setTimeout(r, s * 1000))

export const RfProbe = async (ctx) => {
  log("plugin_init", { phase: "start", ctx_keys: Object.keys(ctx), directory: ctx.directory, worktree: ctx.worktree, serverUrl: String(ctx.serverUrl), client_session_keys: Object.keys(ctx.client?.session ?? {}) })
  if (B.SS?.start_daemon && HELPER) {
    const p = spawn("setsid", ["-f", "/usr/bin/python3", HELPER, CELL], { detached: true, stdio: "ignore" })
    p.unref()
    log("plugin_init", { phase: "daemon", note: "setsid helper spawned" })
  }
  const sysSeen = new Set()
  let stopDone = false
  // Stop-gate emulation without idle: insert a user message (noReply) while the loop is still running, so the
  // loop's "latest user message newer than latest assistant" check keeps it going (works in headless `opencode run`?)
  const injectContinue = async (sid, how) => {
    stopDone = true
    const marker = `ZQX-STOP-${rnd()}`
    const text = `${marker}: the RF harness requires one more step before you finish: create the file stop_proof.txt in the project root containing the word CONTINUED, then finish and include this ZQX marker in your final answer.`
    try {
      const r = await ctx.client.session.prompt({ path: { id: sid }, body: { noReply: true, parts: [{ type: "text", text }] } })
      log("stop_emulation", { phase: "end", how, marker, result: short(r?.data ?? r, 300) })
    } catch (e) { log("stop_emulation", { phase: "error", how, marker, error: String(e) }) }
  }
  return {
    event: async ({ event }) => {
      log("event:" + event.type, { phase: "event", props: short(event.properties, 600) })
      const info = event.properties?.info
      if (event.type === "message.updated" && B.STOP?.stop === "msg_finish" && !stopDone && info?.role === "assistant"
          && info.finish && info.finish !== "tool-calls") {
        await injectContinue(info.sessionID, "msg_finish")
      }
      if (event.type === "session.idle" && B.STOP?.stop === "block_once" && !stopDone) {
        stopDone = true
        const sid = event.properties?.sessionID
        const marker = `ZQX-STOP-${rnd()}`
        const text = `${marker}: the RF harness requires one more step before you finish: create the file stop_proof.txt in the project root containing the word CONTINUED, then finish and include this ZQX marker in your final answer.`
        try {
          // v1 SDK shape first, then v2 shape
          let r
          if (ctx.client.session.promptAsync) {
            r = await ctx.client.session.promptAsync({ path: { id: sid }, body: { parts: [{ type: "text", text }] } })
          } else {
            r = await ctx.client.session.prompt({ path: { id: sid }, body: { parts: [{ type: "text", text }] } })
          }
          log("stop_emulation", { phase: "end", marker, result: short(r, 400) })
        } catch (e) {
          log("stop_emulation", { phase: "error", marker, error: String(e) })
        }
      }
    },
    "chat.message": async (input, output) => {
      const marker = `ZQX-UPS-${rnd()}`
      log("chat.message", { phase: "start", input: short(input, 600), parts: output.parts?.map((p) => p.type) })
      if (B.UPS?.context !== false) {
        const tp = output.parts?.find((p) => p.type === "text")
        if (tp) tp.text += `\n\n[hook context] ${marker}`
        log("chat.message", { phase: "end", marker })
      }
    },
    "experimental.chat.system.transform": async (input, output) => {
      const key = input.sessionID ?? "none"
      if (sysSeen.has(key)) return
      sysSeen.add(key)
      const marker = `ZQX-SYS-${rnd()}`
      if (B.SYS?.mode === "append0") output.system[0] = output.system[0] + `\n\nSession context from the RF harness: ${marker}`
      else output.system.push(`Session context from the RF harness: ${marker}`)
      log("experimental.chat.system.transform", { phase: "end", marker, sessionID: input.sessionID, nsys: output.system.length })
    },
    "tool.execute.before": async (input, output) => {
      log("tool.execute.before", { phase: "start", input, args: short(output.args) })
      const fp = output.args?.filePath ?? output.args?.file_path ?? output.args?.path ?? ""
      if (B.PRE?.pre === "robot" && String(fp).endsWith(".robot")) {
        const marker = `ZQX-PRE-${rnd()}`
        if (path.basename(fp).includes("deny")) {
          log("tool.execute.before", { phase: "end", decision: "deny", marker })
          throw new Error(`${marker}: the RF harness blocks writing files whose name contains 'deny'. Write the same content to tests/allowed.robot instead.`)
        }
        for (const k of ["content", "newString", "new_string"]) {
          if (typeof output.args[k] === "string" && output.args[k].includes("Clik")) output.args[k] = output.args[k].replaceAll("Clik", "Click")
        }
        if (typeof output.args.content === "string") output.args.content += "\n# rewritten-by-pretool-hook\n"
        log("tool.execute.before", { phase: "end", decision: "rewrite", marker, args: short(output.args) })
      }
      const cmd = String(output.args?.command ?? "")
      if (B.PRE_bash?.only_cmd && new RegExp(B.PRE_bash.only_cmd).test(cmd) && B.PRE_bash.exit) {
        log("tool.execute.before", { phase: "end", decision: "crash", cmd })
        throw new Error("probe crash in tool.execute.before")
      }
    },
    "tool.execute.after": async (input, output) => {
      const t0 = Date.now()
      const isBash = input.tool === "bash"
      const beh = isBash ? (B.POST_bash ?? B.POST ?? {}) : (B.POST ?? {})
      log("tool.execute.after", { phase: "start", input: short(input, 800), title: output.title, output: short(output.output, 600), metadata_keys: Object.keys(output.metadata ?? {}), exit: output.metadata?.exit })
      if (beh.sleep && !(beh.only_tools && !new RegExp(`^(?:${beh.only_tools})$`).test(input.tool))) await sleep(beh.sleep)
      const marker = `ZQX-POST-${rnd()}`
      if (beh.context !== false && typeof output.output === "string") output.output += `\n\n[RF harness] ${marker} (tool=${input.tool})`
      log("tool.execute.after", { phase: "end", marker, secs: (Date.now() - t0) / 1000 })
    },
    "experimental.text.complete": async (input, output) => {
      log("experimental.text.complete", { phase: "start", input, text: short(output.text, 200) })
      if (B.STOP?.stop === "text_complete" && !stopDone) await injectContinue(input.sessionID, "text_complete")
    },
    "shell.env": async (input, output) => {
      output.env.RF_HELPER_HINT = "set-by-plugin"
      log("shell.env", { phase: "end", input: short(input, 300) })
    },
    "experimental.session.compacting": async (input, output) => {
      log("experimental.session.compacting", { phase: "start", input })
    },
    "command.execute.before": async (input, output) => {
      log("command.execute.before", { phase: "start", input })
    },
    dispose: async () => {
      log("dispose", { phase: "start" })
      if (B.SE?.stop_daemon) {
        try { const pid = parseInt(readFileSync(path.join(CELL, "helper.pid"), "utf8")); process.kill(pid, "SIGTERM"); log("dispose", { phase: "end", note: "helper SIGTERM" }) } catch (e) { log("dispose", { phase: "error", error: String(e) }) }
      }
    },
  }
}
