#!/bin/bash
# The MIS-0007 container prototype's harness (draft, #855). It runs macf.sd.root as a disposable
# container's main command, under tini, on the sandbox image, with synthetic accounts and stand-in
# units, and prints what each measurement found.
#
# Usage: run_prototype.sh [subreaper|marker] [docker stop timeout in s, default 60]
#   subreaper  the prototype: a per-unit supervisor as the unit's account, subreaper of its tree
#   marker     the comparison: no supervisor, a stop finds processes by the MACEFF_SD_UNIT marker
#
# It creates one container, maceff-sd-proto-<mode>, and removes it when it's done. Nothing else on
# the host is touched; the branch's source is mounted read-only, so no account inside can write the
# code root runs.
set -u
MODE=${1:-subreaper}
STOP_T=${2:-60}
SRC=$(cd "$(dirname "$0")/../../src" && pwd)
NAME=maceff-sd-proto-$MODE
IMAGE=${MACEFF_SD_PROTO_IMAGE:-maceff-sandbox:latest}
FLAG=""
[ "$MODE" = marker ] && FLAG="--experiment-stop-by-marker-only"
x() { docker exec -i "$NAME" "$@"; }

docker rm -f "$NAME" >/dev/null 2>&1
docker run -d --name "$NAME" --init --stop-timeout "$STOP_T" -v "$SRC":/proto/src:ro -e PYTHONPATH=/proto/src \
  --entrypoint sh "$IMAGE" -c \
  'until [ -f /etc/maceff/system.json ]; do sleep 0.2; done; exec python3 -m macf.sd.root /etc/maceff/system.json "$@"' \
  sd $FLAG >/dev/null || exit 1

