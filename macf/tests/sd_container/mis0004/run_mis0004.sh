#!/bin/bash
# Experiment 016, MIS-0004's container half. One disposable container running the prototype
# system daemon as its main command under tini, with the real amail broker and two stand-in
# receivers as its units, on three real accounts.
#
# Usage: run_mis0004.sh up|e1|e3|e2|e5|e4|e6|e7|down
#   up    starts the container, sets up accounts, boxes and config, and runs the baseline
#   e*    runs one experiment; readings go to data/<phase>*.jsonl
#   down  saves the container log and the broker audit, stops and removes the container
#
# Sources: SRC is a MacEff checkout carrying macf.sd.root (proto/sd-container-root), mounted
# read-only. Third-party packages (cryptography for amail) come from a venv volume mounted
# read-only (VENV_VOLUME), since the base image has none. Nothing on the host or in any
# deployment is written.
set -u
PHASE=${1:?phase}
HERE=$(cd "$(dirname "$0")" && pwd)
EXP=$(dirname "$HERE")
DATA=$EXP/data
SRC=${MIS0004_SRC:?set MIS0004_SRC to the macf/src of a MacEff checkout}
NAME=${MIS0004_NAME:-maceff-mis0004-proto}
IMAGE=${MACEFF_SD_PROTO_IMAGE:-maceff-sandbox:latest}
BOXA=/var/lib/amail_handoff/seat_a
BOXB=/var/lib/amail_handoff/seat_b
mkdir -p "$DATA"
x() { docker exec -i "$NAME" "$@"; }
as() { local who=$1; shift; docker exec -i "$NAME" su -s /bin/sh "$who" -c "PYTHONPATH=/proto/src /opt/maceff-venv/bin/python /proto/exp/probe.py $*"; }
hold() { x sh -c "touch /run/amail-exp/hold-$1"; }
release() { x sh -c "rm -f /run/amail-exp/hold-$1"; }
broker_pid() { x pgrep -u mail_broker -f macf.amail.daemons.broker | head -1; }

case "$PHASE" in
up)
  docker run -d --rm --name "$NAME" --init --stop-timeout 30 -v "$SRC":/proto/src:ro -v "$HERE":/proto/exp:ro -v "${VENV_VOLUME:?set VENV_VOLUME to a docker volume holding a venv with the amail extra}":/opt/maceff-venv:ro \
    -e PYTHONPATH=/proto/src --entrypoint sh "$IMAGE" -c \
    'until [ -f /etc/maceff/system.json ]; do sleep 0.2; done; exec python3 -m macf.sd.root /etc/maceff/system.json' \
    >/dev/null || exit 1
  x sh -s <<'SETUP'
