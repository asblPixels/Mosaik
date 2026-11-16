// Mosaïk en ligne — remplace le serveur local : l'interface parle au moteur via un Web Worker.
(function () {
  "use strict";
  const FAMILIES = {"jpg": "Photos JPEG", "png": "Images PNG", "gif": "Images GIF", "bmp": "Images BMP", "pdf": "PDF", "zip": "Office / LibreOffice / ZIP", "riff": "WAV / AVI / WEBP", "mp4": "Vidéos MP4 / MOV / M4A / HEIC", "mp3": "Musique MP3", "sqlite": "Bases SQLite"};
  const VERSION = "2.2.0";
  const now = () => new Date().toTimeString().slice(0, 8);
  let worker = null, files = [], extras = [];
  let st = { phase: "attente", running: false, size: 0, pos: 0, speed: 0, eta: 0, elapsed: 0,
             map: "", counts: {}, bad: 0, out: "", log: [], message: "", source: "" };

  function start(cfg) {
    files.forEach(f => URL.revokeObjectURL(f.url));
    files = []; extras = [];
    st = Object.assign(st, { phase: "chargement", running: true, pos: 0, size: M.file.size, map: "",
      counts: {}, bad: 0, message: "", source: M.file.name,
      log: [now() + "  Chargement du moteur Mosaïk dans le navigateur (une seule fois, ~14 Mo)…"] });
    worker = new Worker("app/worker.mjs", { type: "module" });
    worker.onmessage = (e) => {
      const m = e.data;
      if (m.type === "ready") st.log = st.log.concat([now() + "  Moteur prêt : analyse de " + M.file.name]);
      else if (m.type === "status") { delete m.status.files; Object.assign(st, m.status); st.out = ""; }
      else if (m.type === "file") {
        const blob = new Blob([m.bytes]);
        Object.assign(m.meta, { id: files.length, url: URL.createObjectURL(blob), blob });
        files.push(m.meta);
      }
      else if (m.type === "extra") extras.push({ name: m.name, blob: new Blob([m.bytes]) });
      else if (m.type === "error") fail(m.message);
    };
    worker.onerror = (e) => fail(e.message || "Erreur du moteur");
    worker.postMessage({ type: "start", file: M.file, cfg });
  }
  function fail(msg) {
    st.phase = "erreur"; st.running = false; st.message = msg;
    st.log = st.log.concat([now() + "  Erreur : " + msg]);
  }

  // ── ZIP minimal (sans compression) : aucune bibliothèque externe ──
  const CRC = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
  const crc32 = (u8) => { let c = 0xFFFFFFFF; for (let i = 0; i < u8.length; i++) c = CRC[(c ^ u8[i]) & 255] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; };
  async function buildZip(entries) {
    const enc = new TextEncoder(), parts = [], central = [];
    let offset = 0;
    for (const e of entries) {
      const data = new Uint8Array(await e.blob.arrayBuffer()), name = enc.encode(e.name), crc = crc32(data);
      const h = new DataView(new ArrayBuffer(30));
      h.setUint32(0, 0x04034b50, true); h.setUint16(4, 20, true); h.setUint16(6, 0x0800, true);
      h.setUint32(14, crc, true); h.setUint32(18, data.length, true); h.setUint32(22, data.length, true);
      h.setUint16(26, name.length, true);
      parts.push(h, name, data);
      const c = new DataView(new ArrayBuffer(46));
      c.setUint32(0, 0x02014b50, true); c.setUint16(4, 20, true); c.setUint16(6, 20, true); c.setUint16(8, 0x0800, true);
      c.setUint32(16, crc, true); c.setUint32(20, data.length, true); c.setUint32(24, data.length, true);
      c.setUint16(28, name.length, true); c.setUint32(42, offset, true);
      central.push(c, name);
      offset += 30 + name.length + data.length;
    }
    const csize = central.reduce((s, p) => s + p.byteLength, 0);
    const end = new DataView(new ArrayBuffer(22));
    end.setUint32(0, 0x06054b50, true); end.setUint16(8, entries.length, true); end.setUint16(10, entries.length, true);
    end.setUint32(12, csize, true); end.setUint32(16, offset, true);
    return new Blob([...parts, ...central, end], { type: "application/zip" });
  }
  function save(blob, name) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 60000);
  }

  const M = window.MosaikWeb = {
    file: null,
    async api(p, body) {
      const [path, q] = p.split("?");
      if (path === "/api/info") return { version: VERSION, root: false, web: true, out: "", families: FAMILIES, tsk: false, tsk_hint: "" };
      if (path === "/api/devices") return [];
      if (path === "/api/status") {
        const since = +(new URLSearchParams(q || "").get("since") || 0);
        return Object.assign({}, st, { files: files.slice(since), total_files: files.length });
      }
      if (path === "/api/start") {
        if (!M.file) throw { erreur: "Choisissez d'abord une image disque." };
        if (typeof Worker === "undefined" || typeof WebAssembly === "undefined")
          throw { erreur: "Ce navigateur est trop ancien : utilisez une version récente de Firefox, Chrome, Edge ou Safari." };
        start(body); return { ok: true };
      }
      if (path === "/api/stop") {
        if (worker) { worker.terminate(); worker = null; }
        st.running = false; st.phase = "arrete";
        st.log = st.log.concat([now() + "  Analyse arrêtée. " + files.length + " fichier(s) déjà récupéré(s)."]);
        return { ok: true };
      }
      return { ok: true };
    },
    download(id) { const f = files[id]; if (f) save(f.blob, f.name); },
    async zipAll() {
      const entries = files.map(f => ({ name: f.cat + "/" + f.name, blob: f.blob })).concat(extras.map(x => ({ name: x.name, blob: x.blob })));
      save(await buildZip(entries), "mosaik-" + (st.source || "recuperation").replace(/\.[^.]+$/, "") + ".zip");
    },
  };

  // Démonstration / test automatique : ?demo=chemin/vers/image.img
  const demo = new URLSearchParams(location.search).get("demo");
  if (demo) fetch(demo).then(r => r.blob()).then(b => {
    M.file = new File([b], demo.split("/").pop());
    const go = () => { const t = document.getElementById("go"); if (!t) return setTimeout(go, 100);
      document.getElementById("drop").querySelector("b").textContent = "✔ " + M.file.name;
      window.dispatchEvent(new Event("mosaik-demo")); };
    go();
  });
})();
