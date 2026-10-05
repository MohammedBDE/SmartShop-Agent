(function () {
  "use strict";

  const API_BASE = window.location.origin.startsWith("http")
    ? window.location.origin
    : "http://localhost:5000";

  const SESSION_KEY = "smart_shop_session_id";

  const streamEl = document.getElementById("stream");
  const openingEl = document.getElementById("opening");
  const formEl = document.getElementById("composer");
  const inputEl = document.getElementById("input");
  const sendEl = document.getElementById("send");
  const alertEl = document.getElementById("alert");
  const alertTextEl = document.getElementById("alert-text");
  const sessionLabelEl = document.getElementById("session-label");
  const statusPillEl = document.getElementById("status-pill");
  const statusTextEl = document.getElementById("status-text");
  const newSessionEl = document.getElementById("new-session");

  let sessionId = localStorage.getItem(SESSION_KEY) || null;
  let pending = false;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function setSession(id) {
    sessionId = id;
    if (id) {
      localStorage.setItem(SESSION_KEY, id);
      sessionLabelEl.textContent = "session " + id.slice(0, 8);
    } else {
      localStorage.removeItem(SESSION_KEY);
      sessionLabelEl.textContent = "no session yet";
    }
  }

  function showAlert(message) {
    alertTextEl.textContent = message;
    alertEl.hidden = false;
  }

  function clearAlert() {
    alertEl.hidden = true;
    alertTextEl.textContent = "";
  }

  function closeOpening() {
    if (openingEl && openingEl.parentNode) openingEl.parentNode.removeChild(openingEl);
  }

  function scrollToBottom() {
    streamEl.scrollTop = streamEl.scrollHeight;
  }

  /* ---------- the trace rail: Query -> Router -> path -> LLM ---------- */

  function buildTrace(route, router, toolName) {
    const trace = el("div", "trace");
    const steps = [];

    steps.push({ label: "Query", live: true });

    steps.push({
      label: "Router",
      live: true,
      title:
        (router && router.reasoning ? router.reasoning : "No reasoning recorded") +
        (router && router.classifier ? "\n\nClassifier: " + router.classifier : ""),
    });

    if (route === "rag") {
      steps.push({ label: "RAG", live: true, kind: "rag" });
      steps.push({ label: "Tools", live: false });
    } else if (route === "tool") {
      steps.push({ label: "RAG", live: false });
      steps.push({ label: toolName || "Tool", live: true, kind: "tool" });
    } else {
      steps.push({ label: "RAG", live: false });
      steps.push({ label: "Tools", live: false });
    }

    steps.push({
      label: "LLM",
      live: true,
      kind: route === "direct" ? "direct" : undefined,
    });

    steps.forEach(function (step, index) {
      if (index > 0) {
        const link = el("span", "link");
        link.style.animationDelay = index * 55 - 25 + "ms";
        trace.appendChild(link);
      }

      let className = "node " + (step.live ? "node-live" : "node-skip");
      if (step.kind) className += " node-" + step.kind;

      const node = el("span", className, step.label);
      if (step.title) node.title = step.title;
      node.style.animationDelay = index * 55 + "ms";
      trace.appendChild(node);
    });

    return trace;
  }

  function buildSources(sources) {
    const box = el("div", "sources");
    box.appendChild(el("div", "sources-head", "Retrieved from " + sources.length + " source" + (sources.length === 1 ? "" : "s")));

    const seen = {};
    sources.forEach(function (source) {
      seen[source.title] = (seen[source.title] || 0) + 1;
    });

    const counted = {};
    sources.forEach(function (source) {
      const row = el("div", "source");
      counted[source.title] = (counted[source.title] || 0) + 1;
      const label =
        seen[source.title] > 1
          ? source.title + " · part " + counted[source.title]
          : source.title;
      row.appendChild(el("span", "source-title", label));

      const meter = el("div", "meter");
      const fill = el("div", "meter-fill");
      const score = Math.max(0, Math.min(1, Number(source.similarity) || 0));
      fill.style.width = (score * 100).toFixed(0) + "%";
      meter.appendChild(fill);
      row.appendChild(meter);

      row.appendChild(el("span", "source-score", score.toFixed(2)));

      if (source.excerpt) row.title = source.excerpt;
      box.appendChild(row);
    });

    return box;
  }

  function buildInspector(tool) {
    const details = el("details", "inspect");
    const summary = el("summary");
    summary.appendChild(document.createTextNode("Tool call · " + (tool.name || "unknown")));
    details.appendChild(summary);

    const pre = el("pre");
    pre.textContent =
      "input   " + JSON.stringify(tool.input, null, 2) +
      "\n\noutput  " + JSON.stringify(tool.output, null, 2);
    details.appendChild(pre);

    return details;
  }

  function addUserTurn(text) {
    closeOpening();
    const turn = el("div", "turn turn-user");
    turn.appendChild(el("div", "bubble-user", text));
    streamEl.appendChild(turn);
    scrollToBottom();
  }

  function addAnswerTurn(data) {
    closeOpening();
    const turn = el("div", "turn");
    const card = el("article", "answer");

    card.appendChild(buildTrace(data.route, data.router, data.tool && data.tool.name));
    card.appendChild(el("div", "answer-body", data.answer));

    if (data.sources && data.sources.length) card.appendChild(buildSources(data.sources));
    if (data.tool && data.tool.name && data.tool.output) card.appendChild(buildInspector(data.tool));

    if (data.degraded) {
      const flag = el("div", "flag", "Limited mode" + (data.notes && data.notes.length ? " · " + data.notes.join(" · ") : ""));
      card.appendChild(flag);
    }

    turn.appendChild(card);
    streamEl.appendChild(turn);
    scrollToBottom();
  }

  function addPlainAnswer(text) {
    closeOpening();
    const turn = el("div", "turn");
    const card = el("article", "answer");
    card.appendChild(el("div", "answer-body", text));
    turn.appendChild(card);
    streamEl.appendChild(turn);
    scrollToBottom();
  }

  function addThinking() {
    closeOpening();
    const turn = el("div", "turn");
    const box = el("div", "thinking");
    const beads = el("span", "beads");
    beads.innerHTML = "<i></i><i></i><i></i>";
    box.appendChild(beads);
    box.appendChild(el("span", null, "Routing your question"));
    turn.appendChild(box);
    streamEl.appendChild(turn);
    scrollToBottom();
    return turn;
  }

  function setPending(value) {
    pending = value;
    inputEl.disabled = value;
    sendEl.disabled = value;
  }

  function autoGrow() {
    inputEl.style.height = "auto";
    inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + "px";
  }

  async function sendMessage(text) {
    clearAlert();
    addUserTurn(text);
    const thinking = addThinking();
    setPending(true);

    try {
      const response = await fetch(API_BASE + "/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });

      const data = await response.json().catch(function () { return null; });
      thinking.remove();

      if (!response.ok || !data || data.ok === false) {
        const message =
          (data && data.error && data.error.message) ||
          "The server responded with status " + response.status + ".";
        showAlert(message);
        addPlainAnswer("I could not process that question. " + message);
        return;
      }

      if (data.session_id) setSession(data.session_id);
      addAnswerTurn(data);
    } catch (error) {
      thinking.remove();
      showAlert("Cannot reach the server. Make sure it is running, then try again.");
      addPlainAnswer("No connection to the server right now.");
    } finally {
      setPending(false);
      inputEl.focus();
    }
  }

  async function loadHistory() {
    if (!sessionId) return;

    try {
      const response = await fetch(API_BASE + "/history?session_id=" + encodeURIComponent(sessionId));
      if (!response.ok) return;

      const data = await response.json();
      if (!data.ok || !data.messages || !data.messages.length) return;

      data.messages.forEach(function (message) {
        if (message.role === "user") {
          addUserTurn(message.content);
          return;
        }

        let sources = message.sources;
        if (typeof sources === "string") {
          try { sources = JSON.parse(sources); } catch (error) { sources = []; }
        }

        addAnswerTurn({
          answer: message.content,
          route: message.route,
          router: { reasoning: message.router_reasoning },
          sources: sources || [],
          tool: message.tool_name ? { name: message.tool_name } : null,
          degraded: false,
          notes: [],
        });
      });
    } catch (error) {
      showAlert("Could not load the earlier conversation.");
    }
  }

  async function checkHealth() {
    try {
      const response = await fetch(API_BASE + "/health");
      const data = await response.json();

      if (data.ok) {
        statusPillEl.className = "status status-ok";
        statusTextEl.textContent = "Server and database ready";
      } else {
        statusPillEl.className = "status status-warn";
        const missing = (data.missing_secrets || []).join(", ");
        const dbDown = data.database && data.database.database !== "up";
        statusTextEl.textContent = dbDown
          ? "Database unreachable"
          : missing
          ? "Missing " + missing
          : "Limited mode";
      }
      statusPillEl.title = JSON.stringify(data, null, 2);
    } catch (error) {
      statusPillEl.className = "status status-down";
      statusTextEl.textContent = "Server offline";
      statusPillEl.title = "";
    }
  }

  formEl.addEventListener("submit", function (event) {
    event.preventDefault();
    if (pending) return;

    const text = inputEl.value.trim();
    if (!text) return;

    inputEl.value = "";
    autoGrow();
    sendMessage(text);
  });

  inputEl.addEventListener("input", autoGrow);

  inputEl.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (formEl.requestSubmit) formEl.requestSubmit();
      else formEl.dispatchEvent(new Event("submit", { cancelable: true }));
    }
  });

  document.addEventListener("click", function (event) {
    const starter = event.target.closest(".starter");
    if (!starter || pending) return;
    sendMessage(starter.getAttribute("data-q"));
  });

  newSessionEl.addEventListener("click", function () {
    setSession(null);
    streamEl.innerHTML = "";
    if (openingEl) streamEl.appendChild(openingEl);
    clearAlert();
    inputEl.focus();
  });

  setSession(sessionId);
  checkHealth();
  loadHistory();
})();
