/**
 * MACF Diagnostic Logger — generalized from EXPERIMENT #1035 Phase 1 patches.
 *
 * Phase 2 of MISSION #1043 (Custom MacEff Telegram Server with Enhanced
 * Traceability and Extensibility). Extracts the macfLog instrumentation
 * pattern that was inlined as hot-patches during the disconnect investigation,
 * giving the bot a durable, opt-in diagnostic surface.
 *
 * Design:
 *  - Off by default (production): MACF_TG_DEBUG must be set to '1' (or any
 *    truthy non-empty non-'0' value) to enable. Production users not
 *    debugging shouldn't pay any cost.
 *  - Tee to stderr (with [macf-dbg] prefix for visual disambiguation) AND
 *    to a per-process JSONL file under MACF_TG_DEBUG_DIR (default
 *    /tmp/maceff/telegram-debug). The stderr stream is what CC sees if it
 *    captures bot stderr; the file persists across CC sessions for forensic
 *    analysis after a disconnect.
 *  - Schema: every event is { ts, ev, pid, ppid, uptime_s, data }. Predictable
 *    fields enable jq queries like `jq 'select(.ev == "shutdown.entry")'`
 *    across rotated logs.
 *  - Best-effort: file IO failures are silently swallowed (rotated/full disk
 *    must not crash the bot). stderr write is the primary signal channel.
 *
 * Event taxonomy (suggested vocabulary; not enforced — callers may emit any
 * event name they like, but consistency aids cross-session analysis):
 *  - 'spawn'                     — bot starting up; include argv, runtime, env
 *  - 'process.exit' / 'process.beforeExit' — bot terminating
 *  - 'signal.received'           — kernel signal delivered (SIGTERM, etc.)
 *  - 'stdin.data' / 'stdin.end' / 'stdin.close' / 'stdin.error' — MCP transport state
 *  - 'stdout.error'              — pipe broken; CC may have hung up
 *  - 'probe'                     — periodic health snapshot (stdin state)
 *  - 'mcp.connect.before' / 'mcp.connect.after' — handshake bracketing
 *  - 'mcp.call.entry' / 'mcp.call.exit' / 'mcp.call.error' — tool invocation
 *  - 'shutdown.entry' / 'shutdown.race_winner' / 'shutdown.reentry_skipped' —
 *    shutdown coordination
 *  - 'watchdog.check'            — orphan watchdog evaluation
 *  - 'bot.start' / 'bot.stop'    — grammy lifecycle
 *  - 'auth.deny' / 'auth.allow'  — access control decisions (avoid logging
 *    secrets; log decisions and chat_ids only)
 *
 * Usage:
 *   import { createDiagnosticLogger } from './lib/diagnostic-logger.ts'
 *   const log = createDiagnosticLogger()  // reads env, picks file, returns logger
 *   log('spawn', { argv: process.argv.slice(0, 3), node: process.version })
 *   ...
 *
 * Environment:
 *   MACF_TG_DEBUG          set to '1' to enable; absent or '0' disables
 *   MACF_TG_DEBUG_DIR      log directory (default /tmp/maceff/telegram-debug)
 *
 * The returned function is a no-op when disabled — callers can sprinkle
 * log() calls liberally without performance concerns when the env var is
 * not set.
 */

import { mkdirSync, writeFileSync } from 'fs'
import { join } from 'path'

export interface DiagnosticLogger {
  /** Emit a structured event. data fields are merged into the JSON line. */
  (ev: string, data?: Record<string, unknown>): void
}

export interface LoggerOptions {
  /** Override env var; default reads MACF_TG_DEBUG */
  enabled?: boolean
  /** Override env var; default reads MACF_TG_DEBUG_DIR or /tmp/maceff/telegram-debug */
  dir?: string
  /** Custom prefix for stderr lines; default '[macf-dbg]' */
  stderrPrefix?: string
}

