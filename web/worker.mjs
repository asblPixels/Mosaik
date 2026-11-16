// Mosaïk en ligne — moteur Python (Pyodide) exécuté dans un Web Worker.
// L'image disque est lue directement sur l'ordinateur (WORKERFS) : rien n'est envoyé sur internet.
import { loadPyodide } from "../pyodide/pyodide.mjs";

const PY = `
import sys, json, time, os
sys.path.insert(0, "/app")
import mosaik, js
J = mosaik.JOB
J.reset()
J.running = True
J.source = IMG_PATH
_last = [0.0]

def _tick(force=False):
    now = time.time()
    if force or now - _last[0] > 0.25:
        _last[0] = now
        js.sendStatus(json.dumps(J.status(1 << 30)))

def _onfile(meta):
    m = dict(meta)
    js.sendFile(m["path"], json.dumps(m))
    _tick()

J.on_tick = _tick
J.on_file = _onfile
cfg = json.loads(CFG_JSON)
cfg.update(source=IMG_PATH, out="/out", tsk=False, clone=False, hashdb="")
mosaik.run_scan(cfg, J)
for n in ("rapport.csv", "LISEZMOI.txt"):
    p = os.path.join(J.out_dir, n)
    if os.path.exists(p):
        js.sendExtra(p, n)
J.on_tick = None
_tick(True)
`;

self.onmessage = async (e) => {
  const { file, cfg } = e.data;
  try {
    const py = await loadPyodide({ indexURL: new URL("../pyodide/", import.meta.url).href });
    const code = await (await fetch(new URL("mosaik.py", import.meta.url))).text();
    py.FS.mkdirTree("/app");
    py.FS.writeFile("/app/mosaik.py", code);
    py.FS.mkdirTree("/img");
    py.FS.mount(py.FS.filesystems.WORKERFS, { files: [file] }, "/img");
    self.sendStatus = (json) => postMessage({ type: "status", status: JSON.parse(json) });
    self.sendFile = (path, meta) => {
      const bytes = py.FS.readFile(path);
      postMessage({ type: "file", meta: JSON.parse(meta), bytes }, [bytes.buffer]);
      py.FS.unlink(path);
    };
    self.sendExtra = (path, name) => {
      const bytes = py.FS.readFile(path);
      postMessage({ type: "extra", name, bytes }, [bytes.buffer]);
    };
    postMessage({ type: "ready" });
    py.globals.set("IMG_PATH", "/img/" + file.name);
    py.globals.set("CFG_JSON", JSON.stringify(cfg));
    py.runPython(PY);
  } catch (err) {
    postMessage({ type: "error", message: String((err && err.message) || err) });
  }
};
