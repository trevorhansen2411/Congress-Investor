#!/usr/bin/env python3
# ================================================================
#  CONVICTION-CLUSTER MONITOR  —  cloud (GitHub Actions) version
#  Runs automatically every weekday morning. Reads the Quiver token
#  from an environment secret, finds fresh clusters, and writes a
#  self-updating web page (docs/index.html) + docs/current_alerts.json.
# ================================================================
import os, re, json, sys
from collections import defaultdict
from datetime import datetime, timedelta

QUIVER_TOKEN = os.environ.get("QUIVER_TOKEN", "")
if not QUIVER_TOKEN:
    print("ERROR: QUIVER_TOKEN env var not set (add it as a GitHub secret)."); sys.exit(1)

MIN_MEMBERS, WINDOW_DAYS, LOOKBACK_DAYS, LAG_DAYS = 4, 30, 200, 45
EXCLUDE = {"ro khanna"}          # hyperactive managed accounts — don't count toward conviction

import requests
try:
    import yfinance as yf
    HAVE_YF = True
except Exception:
    HAVE_YF = False

def canon(name):
    n = re.sub(r'\b(Mr|Mrs|Ms|Hon|Dr|Rep|Sen)\.?\b', '', name, flags=re.I)
    n = re.sub(r'\b(Jr|Sr|II|III|IV)\b\.?', '', n); n = re.sub(r'[."]', ' ', n)
    return " ".join(p for p in re.sub(r'\s+', ' ', n).strip().title().split() if len(p) > 1)

print("Pulling Quiver congress trades...")
r = requests.get("https://api.quiverquant.com/beta/bulk/congresstrading",
                 headers={"Authorization": f"Token {QUIVER_TOKEN}", "Accept": "application/json"}, timeout=120)
r.raise_for_status(); raw = r.json()
print(f"  {len(raw):,} records")

ev = defaultdict(list); seen = set()
for x in raw:
    if "purchase" not in str(x.get("Transaction", "")).lower() and "buy" not in str(x.get("Transaction", "")).lower():
        continue
    tk = str(x.get("Ticker", "")).upper().strip()
    d = str(x.get("TransactionDate", ""))[:10]
    m = canon(str(x.get("Representative", x.get("Name", ""))))
    if not (tk.isalpha() and 1 <= len(tk) <= 5) or not re.match(r"\d{4}-\d{2}-\d{2}", d):
        continue
    if (tk, d, m) in seen: continue
    seen.add((tk, d, m)); ev[tk].append((datetime.strptime(d, "%Y-%m-%d"), m))

today = datetime.today(); cutoff = today - timedelta(days=LOOKBACK_DAYS)
alerts = []
for tk, lst in ev.items():
    lst.sort(); n = len(lst); used = [False]*n
    for i in range(n):
        if used[i]: continue
        j = i; members = {}
        while j < n and (lst[j][0]-lst[i][0]).days <= WINDOW_DAYS:
            members.setdefault(lst[j][1], lst[j][0]); j += 1
        if len([m for m in members if m.lower() not in EXCLUDE]) >= MIN_MEMBERS:
            sig = max(members.values())
            if sig >= cutoff:
                act = sig + timedelta(days=LAG_DAYS)
                alerts.append({"ticker": tk, "signal": sig.strftime("%Y-%m-%d"), "size": len(members),
                               "members": sorted(members.keys()), "actionable": act <= today,
                               "days_live": (today-act).days})
            for k in range(i, j): used[k] = True

best = {}
for a in alerts:
    c = best.get(a["ticker"])
    if not c or (a["size"], a["signal"]) > (c["size"], c["signal"]): best[a["ticker"]] = a
alerts = sorted(best.values(), key=lambda a: (a["actionable"], a["size"], a["signal"]), reverse=True)

# current prices (best-effort)
prices = {}
if HAVE_YF and alerts:
    try:
        tks = list({a["ticker"] for a in alerts})
        data = yf.download(tks, period="5d", progress=False, group_by="ticker")
        for t in tks:
            try: prices[t] = round(float(data[t]["Close"].dropna().iloc[-1]), 2)
            except Exception: pass
    except Exception as e:
        print("price fetch skipped:", e)

os.makedirs("docs", exist_ok=True)
json.dump({"generated": today.strftime("%Y-%m-%d %H:%M UTC"), "alerts": alerts},
          open("docs/current_alerts.json", "w"), indent=2)

