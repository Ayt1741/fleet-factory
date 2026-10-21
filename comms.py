#!/usr/bin/env python3
"""СВЯЗЬ МЕЖДУ ВСЕМИ МАШИНАМИ — ntfy.sh как живая шина (без аккаунта и ключей).

Ограничения ntfy.sh (docs.ntfy.sh/publish, проверено 21.10.2026):
  сообщение <= 4096 байт, 250 сообщений в сутки, запросы: 60 залпом, потом 1 в 5 с,
  вложение <= 2 МБ (20 МБ на посетителя), вложения живут 3 часа.
Поэтому: короткие сообщения — сюда (живая связь), файлы и история — в git-репозиторий.

Команды:
  presence <канал> <полоса> <текст>    «я на связи»
  council  <канал> <полоса> <мнение>   мнение (слепое чтение: без подписи в тексте)
  post     <канал> <полоса> <тип> <текст>
  read     <канал> [since]
  tally    <канал> [since]             сводка: кто на связи, сколько мнений
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
DEFAULT_CHANNEL = os.environ.get("COUNCIL_CHANNEL", "arena-council-7k3m9p2x")


def _req(url, data=None, timeout=25):
    r = urllib.request.Request(url, data=data, headers={"User-Agent": "arena-fleet-comms/1.0"},
                               method="POST" if data else "GET")
    with urllib.request.urlopen(r, timeout=timeout) as x:
        return x.read()


def post(channel, lane, kind, text, priority=3, tags=()):
    body = json.dumps({"topic": channel, "message": text[:3800], "title": "%s:%s" % (kind, lane),
                       "tags": list(tags), "priority": priority}).encode("utf-8")
    for _ in range(4):
        try:
            raw = _req(SERVER + "/", data=body)
            return json.loads(raw).get("id", "?")
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(6)
                continue
            raise
    raise RuntimeError("ntfy отверг сообщение 4 раза (лимит 429)")


def read(channel, since="all"):
    raw = _req("%s/%s/json?poll=1&since=%s" % (SERVER, channel, since))
    out = []
    for line in raw.decode("utf-8", "ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("event") == "message":
            out.append(ev)
    return out


def blind_opinions(events):
    return [e["message"] for e in events if str(e.get("title", "")).startswith("council:")]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd == "post":
        _, _, channel, lane, kind, *rest = sys.argv
        print(json.dumps({"ok": True, "id": post(channel, lane, kind, " ".join(rest))}))
    elif cmd == "read":
        channel = sys.argv[2]
        since = sys.argv[3] if len(sys.argv) > 3 else "all"
        evs = read(channel, since)
        print(json.dumps([{"id": e["id"], "time": e["time"], "title": e.get("title"), "message": e["message"]}
                          for e in evs], ensure_ascii=False, indent=2))
    elif cmd == "presence":
        channel, lane = sys.argv[2], sys.argv[3]
        print(json.dumps({"ok": True, "lane": lane,
                          "id": post(channel, lane, "presence", "%s на связи | %s" % (lane, " ".join(sys.argv[4:])), tags=["wave"])}))
    elif cmd == "council":
        channel, lane = sys.argv[2], sys.argv[3]
        print(json.dumps({"ok": True, "lane": lane,
                          "id": post(channel, lane, "council", " ".join(sys.argv[4:]))}))
    elif cmd == "tally":
        channel = sys.argv[2]
        since = sys.argv[3] if len(sys.argv) > 3 else "all"
        evs = read(channel, since)
        on_air = sorted({str(e.get("title", "")).split(":", 1)[1] for e in evs
                         if str(e.get("title", "")).startswith("presence:")})
        print(json.dumps({"messages": len(evs), "on_air": len(on_air), "lanes": on_air,
                          "opinions": len(blind_opinions(evs)),
                          "kinds": dict(Counter(str(e.get("title", "")).split(":")[0] for e in evs))},
                         ensure_ascii=False, indent=2))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
