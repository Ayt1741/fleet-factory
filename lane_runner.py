#!/usr/bin/env python3
"""Одна машина завода = одна «полоса» руководителя.

Использование: python3 lane_runner.py L1-a
Что делает: находит свою полосу в lanes.json, берёт свою задачу из tasks/<L>.json
(детерминированно: слот a — первая задача, слот b — вторая), выполняет её
и пишет результат в results/<lane>.json. Только stdlib, без сети.

Детерминированное назначение выбрано намеренно: двадцать машин работают
одновременно и не должны спорить за один и тот же файл. Динамический захват
(claim с повтором через git push) — следующий шаг, он требует записи в репозиторий.
"""
import hashlib
import json
import os
import sys
import time
import platform
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load(path, default=None):
    p = ROOT / path
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def work(task, seconds=8.0):
    """Полезная нагрузка: считаем простые числа и хеши, чтобы машина реально работала."""
    end = time.time() + seconds
    h = hashlib.sha256(task["id"].encode())
    n = 0
    primes = 0
    candidate = 2
    while time.time() < end:
        for i in range(500):
            candidate += 1
            h.update(str(candidate).encode())
            n += 1
            if all(candidate % d for d in range(2, int(candidate ** 0.5) + 1)):
                primes += 1
    return {"hash_updates": n, "primes_found": primes, "digest": h.hexdigest()[:32]}


def main():
    lane_id = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LANE", "")
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else float(os.environ.get("SECONDS", "8"))
    cfg = load("lanes.json")
    lane = next((x for x in cfg["lanes"] if x["lane"] == lane_id), None)
    if not lane:
        print("НЕИЗВЕСТНАЯ ПОЛОСА:", lane_id)
        return 2
    leader, slot = lane["leader"], lane["slot"]
    tasks = load(f"tasks/{leader}.json", {"tasks": []})["tasks"]
    if slot >= len(tasks):
        print(f"{lane_id}: задач на слот {slot} нет")
        return 3
    task = tasks[slot]
    t0 = time.time()
    result = work(task, seconds)
    dt = round(time.time() - t0, 2)
    out = {
        "lane": lane_id, "leader": leader, "role": lane["role"], "task": task,
        "machine": {"host": platform.node(), "cores": os.cpu_count(),
                    "cpu_affinity": len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
                    "os": platform.platform()},
        "seconds": dt, "result": result, "status": "done", "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / f"{lane_id}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
