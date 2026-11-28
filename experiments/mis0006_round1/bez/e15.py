"""E15, whose turn: on voice days, the share of operator-originated drives that were dictated (H15 as amended
2026-11-25: dictation alone decides). Day is the resampling unit. Prints figures only.
usage: e15.py DRIVES_JSON"""
import sys, json, collections, random, re

SEED, B = 20261123, 10000
d = json.load(open(sys.argv[1]))
dr = [x for x in d["drives"] if x["day"] >= "2026-11-18"]
OPER = {"typed", "dictated", "telegram", "dictated_socket"}


def run(dictated_classes, label):
    per = collections.defaultdict(lambda: collections.Counter())
    for x in dr: per[x["day"]][x["cls"]] += 1
    vdays = sorted(k for k, c in per.items() if any(c[k2] for k2 in dictated_classes))
    rows = []
    for day in vdays:
        c = per[day]; op = sum(c[k] for k in OPER if k in dictated_classes or k in ("typed", "telegram"))
        dic = sum(c[k] for k in dictated_classes)
        rows.append((day, dic, op))
    share = lambda rs: sum(r[1] for r in rs) / max(1, sum(r[2] for r in rs))
    rnd = random.Random(SEED); boots = sorted(share([rnd.choice(rows) for _ in rows]) for _ in range(B))
    lo, hi = boots[int(0.025 * B)], boots[int(0.975 * B) - 1]
    over = sum(1 for r in rows if r[1] / r[2] > 0.5)
    print(f"\n[{label}] voice days: {len(rows)}")
    for r in rows: print(f"  {r[0]}: dictated {r[1]} of {r[2]} operator-originated drives = {r[1]/r[2]:.2f}")
    print(f"  pooled share {share(rows):.3f}, 95% interval by day [{lo:.3f}, {hi:.3f}]; days over 0.5: {over} of {len(rows)}")
    if len(rows) < 10: verdict = "NOT REACHED (fewer than ten voice days)"
    elif over > len(rows) / 2 and lo > 0.5: verdict = "VALIDATED"
    elif hi < 0.5: verdict = "CONTRADICTED"
    else: verdict = "NOT REACHED"
    print(f"  H15: {verdict}")
    return rows, vdays


rows, vdays = run({"dictated"}, "primary: dictated = voice channel messages")
run({"dictated", "dictated_socket"}, "beside: voice channel plus daemon-labelled dictation delivered over the session socket")

vd = set(vdays)
on = [x for x in dr if x["day"] in vd]
cnt = collections.Counter(x["cls"] for x in on)
op = sum(cnt[k] for k in OPER)
print("\nBeside, deciding nothing (voice days of the primary reading):")
print(f"  drives by class: {dict(cnt)}")
print(f"  any channel (dictated + socket dictation + Telegram) share of operator-originated: {(cnt['dictated'] + cnt['dictated_socket'] + cnt['telegram']) / op:.3f}")
print(f"  share of all drives no operator opened: {sum(v for k, v in cnt.items() if k not in OPER) / sum(cnt.values()):.3f}")
dic = [x for x in on if x["cls"] == "dictated"]
shallow = [x for x in dic if len(x["text"].split()) < 10]
print(f"  dictated utterances under ten words (my reading of the draft's 'shallow operator prompt', which it does not define): {len(shallow)} of {len(dic)} = {len(shallow)/max(1,len(dic)):.2f}")
marks = collections.Counter()
for x in [y for y in dr if y["cls"] in ("dictated", "dictated_socket")]:
    h = x["raw_head"]
    if re.search(r'screen="locked"|screen locked', h): marks["screen locked"] += 1
    if re.search(r'screen="(unknown|)"', h): marks["screen state unknown"] += 1
    if re.search(r'information_only="true"|information only', h): marks["information only"] += 1
    if re.search(r'voice_lock="not_declared"|voice lock not declared', h): marks["no voice lock declared (speaker unverified)"] += 1
print(f"  dictated drives (both routes, {sum(1 for y in dr if y['cls'] in ('dictated','dictated_socket'))}) by mark: {dict(marks)}")
trig = collections.Counter(x["trigger"] for x in dic)
print(f"  dictated by trigger: {dict(trig)}")
print(f"  framework keystroke records available from: the event log's keys_sent (62 records, from 2026-11-24 23:36); earlier framework-typed notices were known by their fixed openings")
