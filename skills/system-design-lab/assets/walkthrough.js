// walkthrough.html script. Inline at the end of <body>, then add page hooks below it.
// Markup it drives (see references/walkthrough.md):
//   <button id="toggle-code">                        expand / collapse every code accordion
//   <select id="api-user" data-header="X-User-Id">      who is calling (optional)
//   <input data-var="file_id">                          fills {file_id} in paths; a 2xx answer with "file_id" refills it
//   <span id="api-conn">                                gateway status
//   <details class="api" id="api-x" data-method="POST" data-path="/files/{file_id}/share">
//     <textarea> JSON body   <input data-query="since">   <button data-send>   <pre class="out" hidden>
//   Steps that bypass the gateway: <details class="api"> without data-path, own button id + handler
//   <details class="api" id="api-peek" open data-peek="/lab/peek">  #refresh-peek  #peek-status  <pre>
//   [data-reset] → #reset-confirm (#reset-yes / #reset-no) → POST /lab/reset → #reset-out
// Page hooks:
//   HOOKS.after["api-x"] = (r, body) => …   feed this answer into the next step
//   HOOKS.peek = (data) => …                render the peek (default: JSON into the first <pre>)
//   HOOKS.reset = () => …                   forget page state, refill sample inputs

// The gateway sends CORS *, so this also works from file:// and editor previews.
const GATEWAY = "http://localhost:8090";
const $ = (id) => document.getElementById(id);
const HOOKS = { after: {}, peek: null, reset: () => {} };

$("toggle-code")?.addEventListener("click", (e) => {
  const open = e.target.dataset.open !== "1";
  document.querySelectorAll("details.code").forEach((d) => (d.open = open));
  e.target.dataset.open = open ? "1" : "0";
  e.target.textContent = open ? "Collapse all code" : "Expand all code";
});

const who = () => $("api-user")?.value;
const vars = () => Object.fromEntries([...document.querySelectorAll("[data-var]")].map((i) => [i.dataset.var, i]));

// One HTTP call. HTTP errors (403, 404, …) are answers, not exceptions.
async function call(method, path, body) {
  const started = performance.now();
  const headers = {};
  if ($("api-user")) headers[$("api-user").dataset.header || "X-User-Id"] = who();
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(GATEWAY + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  const text = await res.text();
  let data = null;
  try {
    if (text) data = JSON.parse(text);
  } catch {
    if (res.status >= 502) throw new Error(`${res.status} from the gateway: the service behind it is down or restarting (docker compose logs).`);
    throw new Error(`${GATEWAY} answered with HTML, not JSON. Another app is probably using the port. Run \`docker compose up\` in this lab's folder.`);
  }
  return { status: res.status, statusText: res.statusText, ok: res.ok, data, ms: Math.round(performance.now() - started) };
}

function show(out, lines) {
  out.hidden = false;
  out.textContent = lines.join("\n");
}

const outOf = (api) => api.querySelector("pre.out");

// The generic Send button: method + path from <details data-method data-path>.
async function send(api) {
  const method = api.dataset.method;
  let path = api.dataset.path.replace(/\{(\w+)\}/g, (_, k) => encodeURIComponent(vars()[k]?.value.trim() ?? ""));
  const params = new URLSearchParams();
  api.querySelectorAll("[data-query]").forEach((i) => params.set(i.dataset.query, i.value.trim()));
  if ([...params].length) path += "?" + params;

  const out = outOf(api);
  const textarea = api.querySelector("textarea");
  let body;
  if (textarea) {
    try {
      body = JSON.parse(textarea.value);
    } catch (err) {
      return show(out, [`The body is not valid JSON: ${err.message}`]);
    }
  }

  const request = `→ ${method} ${path}` + (who() ? `   ${$("api-user").dataset.header || "X-User-Id"}: ${who()}` : "") + (body ? `\n  ${JSON.stringify(body)}` : "");
  show(out, [request, "…"]);
  try {
    const r = await call(method, path, body);
    show(out, [request, `← ${r.status} ${r.statusText} · ${r.ms} ms`, "", JSON.stringify(r.data, null, 2)]);
    if (r.ok && r.data && !Array.isArray(r.data)) {
      for (const [k, input] of Object.entries(vars())) if (typeof r.data[k] === "string") input.value = r.data[k];
    }
    HOOKS.after[api.id]?.(r, body);
  } catch (err) {
    show(out, [request, `✕ ${err.message}`]);
  }
  peek();
}

document.querySelectorAll("details.api[data-path] [data-send]").forEach((btn) => btn.addEventListener("click", () => send(btn.closest("details.api"))));

// Peek: one GET, every 5 s while its accordion is open, and after every Send.
async function peek() {
  const box = document.querySelector("[data-peek]");
  if (!box) return;
  const conn = $("api-conn");
  try {
    const r = await call("GET", box.dataset.peek);
    if (HOOKS.peek) HOOKS.peek(r.data);
    else box.querySelector("pre").textContent = JSON.stringify(r.data, null, 2);
    $("peek-status").textContent = "Updated " + new Date().toLocaleTimeString();
    conn.textContent = "● Connected to " + GATEWAY.replace("http://", "");
    conn.className = "ok";
  } catch (err) {
    const msg = err instanceof TypeError ? `Can't reach ${GATEWAY}. Is docker compose up?` : err.message;
    $("peek-status").textContent = msg;
    conn.textContent = "● " + msg;
    conn.className = "bad";
  }
}
$("refresh-peek")?.addEventListener("click", peek);
setInterval(() => document.querySelector("[data-peek]")?.open && !document.hidden && peek(), 5000);
setTimeout(peek); // after the page script has set its HOOKS

// Reset: confirm on the page (no confirm()), POST, then let the page forget its state.
function askReset() {
  $("reset-confirm").hidden = false;
  $("reset-confirm").scrollIntoView({ block: "nearest" });
}
document.querySelectorAll("[data-reset]").forEach((b) => b.addEventListener("click", askReset));
$("reset-no")?.addEventListener("click", () => ($("reset-confirm").hidden = true));
$("reset-yes")?.addEventListener("click", async () => {
  $("reset-confirm").hidden = true;
  const out = $("reset-out");
  show(out, ["→ POST /lab/reset", "…"]);
  try {
    const r = await call("POST", "/lab/reset");
    show(out, ["→ POST /lab/reset", `← ${r.status} ${r.statusText}`, "", JSON.stringify(r.data, null, 2)]);
    if (!r.ok) return;
  } catch (err) {
    return show(out, ["→ POST /lab/reset", `✕ ${err.message}`]);
  }
  document.querySelectorAll("[data-var]").forEach((i) => (i.value = i.defaultValue));
  document.querySelectorAll("details.api [data-query], details.api textarea").forEach((i) => (i.value = i.defaultValue));
  document.querySelectorAll("details.api pre.out").forEach((p) => (p.hidden = true));
  HOOKS.reset();
  peek();
});
