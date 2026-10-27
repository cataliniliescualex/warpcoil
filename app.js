/*
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.
*/

(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const boot = window.LOCALDROP_BOOT || {};
  let token = boot.token || sessionStorage.getItem("localdrop_token") || "";
  let processing = false;
  let paused = false;
  let currentController = null;
  let wakeResume = null;
  const queue = [];
  const diagEntries = [];
  const chunkTimeLimitMs = 45000;

  function ms(n) { return Number.isFinite(Number(n)) ? Math.round(Number(n)) + " ms" : "n/a"; }
  function diag(message) {
    const line = new Date().toLocaleTimeString("en-GB", { hour12: false }) + "  " + message;
    diagEntries.push(line);
    if (diagEntries.length > 35) diagEntries.shift();
    $("diagnostic-log").textContent = diagEntries.join("\n");
  }
  diag("WarpCoil 1.3.2 active; diagnostics ready.");

  $("copy-diagnostics").addEventListener("click", async () => {
    const report = "WarpCoil 1.3.2\n" + $("speed-result").textContent + "\n" + diagEntries.join("\n");
    try {
      await navigator.clipboard.writeText(report);
      $("copy-diagnostics").textContent = "Copied ✓";
      setTimeout(() => { $("copy-diagnostics").textContent = "Copy diagnostics"; }, 1600);
    } catch {
      window.prompt("Select and copy the diagnostics:", report);
    }
  });

  $("speed-test").addEventListener("click", async () => {
    const button = $("speed-test");
    if (processing) {
      $("speed-result").textContent = "Wait for the transfer to finish before testing the network.";
      return;
    }
    button.disabled = true;
    $("speed-result").textContent = "Testing 8 MB between iPhone and PC…";
    // Exactly the same 2 MiB PUT shape as the real upload, but no disk IO.
    const chunk = new Uint8Array(2 * 1024 * 1024);
    chunk.fill(0x5a);
    let sent = 0;
    let totalServerReadMs = 0;
    const t0 = performance.now();
    try {
      for (let i = 0; i < 4; i++) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), chunkTimeLimitMs);
        try {
          const res = await fetch("/api/bench", {
            method: "PUT",
            headers: { "X-LocalDrop-Token": token,
                       "Content-Type": "application/octet-stream" },
            body: chunk.buffer,
            signal: controller.signal,
            cache: "no-store",
          });
          const data = await res.json();
          if (!res.ok || data.bytes !== chunk.byteLength) throw new Error(data.error || "Invalid test response");
          sent += data.bytes;
          totalServerReadMs += data.serverReadMs || 0;
          $("speed-result").textContent = `Local test: ${i+1}/4 chunks sent…`;
        } finally { clearTimeout(timeout); }
      }
      const seconds = (performance.now() - t0) / 1000;
      const mbps = sent * 8 / seconds / 1e6;
      const result = `Local network: ${mbps.toFixed(1)} Mbps (${humanSize(sent/seconds)}/s) · ` +
                     `8 MB in ${seconds.toFixed(2)} s · server read time ${Math.round(totalServerReadMs)} ms`;
      $("speed-result").textContent = result;
      diag("TEST LOCAL: " + result);
    } catch (err) {
      const message = `Local test failed: ${err.message || String(err)}`;
      $("speed-result").textContent = message;
      diag(message);
    } finally { button.disabled = false; }
  });

  function getClientId() {
    let value = localStorage.getItem("localdrop_client");
    if (!value || !/^[a-f0-9]{32}$/.test(value)) {
      const bytes = new Uint8Array(16);
      crypto.getRandomValues(bytes);
      value = Array.from(bytes, (v) => v.toString(16).padStart(2, "0")).join("");
      localStorage.setItem("localdrop_client", value);
    }
    return value;
  }

  function humanSize(n) {
    if (n < 1024) return n + " B";
    const units = ["KB", "MB", "GB", "TB"];
    let i = -1;
    do { n /= 1024; i++; } while (n >= 1024 && i < units.length - 1);
    return n.toFixed(n >= 10 ? 1 : 2).replace(/\.0+$/, "") + " " + units[i];
  }

  function fileFingerprint(file) {
    // Do not read the file before uploading: some iOS file providers stall
    // for minutes when asked to seek inside a multi-gigabyte video.
    const metadata = `${file.name}\u0000${file.size}\u0000${file.lastModified || 0}`;
    function fnv32(initial) {
      let hash = initial;
      for (let i = 0; i < metadata.length; i++) {
        hash = Math.imul(hash ^ metadata.charCodeAt(i), 16777619);
      }
      return (hash >>> 0).toString(16).padStart(8, "0");
    }
    return fnv32(2166136261) + fnv32(2166136261 ^ 0x9e3779b9);
  }

  async function jsonRequest(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(url === "/api/pair" ? {} : { "X-LocalDrop-Token": token }),
      },
      cache: "no-store",
    });
    let data;
    try { data = await response.json(); } catch { data = {}; }
    if (!response.ok) {
      if (response.status === 401) {
        sessionStorage.removeItem("localdrop_token");
        token = "";
        $("main-panel").hidden = true;
        $("pair-panel").hidden = false;
      }
      throw new Error(data.error || "The connection to the computer failed");
    }
    return data;
  }

  async function loadInfo() {
    const info = await jsonRequest("/api/info");
    $("pair-panel").hidden = true;
    $("main-panel").hidden = false;
    $("save-folder").textContent = info.folder;
    $("free-space").textContent = humanSize(info.free) + " free space";
    if (boot.local) {
      $("pc-panel").hidden = false;
      $("lan-url").textContent = `http://${info.ip}:${info.port}`;
      $("pc-pin").textContent = info.pin || "······";
    } else {
      $("upload-step").textContent = "SEND FROM IPHONE";
    }
  }

  async function connect(pin) {
    const data = await jsonRequest("/api/pair", {
      method: "POST", body: JSON.stringify({ pin }),
    });
    token = data.token;
    sessionStorage.setItem("localdrop_token", token);
    await loadInfo();
  }

  $("pair-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    $("pair-error").hidden = true;
    const button = $("pair-button");
    button.disabled = true;
    try {
      await connect($("pin").value.trim());
    } catch (error) {
      $("pair-error").textContent = error.message;
      $("pair-error").hidden = false;
    } finally { button.disabled = false; }
  });

  $("copy-url").addEventListener("click", async () => {
    const url = $("lan-url").textContent;
    try {
      await navigator.clipboard.writeText(url);
      $("copy-url").textContent = "Copied ✓";
      setTimeout(() => $("copy-url").textContent = "Copy", 1500);
    } catch { window.prompt("Copy the address:", url); }
  });

  function makeRow(file) {
    const row = document.createElement("div");
    row.className = "file-row";
    const top = document.createElement("div");
    top.className = "file-top";
    const icon = document.createElement("div");
    icon.className = "file-icon";
    icon.textContent = "↗";
    const identity = document.createElement("div");
    identity.className = "file-identity";
    const title = document.createElement("strong");
    title.textContent = file.name;
    const sub = document.createElement("small");
    sub.textContent = humanSize(file.size);
    identity.append(title, sub);
    const status = document.createElement("span");
    status.className = "file-status";
    status.textContent = "Waiting";
    const track = document.createElement("div");
    track.className = "progress-track";
    const fill = document.createElement("div");
    fill.className = "progress-fill";
    track.appendChild(fill);
    top.append(icon, identity, status);
    row.append(top, track);
    $("queue").appendChild(row);
    return { row, status, fill };
  }

  function draw(item, value, label, state = "active") {
    const percent = item.file.size ? Math.min(100, value / item.file.size * 100) : 100;
    item.ui.fill.style.width = percent.toFixed(2) + "%";
    item.ui.status.textContent = label;
    item.ui.row.classList.toggle("completed", state === "completed");
    item.ui.row.classList.toggle("failed", state === "failed");
  }

  async function sendChunk(id, offset, bytes) {
    const controller = new AbortController();
    currentController = controller;
    // Do not wait forever if the phone/browser fails to close a PUT request.
    const timeout = setTimeout(() => controller.abort(), chunkTimeLimitMs);
    try {
      const response = await fetch(`/api/upload/${id}?offset=${offset}`, {
        method: "PUT",
        headers: {
          "X-LocalDrop-Token": token,
          "Content-Type": "application/octet-stream",
        },
        body: bytes,
        signal: controller.signal,
        cache: "no-store",
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `Eroare la bloc: ${response.status}`);
      if (!Number.isSafeInteger(data.offset) || data.offset <= offset || data.offset > offset + bytes.byteLength) {
        throw new Error("Invalid confirmation from the computer");
      }
      return data;
    } catch (error) {
      if (error.name === "AbortError") {
        throw new Error(paused ? "Transfer paused" : "Chunk did not receive confirmation within 45 seconds");
      }
      throw error;
    } finally {
      clearTimeout(timeout);
      if (currentController === controller) currentController = null;
    }
  }

  async function waitIfPaused() {
    while (paused) {
      await new Promise((resolve) => { wakeResume = resolve; });
    }
  }

  async function sendFile(item) {
    let retries = 0;
    const start = Date.now();
    let firstBytes = 0;
    draw(item, 0, "Preparing transfer…");
    const fingerprint = fileFingerprint(item.file);
    const identity = {
      client: getClientId(), name: item.file.name,
      size: item.file.size, mtime: item.file.lastModified || 0, fingerprint,
    };
    let state = await jsonRequest("/api/init", {
      method: "POST",
      body: JSON.stringify(identity),
    });
    let offset = state.offset;
    firstBytes = offset;
    if (offset > 0) {
      draw(item, offset, "Resuming…");
      diag(`Resume ${item.file.name.slice(0, 28)}: ${humanSize(offset)} already saved`);
    }
    while (offset < item.file.size) {
      await waitIfPaused();
      const piece = item.file.slice(offset, Math.min(item.file.size, offset + state.chunkSize));
      try {
        draw(item, offset, `Reading from iPhone… ${humanSize(offset)} / ${humanSize(item.file.size)}`);
        // Read the 2 MiB explicitly before fetch. iOS may otherwise defer
        // reading a Photos/File-provider Blob during an active HTTP upload.
        const tRead = performance.now();
        const readTicker = setInterval(() => {
          draw(item, offset, `Reading from iPhone: ${Math.round((performance.now() - tRead)/1000)} s…`);
        }, 1000);
        let bytes;
        try { bytes = await piece.arrayBuffer(); }
        finally { clearInterval(readTicker); }
        const clientReadMs = performance.now() - tRead;
        if (paused) { await waitIfPaused(); }
        draw(item, offset, `Sending chunk · ${humanSize(offset)} / ${humanSize(item.file.size)}`);
        const tSend = performance.now();
        const sendTicker = setInterval(() => {
          draw(item, offset, `Waiting for PC confirmation: ${Math.round((performance.now() - tSend)/1000)} s…`);
        }, 1000);
        let res;
        try { res = await sendChunk(state.id, offset, bytes); }
        finally { clearInterval(sendTicker); }
        const roundtripMs = performance.now() - tSend;
        offset = res.offset;
        item.confirmed = offset;
        retries = 0;
        diag(`${humanSize(offset)}: iPhone ${ms(clientReadMs)}; HTTP+confirmation ${ms(roundtripMs)}; ` +
             `server-read ${ms(res.serverReadMs)}; disk ${ms(res.serverWriteMs)}; fsync ${ms(res.serverSyncMs)}`);
        const elapsed = (Date.now() - start) / 1000;
        const speed = elapsed > 1 ? (offset - firstBytes) / elapsed : 0;
        const pct = offset / item.file.size * 100;
        const label = pct > 0 && pct < 0.1 ? "<0.1%" : `${Math.floor(pct)}%`;
        draw(item, offset, `${label}${speed > 0 ? " · " + humanSize(speed) + "/s" : ""}`);
      } catch (error) {
        diag(`Bloc ${humanSize(offset)}: ${error.message || String(error)}`);
        if (!paused) {
          retries++;
          if (retries > 4) throw error;
          draw(item, offset, `Reconnecting ${retries}/4…`);
          await new Promise((resolve) => setTimeout(resolve, 750 * retries));
        }
        await waitIfPaused();
        // The server may have written part of a chunk before the disconnect.
        state = await jsonRequest("/api/init", {
          method: "POST",
          body: JSON.stringify(identity),
        });
        offset = state.offset;
      }
    }
    draw(item, item.file.size, "Finishing…");
    const result = await jsonRequest(`/api/finish/${state.id}`, { method: "POST" });
    draw(item, item.file.size, "Completed ✓", "completed");
    diag(`Completed ${item.file.name.slice(0, 28)}: ${humanSize(item.file.size)}`);
    item.ui.row.title = `Saved on the computer as ${result.name}`;
  }

  async function runQueue() {
    if (processing) return;
    processing = true;
    $("pause-button").hidden = false;
    for (const item of queue) {
      if (item.state !== "waiting") continue;
      item.state = "sending";
      try {
        await sendFile(item);
        item.state = "done";
      } catch (error) {
        item.state = "failed";
        draw(item, item.confirmed || 0, error.message || "Transfer failed", "failed");
      }
    }
    processing = false;
    paused = false;
    $("pause-button").hidden = true;
    $("pause-button").textContent = "Pause";
    try { await loadInfo(); } catch { /* no network */ }
  }

  $("pause-button").addEventListener("click", () => {
    paused = !paused;
    $("pause-button").textContent = paused ? "Resume" : "Pause";
    if (paused) {
      if (currentController) currentController.abort();
    } else if (wakeResume) {
      const resolve = wakeResume;
      wakeResume = null;
      resolve();
    }
  });

  function addFiles(files) {
    if (!token) {
      $("pair-panel").hidden = false;
      return;
    }
    for (const file of files) {
      const item = { file, state: "waiting", ui: makeRow(file) };
      queue.push(item);
    }
    if (files.length) {
      $("queue-panel").hidden = false;
      runQueue();
    }
  }

  const dropzone = $("dropzone");
  const input = $("file-input");
  dropzone.addEventListener("click", () => input.click());
  dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault(); input.click();
    }
  });
  input.addEventListener("change", () => {
    addFiles(Array.from(input.files || []));
    input.value = "";
  });
  dropzone.addEventListener("dragover", (event) => {
    event.preventDefault(); dropzone.classList.add("dragover");
  });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault(); dropzone.classList.remove("dragover");
    addFiles(Array.from(event.dataTransfer.files || []));
  });

  if (token) {
    loadInfo().catch(() => {
      $("pair-panel").hidden = false;
      $("main-panel").hidden = true;
    });
  } else {
    $("pair-panel").hidden = false;
  }
})();