x sh -s <<'SETUP'
set -e
groupadd -g 21100 mailers
for spec in seat_a:21001 seat_b:21002 mail_broker:21003 tester:21004; do
  n=${spec%:*}; u=${spec#*:}
  useradd -u "$u" -U -M -d "/home/$n" -s /usr/sbin/nologin "$n"
  mkdir -p "/home/$n"; chown "$n:$n" "/home/$n"; chmod 700 "/home/$n"
done
usermod -aG mailers seat_a
mkdir -p /opt/sd-units /etc/maceff
cat > /opt/sd-units/idle <<'EOF'
#!/bin/sh
trap 'exit 0' TERM
while :; do sleep 0.2; done
EOF
cat > /opt/sd-units/graceful <<'EOF'
#!/bin/sh
echo "$(date +%T) up" >> stop.log
trap 'echo "$(date +%T) TERM: stopping over ${STOP_TAKES_S}s" >> stop.log; sleep "$STOP_TAKES_S"; echo "$(date +%T) stopped cleanly" >> stop.log; exit 0' TERM
while :; do sleep 0.2; done
EOF
cat > /opt/sd-units/escapee <<'EOF'
#!/bin/sh
# Two detached workers in sessions of their own that ignore TERM and HUP. One keeps the
# environment, marker included; the other clears it. Then the unit's main process ends.
setsid sh -c 'trap "" TERM HUP; exec sleep 100000' &
setsid env -i /bin/sh -c 'trap "" TERM HUP; exec sleep 100001' &
sleep 3
exit 78
EOF
cat > /opt/sd-units/exits <<'EOF'
#!/bin/sh
sleep 1
exit "$EXIT_WITH"
EOF
chmod 755 /opt/sd-units/*
SETUP

# R03, R04, R06: the loader's refusals, by --check, before the real declaration exists.
x python3 - <<'DECL'
import json
unit = lambda name, account, cmd, restart="always", grace=2, **kw: dict(
    name=name, account=account, relationship="parent", command=[cmd], restart=restart, liveness_interval_s=30,
    memory_limit_mb=64, stop_grace_s=grace, platform={"kind": "linux", "stop": "subreaper"},
    environment={"PATH": "/usr/bin:/bin", **kw.pop("env", {})}, **kw)
units = [
    unit("broker", "mail_broker", "/opt/sd-units/idle", grace=5),
    unit("seat-a", "seat_a", "/opt/sd-units/graceful", grace=30, after=["broker"], groups=["mailers"],
         env={"STOP_TAKES_S": "25"}),
    unit("seat-b", "seat_b", "/opt/sd-units/idle", grace=5, after=["broker"]),
    unit("escapee", "tester", "/opt/sd-units/escapee"),
] + [unit(f"exit{c}-{r}", "tester", "/opt/sd-units/exits", restart=r, env={"EXIT_WITH": str(c)})
     for c, r in ((78, "always"), (0, "always"), (0, "on-failure"), (1, "on-failure"), (1, "never"))]
decl = {"version": 1, "system": "sd-proto", "time_zone": "America/New_York", "stop_timeout_s": 60, "units": units}
open("/root/system.json", "w").write(json.dumps(decl, indent=1))
open("/root/too-tight.json", "w").write(json.dumps(dict(decl, stop_timeout_s=30)))
DECL
x sh -s <<'CHECKS'
cd /root
chmod 644 system.json too-tight.json
cp system.json owned.json; chown seat_a owned.json
cp system.json gw.json; chmod 664 gw.json
ln -s system.json link.json
cp system.json hard.json; ln hard.json hard2.json
for f in system.json owned.json gw.json link.json hard.json too-tight.json; do
  out=$(python3 -m macf.sd.root --check "/root/$f" 2>&1); rc=$?
  echo "check $f: exit $rc :: $(printf '%s\n' "$out" | tail -1 | cut -c1-300)"
done
CHECKS

echo "== start (stop by $MODE, docker stop timeout ${STOP_T}s)"
x sh -c 'cp /root/system.json /etc/maceff/system.json.new && chmod 644 /etc/maceff/system.json.new && mv /etc/maceff/system.json.new /etc/maceff/system.json'
sleep 12

echo "== processes 12 s after start"
x ps -eo pid,ppid,uid,stat,args --forest | grep -v 'ps -eo'

echo "== R08, R12, R13: seat-a's main process, as root reads it"
x sh -c 'p=$(pgrep -f "^/bin/sh /opt/sd-units/graceful" | head -1); echo "pid $p"; grep -E "^(Uid|Gid|Groups):" /proc/$p/status
  echo "environ, read by root:"; tr "\0" "\n" < /proc/$p/environ
  echo "environ, read by seat_a:"; su -s /bin/sh seat_a -c "tr \"\\\\0\" \"\\\\n\" < /proc/$p/environ"
  echo "root capabilities:"; grep CapEff /proc/self/status'

echo "== R05: what the escapee left once its main process ended (exit 78, so it stays stopped)"
x sh -c 'pgrep -a -f "sleep 10000[01]" || echo "nothing left"'

echo "== R07: the status socket, asked by seat_b to stop the broker"
x su -s /bin/sh seat_b -c "python3 -c \"import socket; s=socket.socket(socket.AF_UNIX); s.connect('/run/maceff-sd/status.sock'); s.sendall(b'stop broker'); print(s.recv(1<<16).decode())\"" \
  | python3 -c 'import json,sys; st=json.load(sys.stdin); print({k: st[k] for k in ("time_zone","stop","stop_timeout_s","longest_stop_s","longest_stop_chain","egress_rule")}); [print("  ", u) for u in st["units"]]'

echo "== R20: docker stop -t $STOP_T"
t0=$(date +%s.%N); docker stop -t "$STOP_T" "$NAME" >/dev/null; t1=$(date +%s.%N)
python3 -c "print(f'docker stop took {$t1-$t0:.1f} s')"
echo "-- seat-a's own record of its stop"
docker cp "$NAME":/home/seat_a/stop.log - 2>/dev/null | tar -xO
echo "-- the system daemon's record"
docker logs "$NAME" 2>&1 | python3 -c '
import json, sys, collections
counts = collections.Counter()
for line in sys.stdin:
    try:
        e = json.loads(line)
    except ValueError:
        print("   (not json)", line.rstrip()[:160]); continue
    if e["event"] == "unit_exited" and e.get("decision") != "stopping":
        counts[(e["unit"], e["code"], e["decision"])] += 1
        continue
    if e["event"] == "unit_started" and e["unit"].startswith("exit"):
        continue
    print("  ", json.dumps(e)[:300])
print("   exits, outside the stop:")
for (u, c, d), n in sorted(counts.items()):
    print(f"     {u}: exit {c} -> {d} (x{n})")
'
docker rm "$NAME" >/dev/null