set -e
for spec in seat_a:21001 seat_b:21002 mail_broker:21003; do
  n=${spec%:*}; u=${spec#*:}
  groupadd -g "$u" "$n"; useradd -u "$u" -g "$u" -M -d "/home/$n" -s /usr/sbin/nologin "$n"
  mkdir -p "/home/$n"; chown "$n:$n" "/home/$n"; chmod 700 "/home/$n"
done
install -d -o mail_broker -g mail_broker -m 0755 /var/lib/amail_broker /var/lib/amail_broker/ledger /run/amail /var/lib/amail_handoff
install -d -o mail_broker -g seat_a -m 2770 /var/lib/amail_handoff/seat_a
install -d -o mail_broker -g seat_b -m 2770 /var/lib/amail_handoff/seat_b
install -d -o root -g root -m 0755 /run/amail-exp /etc/amail /etc/maceff
cat > /var/lib/amail_broker/amail_addressing.yaml <<'EOF'
domain: proto.local
agents:
  seat_a:
    account: seat_a
    home: /home/seat_a
    contacts:
      - {address: seat_b@proto.local, direction: both}
      - {address: seat_a@proto.local, direction: both}
  seat_b:
    account: seat_b
    home: /home/seat_b
    contacts:
      - {address: seat_a@proto.local, direction: both}
      - {address: seat_b@proto.local, direction: both}
EOF
chown mail_broker:mail_broker /var/lib/amail_broker/amail_addressing.yaml; chmod 0644 /var/lib/amail_broker/amail_addressing.yaml
cat > /etc/amail/broker_config.yaml <<'EOF'
addressing_path: /var/lib/amail_broker/amail_addressing.yaml
socket_path: /run/amail/broker.sock
audit_path: /var/lib/amail_broker/audit.jsonl
inbound_handoff: /var/lib/amail_handoff
ledger_dir: /var/lib/amail_broker/ledger
EOF
chmod 0644 /etc/amail/broker_config.yaml
python3 - <<'EOF'
import json
env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": "/proto/src"}
plat = {"kind": "linux", "stop": "subreaper"}
def unit(name, account, command, **kw):
    return dict(name=name, account=account, relationship="parent", command=command, restart="always",
                liveness_interval_s=30, memory_limit_mb=256, stop_grace_s=5, platform=plat, **kw)
recv = lambda seat: unit(f"recv-{seat[-1]}", seat, ["/opt/maceff-venv/bin/python", "/proto/exp/probe.py", "receiver",
       "--seat", seat, "--home", f"/home/{seat}", "--box", f"/var/lib/amail_handoff/{seat}"],
       after=["broker"], environment=dict(env, HOME=f"/home/{seat}"))
decl = {"version": 1, "system": "mis0004-proto", "time_zone": "America/New_York", "stop_timeout_s": 30,
        "units": [unit("broker", "mail_broker", ["/opt/maceff-venv/bin/python", "-m", "macf.amail.daemons.broker"],
                       environment=dict(env, AMAIL_BROKER_CONFIG="/etc/amail/broker_config.yaml")),
                  recv("seat_a"), recv("seat_b")]}
open("/etc/maceff/system.json.new", "w").write(json.dumps(decl, indent=1))
EOF
chmod 0644 /etc/maceff/system.json.new; mv /etc/maceff/system.json.new /etc/maceff/system.json
SETUP
  for i in $(seq 1 40); do docker logs "$NAME" 2>&1 | grep -q "serving on" && break; sleep 0.5; done
  docker logs "$NAME" 2>&1 | grep -vE '"kind": "ingest"' | head -30 > "$DATA/up_log.txt"; cat "$DATA/up_log.txt"
  echo "== baseline"
  { as seat_b send --sender seat_b --to seat_a --tag baseline-b2a
    as seat_a send --sender seat_a --to seat_b --tag baseline-a2b
    sleep 3
    as seat_a store --seat seat_a --home /home/seat_a
    as seat_b store --seat seat_b --home /home/seat_b; } | tee "$DATA/baseline.jsonl"
  ;;
e1)
  hold seat_a; hold seat_b
  { as seat_b send --sender seat_b --to seat_a --n 5 --tag e1
    as seat_a stat --box $BOXA --limit 4
    as seat_b stat --box $BOXA --limit 4
    x sh -c "grep -E '^(Uid|Gid|Groups|Umask):' /proc/$(broker_pid)/status | sed 's/^/broker /'"
    as seat_a plant --box $BOXA --home /home/seat_a --kind groupwritable
    as seat_b send --sender seat_b --to seat_a --n 200 --tag e1-burst >/dev/null &
    as seat_a watch --box $BOXA --seconds 12
    wait
    x sh -c "rm -f $BOXA/*.ctl"
    as seat_a watch --box $BOXA --seconds 1; } 2>&1 | tee "$DATA/e1.jsonl"
  ;;
e3)
  { as seat_b send --sender seat_b --to seat_a seat_b --tag e3-fanout
    sleep 1
    x sh -c "for f in \$(grep -l 'e3-fanout' $BOXA/*.amsg $BOXB/*.amsg 2>/dev/null); do stat -c '%n ino=%i links=%h owner=%u group=%g mode=%a' \$f; done"; } 2>&1 | tee "$DATA/e3.jsonl"
  ;;
e2)
  { as seat_a plant --box $BOXA --home /home/seat_a --kind owned
    as seat_a plant --box $BOXA --home /home/seat_a --kind symlink
    as seat_a plant --box $BOXA --home /home/seat_a --kind hardlink
    as seat_a r37 --box $BOXA --broker-uid 21003 | python3 "$HERE/summarize.py" r37
    echo '{"kind":"note","text":"today: one ingest pass as seat_a, as main does it"}'
    as seat_a ingest --seat seat_a --home /home/seat_a --box $BOXA | grep -E 'planted'
    as seat_a store --seat seat_a --home /home/seat_a | python3 "$HERE/summarize.py" planted
  } 2>&1 | tee "$DATA/e2.jsonl"
  release seat_a; release seat_b
  ;;
