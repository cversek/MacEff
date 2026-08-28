#!/bin/bash
# MacEff framework shell layer: the supervised launcher.
#
# THIS IS FRAMEWORK, NOT DEPLOYMENT. It lives in framework/shell/ rather than
# framework/env.d/ because those two answer different questions and start.py
# already says so: env.d is "deployment-provided toolchain setup (conda, Lean,
# TeX), not framework semantics". A launcher that every agent needs is framework
# semantics, and putting it in env.d would mean each deployment carried its own
# copy, diverging silently. First deployment to need it is not the same as
# belonging to that deployment.
#
#     launch_cc_supervised            # start (or attach to) this agent's session
#     launch_cc_supervised --attach   # attach only; never create
#     launch_cc_supervised --stop     # stop the supervisor cleanly
#
# A FUNCTION, NOT AN ALIAS: an alias takes no arguments, returns no status, and
# does not exist in non-interactive shells.
#
# AN ENTRY POINT, NOT A SECOND IMPLEMENTATION. How the client starts -- `-c`
# continuity, the resume prompt, the load-bearing argument order for the
# variadic --channels, the proxy probe -- lives in the scripts `macf_tools
# harness generate` renders and is deliberately not restated here.

# The agent slug names both the tmux session and the supervisor registry entry.
# It comes from MACEFF_AGENT_NAME, which start.py exports from agents.yaml, so
# the session is named by the DECLARATION rather than by whatever the generator
# infers from a calling card. Override only if a deployment's existing tooling
# attaches to a different name.
MACEFF_HARNESS_SESSION="${MACEFF_HARNESS_SESSION:-${MACEFF_AGENT_NAME:-}}"

launch_cc_supervised() {
    local mode="start" regen=1
    case "${1:-}" in
        --attach)   mode="attach" ;;
        --stop)     mode="stop" ;;
        --no-regen) regen=0 ;;
        --help|-h)
            printf 'usage: launch_cc_supervised [--attach|--stop|--no-regen|--help]\n'
            return 0 ;;
        "")         ;;
        *)  printf 'launch_cc_supervised: unknown option %s (try --help)\n' "$1" >&2
            return 2 ;;
    esac

    command -v macf_tools >/dev/null 2>&1 || {
        printf 'launch_cc_supervised: macf_tools is not on PATH\n' >&2; return 1; }

    local agent="${MACEFF_HARNESS_SESSION:-}"
    if [ -z "$agent" ]; then
        # No declaration to work from. REFUSE rather than guess: a wrong session
        # name creates a second session nobody attaches to, while every command
        # reports success.
        printf 'launch_cc_supervised: MACEFF_AGENT_NAME is not set for this account; cannot name the session\n' >&2
        return 1
    fi

    local bin="$HOME/.local/bin"
    mkdir -p "$bin" || return 1
    local start="$bin/maceff_harness_start_${agent}"
    local child="$bin/maceff_cc_child_${agent}"

    # --channel is repeatable; MACEFF_CHANNELS is the space-separated list
    # start.py exports from agents.yaml claude_config.channels. Building the
    # args from the declaration is what keeps "the plugin an agent is launched
    # with" and "the plugin its home carries" the same statement.
    local chan_args=() c
    for c in ${MACEFF_CHANNELS:-}; do chan_args+=(--channel "$c"); done

    if [ "$mode" != "stop" ] && { [ "$regen" = 1 ] || [ ! -x "$start" ] || [ ! -x "$child" ]; }; then
        local tmp_s tmp_c
        tmp_s="$(mktemp "${TMPDIR:-/tmp}/maceff_start.XXXXXX")" || return 1
        tmp_c="$(mktemp "${TMPDIR:-/tmp}/maceff_child.XXXXXX")" || { rm -f "$tmp_s"; return 1; }
        if macf_tools harness generate --agent "$agent" --what start "${chan_args[@]}" > "$tmp_s" 2>/dev/null &&
           macf_tools harness generate --agent "$agent" --what child "${chan_args[@]}" > "$tmp_c" 2>/dev/null &&
           [ -s "$tmp_s" ] && [ -s "$tmp_c" ]; then
            # Placed atomically and mode 700: a truncated-then-failed write
            # leaves an executable that runs and does nothing recognisable, and
            # `chmod +x` on a mktemp file grants execute to others who cannot
            # read it, which fails as a permissions mystery.
            mv -f "$tmp_s" "$start" && mv -f "$tmp_c" "$child" && chmod 700 "$start" "$child"
        else
            rm -f "$tmp_s" "$tmp_c"
            [ -x "$start" ] && [ -x "$child" ] || {
                printf 'launch_cc_supervised: could not generate the harness for %s\n' "$agent" >&2
                return 1; }
            printf 'launch_cc_supervised: generation failed; using existing artifacts\n' >&2
        fi
        rm -f "$tmp_s" "$tmp_c" 2>/dev/null
    fi

    case "$mode" in
        stop)
            local f pid
            for f in "/tmp/macf-$(id -u)/auto-restart"/*.json \
                     "${XDG_RUNTIME_DIR:-/nonexistent}/macf/auto-restart"/*.json; do
                [ -e "$f" ] || continue
                grep -q "\"name\": \"$agent\"" "$f" 2>/dev/null || continue
                grep -q '"status": "running"' "$f" 2>/dev/null || continue
                pid="${f##*/}"; pid="${pid%.json}"
                kill -0 "$pid" 2>/dev/null || continue
                macf_tools auto-restart disable "$pid" && printf 'stopped supervisor %s for %s\n' "$pid" "$agent"
                return 0
            done
            printf 'launch_cc_supervised: no running supervisor for %s\n' "$agent" >&2
            return 1 ;;
        attach)
            tmux has-session -t "=${agent}" 2>/dev/null || {
                printf 'launch_cc_supervised: no session %s -- run launch_cc_supervised to create it\n' "$agent" >&2
                return 1; }
            tmux attach -d -t "=${agent}" ;;
        start)
            # The start script owns the create-or-not decision and exits 3 when
            # the session NAME is held by something that is not this harness --
            # a question for a human, not a retry.
            "$start" || return $?
            tmux attach -d -t "=${agent}" ;;
    esac
}