def hit(sz): return 60 if sz >= 5 else 53
def card(a):
    tk = a["ticker"]; p = prices.get(tk); px = f"${p:,.2f}" if p else "—"
    badge = "star" if a["size"] >= 6 else ("strong" if a["size"] >= 5 else "std")
    who = ", ".join(m.split()[-1] for m in a["members"])
    status = (f'<span class="live">● actionable — {a["days_live"]}d ago</span>' if a["actionable"]
              else '<span class="pend">◌ pending 45-day lag</span>')
    return f"""<div class="alert {badge}"><div class="ah"><div class="tk">{tk}</div>
      <div class="sz">{a['size']} members<span class="hr">~{hit(a['size'])}% hist. beat S&P (12mo)</span></div></div>
      <div class="ab">{status} · filed {a['signal']}</div>
      <div class="who"><b>Who bought:</b> {who}</div>
      <div class="af"><span class="px">Live: <b>{px}</b></span></div></div>"""

act = [a for a in alerts if a["actionable"]]; pend = [a for a in alerts if not a["actionable"]]
html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Conviction-Cluster Monitor</title><style>
:root{{--star:#eda100;--strong:#1baf7a;--std:#2a78d6;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--border:rgba(11,11,11,.1);--card:#fff;--pos:#006300}}
@media(prefers-color-scheme:dark){{:root{{--star:#c98500;--strong:#199e70;--std:#3987e5;--plane:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;--grid:#2c2c2a;--border:rgba(255,255,255,.1);--card:#1a1a19;--pos:#0ca30c}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--plane);color:var(--ink);font-family:system-ui,-apple-system,sans-serif;line-height:1.5}}
.wrap{{max-width:740px;margin:0 auto;padding:26px 18px 50px}}h1{{font-size:22px;margin:0 0 3px}}
.sub{{color:var(--ink2);font-size:13px;margin:0 0 16px}}h2.sec{{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin:20px 0 9px}}
.alert{{background:var(--card);border:1px solid var(--border);border-left:4px solid var(--std);border-radius:11px;padding:14px 16px;margin-bottom:11px}}
.alert.strong{{border-left-color:var(--strong)}}.alert.star{{border-left-color:var(--star)}}
.ah{{display:flex;justify-content:space-between;align-items:baseline}}.tk{{font-size:18px;font-weight:700}}
.sz{{text-align:right;font-weight:650;font-size:13px}}.sz .hr{{display:block;font-size:11px;font-weight:400;color:var(--pos);margin-top:1px}}
.ab{{font-size:11.5px;color:var(--ink2);margin:5px 0 3px}}.live{{color:var(--pos);font-weight:600}}.pend{{color:var(--muted);font-weight:600}}
.who{{font-size:12px;color:var(--ink2);margin:3px 0 9px}}.who b{{color:var(--ink)}}
.af{{border-top:1px solid var(--grid);padding-top:8px}}.px{{font-size:13px;color:var(--ink2)}}.px b{{color:var(--ink);font-size:15px}}
.note{{background:color-mix(in srgb,var(--star) 12%,transparent);border:1px solid var(--border);border-left:3px solid var(--star);border-radius:8px;padding:11px 14px;font-size:12px;color:var(--ink2);margin-top:16px}}.note b{{color:var(--ink)}}
.foot{{color:var(--muted);font-size:11px;margin-top:16px;text-align:center}}
</style></head><body><div class="wrap">
<h1>🔔 Conviction-Cluster Monitor</h1>
<p class="sub">Auto-updated {today.strftime("%Y-%m-%d %H:%M UTC")} · rule: {MIN_MEMBERS}+ members / {WINDOW_DAYS} days · exit: 12-mo hold</p>
<h2 class="sec">⚡ Actionable — past the 45-day lag ({len(act)})</h2>
{''.join(card(a) for a in act) or '<p class="sub">No actionable clusters right now.</p>'}
<h2 class="sec">◌ Forming — not yet public ({len(pend)})</h2>
{''.join(card(a) for a in pend) or '<p class="sub">None forming.</p>'}
<div class="note"><b>Review with Claude before trading.</b> This page is a watchlist, not an auto-trader. Bring the actionable
clusters to your Cowork chat; Claude stages each order through Robinhood's review screen for your explicit approval. Modest,
backtested edge — start small. Not investment advice.</div>
<p class="foot">Congressional Trading platform · Quiver data · refreshes weekday mornings via GitHub Actions.</p>
</div></body></html>"""
open("docs/index.html", "w").write(html)
print(f"Wrote docs/index.html — {len(act)} actionable, {len(pend)} pending.")
