"""
Levanta el servicio MCP de scraping. Funciona igual en Windows, macOS y Linux.

Uso (desde la raíz del proyecto, con el venv activado):
    python scripts/run_services.py
Ctrl+C detiene el servicio.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
SERVICES = [
    ("scraper", "scraper_server.py", 8101),
]


def main() -> None:
    LOGS.mkdir(exist_ok=True)
    procs = []
    for name, script, port in SERVICES:
        env = {**os.environ, "PORT": str(port), "PYTHONIOENCODING": "utf-8"}
        log = open(LOGS / f"{name}.log", "w", encoding="utf-8")
        p = subprocess.Popen(
            [sys.executable, str(ROOT / "services" / script)],
            env=env, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT,
        )
        procs.append((name, port, p, log))

    time.sleep(2)
    for name, port, p, _ in procs:
        estado = "OK" if p.poll() is None else f"FALLÓ (ver logs/{name}.log)"
        print(f"MCP {name:<8} -> http://127.0.0.1:{port}/mcp   [{estado}]")
    print("Logs en ./logs  ·  Ctrl+C para detener")

    try:
        while all(p.poll() is None for _, _, p, _ in procs):
            time.sleep(1)
        print("El servicio se detuvo; revisa la carpeta logs.")
    except KeyboardInterrupt:
        pass
    finally:
        for _, _, p, log in procs:
            p.terminate()
        for _, _, p, log in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
            log.close()
        print("Servicio detenido.")


if __name__ == "__main__":
    main()