/**
 * Create a diagnostic logger configured from env vars (or override opts).
 *
 * Returns a function. When debug is disabled, the function is a no-op —
 * callers can call it freely without paying any cost.
 */
export function createDiagnosticLogger(opts: LoggerOptions = {}): DiagnosticLogger {
  // Resolve enabled: explicit opt > env. Truthy = '1' or any non-'0' non-empty value.
  const envEnabled = process.env.MACF_TG_DEBUG
  const enabled =
    typeof opts.enabled === 'boolean'
      ? opts.enabled
      : envEnabled !== undefined && envEnabled !== '' && envEnabled !== '0'

  if (!enabled) {
    return () => {} // no-op when disabled
  }

  const dir = opts.dir ?? process.env.MACF_TG_DEBUG_DIR ?? '/tmp/maceff/telegram-debug'
  const prefix = opts.stderrPrefix ?? '[macf-dbg]'

  // Resolve file path once (per-process)
  let logFile: string | null = null
  try {
    mkdirSync(dir, { recursive: true, mode: 0o755 })
    const ts = new Date().toISOString().replace(/[:.]/g, '-').replace('Z', '')
    logFile = join(dir, `log_${ts}_pid${process.pid}.jsonl`)
  } catch {
    // dir creation failed — stderr-only mode
    logFile = null
  }

  return function log(ev: string, data: Record<string, unknown> = {}): void {
    try {
      const line =
        JSON.stringify({
          ts: new Date().toISOString(),
          ev,
          pid: process.pid,
          ppid: process.ppid,
          uptime_s: Math.round(process.uptime()),
          data,
        }) + '\n'
      process.stderr.write(`${prefix} ${line}`)
      if (logFile) writeFileSync(logFile, line, { flag: 'a' })
    } catch {
      // last-resort: never let logging crash the bot
    }
  }
}

/**
 * Convenience helper: install standard process-wide event listeners that
 * emit diagnostic events for lifecycle visibility. Returns the logger so
 * callers can also use it for ad-hoc events.
 *
 * Idempotent: safe to call multiple times in the same process (will register
 * additional listeners — but bot startup typically calls once).
 */
export function installLifecycleListeners(log: DiagnosticLogger): DiagnosticLogger {
  log('spawn', {
    argv: process.argv.slice(0, 3),
    node: process.version,
    cwd: process.cwd(),
    bun: (globalThis as { Bun?: { version: string } }).Bun?.version,
  })

  process.on('exit', code => log('process.exit', { code }))
  process.on('beforeExit', code => log('process.beforeExit', { code }))

  ;(['SIGTERM', 'SIGINT', 'SIGHUP', 'SIGPIPE', 'SIGUSR1', 'SIGUSR2'] as const).forEach(sig => {
    process.on(sig, () => log('signal.received', { sig }))
  })

  process.stdin.on('end', () =>
    log('stdin.end', {
      destroyed: process.stdin.destroyed,
      readableEnded: process.stdin.readableEnded,
    }),
  )
  process.stdin.on('close', () =>
    log('stdin.close', {
      destroyed: process.stdin.destroyed,
      readableEnded: process.stdin.readableEnded,
    }),
  )
  process.stdin.on('error', err => log('stdin.error', { msg: String(err) }))
  process.stdout.on('error', (err: NodeJS.ErrnoException) =>
    log('stdout.error', { code: err.code, msg: String(err) }),
  )

  return log
}

/**
 * Convenience helper: install a periodic probe that emits a 'probe' event
 * with stdin state. Returns the timer so callers can clear it if needed.
 *
 * The interval is .unref()'d — won't keep the event loop alive on its own.
 */
export function installProbe(log: DiagnosticLogger, intervalMs = 1000): NodeJS.Timeout {
  const t = setInterval(() => {
    log('probe', {
      stdin_destroyed: process.stdin.destroyed,
      stdin_readableEnded: process.stdin.readableEnded,
    })
  }, intervalMs)
  t.unref()
  return t
}