e5)
  { as seat_b send --sender seat_b --claim seat_a --to seat_b --tag e5-false-claim
    as seat_b raw --json "'{\"op\": \"status\", \"sender\": \"seat_a@proto.local\"}'"
    as seat_b status
    as nobody send --sender seat_b --to seat_a --tag e5-undeclared-uid
    as seat_b stat --box $BOXA --limit 1
    as seat_a send --sender seat_a --to seat_b --tag e5-control
    as seat_a status
    x sh -c "grep -E 'e5-|refus|disagree|claim' /var/lib/amail_broker/audit.jsonl | tail -6 | cut -c1-400"; } 2>&1 | tee "$DATA/e5.jsonl"
  ;;
e4)
  { as seat_b send --sender seat_b --to seat_a --n 50 --tag e4-from-b >/tmp/e4b &
    as seat_a send --sender seat_a --to seat_a --n 50 --tag e4-from-a >/tmp/e4a &
    wait
    as seat_b send --sender seat_b --to seat_a --tag e4-collide --message-id msg-e4-collide-fixed
    as seat_b send --sender seat_b --to seat_a --tag e4-collide --message-id msg-e4-collide-fixed
    sleep 6
    as seat_a store --seat seat_a --home /home/seat_a | python3 "$HERE/summarize.py" e4; } 2>&1 | tee "$DATA/e4.jsonl"
  ;;
e6)
  { as seat_b send --sender seat_b --to seat_a --n 100 --tag e6-burst --gap 0.05 > "$DATA/e6_sender.jsonl" &
    sleep 2.5
    p=$(broker_pid); echo "{\"kind\":\"kill\",\"broker_pid\":\"$p\",\"t\":$(date +%s.%N)}"; x kill -KILL "$p"
    wait
    sleep 8
    echo "{\"kind\":\"broker_after\",\"pid\":\"$(broker_pid)\"}"
    first=$(grep -m1 -o '"broker_id": "[^"]*"' "$DATA/baseline.jsonl" | head -1 | cut -d'"' -f4)
    as seat_b send --sender seat_b --to seat_a --tag e6-repeat --message-id "$first"
    sleep 4
    as seat_a store --seat seat_a --home /home/seat_a > "$DATA/e6_store.json"
    python3 - "$DATA/e6_sender.jsonl" "$DATA/e6_store.json" "$first" <<'EOF'
import json, sys, collections
sent = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
store = json.load(open(sys.argv[2]))
ids = collections.Counter(i["id"] for i in store["items"])
ok = [s.get("broker_id") or s["id"] for s in sent if s["ok"]]; refused = [s["id"] for s in sent if not s["ok"]]
print(json.dumps({"kind": "e6_reconcile", "sent": len(sent), "accepted": len(ok), "refused_to_sender": len(refused),
                  "accepted_and_in_store": sum(1 for i in ok if ids[i] >= 1),
                  "lost": [i for i in ok if ids[i] == 0], "duplicated": [i for i in ok if ids[i] > 1],
                  "refused_but_in_store": [i for i in refused if ids[i] >= 1],
                  "repeat_id_copies_in_store": ids[sys.argv[3]],
                  "refusal_samples": list({s.get("error", "")[:120] for s in sent if not s["ok"]})[:3]}))
EOF
  } 2>&1 | tee "$DATA/e6.jsonl"
  ;;
e7)
  { hold seat_a
    as seat_b send --sender seat_b --to seat_a --n 3 --tag e7
    as seat_a status; sleep 4; as seat_a status
    release seat_a; sleep 4; as seat_a status; } 2>&1 | tee "$DATA/e7.jsonl"
  ;;
down)
  docker logs "$NAME" > "$DATA/container.log" 2>&1
  x cat /var/lib/amail_broker/audit.jsonl > "$DATA/broker_audit.jsonl" 2>/dev/null
  docker stop -t 30 "$NAME" >/dev/null   # started with --rm, so the stop removes it
  wc -l "$DATA"/container.log "$DATA"/broker_audit.jsonl
  ;;
*) echo "unknown phase $PHASE" >&2; exit 2 ;;
esac
