#!/usr/bin/env python3
"""CPU-бенчмарк парка: сколько хешей в секунду даёт одна машина за фиксированное время.
Только stdlib. Использование: python3 bench.py [секунды]"""
import hashlib, json, os, platform, sys, time

def run(seconds=20.0):
    end = time.time() + seconds
    h = hashlib.sha256(b'seed')
    buf = b'x' * 4096
    n = 0
    while time.time() < end:
        for _ in range(200):
            h.update(buf)
        n += 200
    return n

def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    t0 = time.time()
    n = run(secs)
    dt = time.time() - t0
    out = {
        "host": platform.node(),
        "cpu_count": os.cpu_count(),
        "cpus_logical": len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count(),
        "python": platform.python_version(),
        "hash_updates": n,
        "seconds": round(dt, 2),
        "updates_per_sec": round(n / dt),
        "shard": os.environ.get("SHARD", "0"),
    }
    print(json.dumps(out, ensure_ascii=False))
    with open("bench_result_%s.json" % out["shard"], "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)

if __name__ == "__main__":
    main()
