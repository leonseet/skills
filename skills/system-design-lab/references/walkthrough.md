# walkthrough.html

One static page at `/walkthrough.html`. Inline `assets/walkthrough.css` in `<style>`. Inline `assets/walkthrough.js` at the end of `<body>`, then the page hooks. Links to the Lab UI use `http://localhost:8090/…` so they also work from `file://`.

## Sections, in order

1. **How to use**: keep this tab open, do each lab in the UI, open the viewer, expand the code. Add a `#toggle-code` "Expand all code" button.
2. **TOC**
3. **`#architecture`**: one SVG. Every box links to its lab. The legend lists only the box and edge kinds the design has.
4. **`#peek` Live peek + API explorer** (below)
5. **`#map` What each box is for**: SVG lanes, one per path the user takes (upload, download, sync…). Each lane has a title and a one-line why, using the architecture's boxes and colors. Never ASCII.
6. **`#viewers`**: a card per viewer (Built-in / Companion / CLI) with URL and credentials.
7. **`#lab0` … `#labN`**: Lab 0 is a tour of the seed data in each store.
8. **CLI cheat sheet**: `docker compose exec …` fallbacks, `curl -X POST :8090/lab/reset`, `down -v`.

## Lab section

```html
<section id="labN">
  <h2>Lab N — concept</h2>
  <p class="lesson">Why this hop exists (the lesson note).</p>
  <figure class="lab-arch">
    <p class="eyebrow">This lab · <a href="#architecture">full architecture</a></p>
    <svg><!-- this hop only; active box highlighted, context faded --></svg>
  </figure>
  <!-- code:labN --><!-- /code:labN -->
  <p><strong>Do this</strong></p>
  <ol><li>UI action (real link)</li><li>Viewer action</li><li>What you should see (row, key, log line)</li></ol>
  <p><strong>If the viewer is down</strong></p>
  <pre>docker compose exec …</pre>
</section>
```

## Code accordions

Copy `assets/code_links.py` to `<lab>/tools/`. Add one `SNIPPETS` entry per code pointer, then run it:

- One entry is the function doing the lab's step, 10–40 lines, with 2–5 notes on the lines that carry the lesson. A note says *why* in plain words.
- Anchors are text on a line, never line numbers. Every other Cursor link is `<a class="file" data-code="path::text">`, and the script fills in its `href`.
- Re-run the script after every source edit.

## Live peek + API explorer

Every API route gets an accordion the user can call. Group them by flow step, and put the peek first and open. `assets/walkthrough.js` documents the markup contract. One accordion:

```html
<details class="api" id="api-share" data-method="POST" data-path="/files/{file_id}/share">
  <summary><span class="verb post">POST</span><span class="sym"><code>/files/{file_id}/share</code></span><span class="gist">one-line job</span></summary>
  <div class="code-body">
    <p class="lead">Its place in the flow. <a class="file" data-code="services/file_service/main.py::async def share">share ↗</a></p>
    <textarea spellcheck="false" class="short">{ "user_ids": ["carol"] }</textarea>
    <div class="row"><button class="btn primary sm" data-send type="button">Send</button></div>
    <p class="tip">Try: one experiment that shows the lesson or an error (switch user → 403).</p>
    <pre class="out" hidden></pre>
  </div>
</details>
```

The top bar (`.api-bar`) holds three things:

- **Act as** `<select id="api-user" data-header="X-User-Id">`
- a `<input data-var="…">` per path variable, defaulting to a seeded id
- `#api-conn`, plus a `data-reset` button

Under the bar go `#reset-confirm` (it says what reset keeps and deletes) and `#reset-out`. Verb classes are `get`, `post`, `put`, `patch`, `delete` and `ws`.

- Steps that bypass the gateway get their own accordion and button, e.g. PUT to a presigned URL, GET from the CDN, a WebSocket.
- Chain the flow with `HOOKS.after`, so each answer fills the next step's body.
- Generate client-side inputs (hashes, sample files) on page load and again in `HOOKS.reset`, so Send works with no prep.
- When a step can't run, say exactly why, e.g. "no POST yet", "deduped" or "this page lacks the bytes". Never a generic "nothing to do".
