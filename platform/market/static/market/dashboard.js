(function () {
  function themeColors() {
    var dark = document.documentElement.classList.contains("dark");
    return {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      "font.color": dark ? "#e2e8f0" : "#334155",
      "title.font.color": dark ? "#f8fafc" : "#0f172a",
      "xaxis.gridcolor": dark ? "#1e293b" : "#e2e8f0",
      "yaxis.gridcolor": dark ? "#1e293b" : "#e2e8f0",
      "xaxis.linecolor": dark ? "#334155" : "#cbd5e1",
      "yaxis.linecolor": dark ? "#334155" : "#cbd5e1",
      "legend.font.color": dark ? "#e2e8f0" : "#334155",
    };
  }

  function drawCharts() {
    if (!window.Plotly) return;
    document.querySelectorAll("[data-chart]").forEach(function (node) {
      var source = document.getElementById(node.getAttribute("data-chart"));
      if (!source || node.dataset.ready === "1") return;
      var figure = JSON.parse(source.textContent);
      Plotly.newPlot(node, figure.data, figure.layout, {responsive: true, displayModeBar: false});
      node.dataset.ready = "1";
    });
    document.querySelectorAll("[data-chart]").forEach(function (node) {
      if (node.dataset.ready === "1") Plotly.relayout(node, themeColors());
    });
  }

  var toggle = document.getElementById("theme-toggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      document.documentElement.classList.toggle("dark");
      localStorage.setItem("nse-theme", document.documentElement.classList.contains("dark") ? "dark" : "light");
      drawCharts();
    });
  }

  var opener = document.getElementById("chat-open");
  var panel = document.getElementById("chat-panel");
  var closer = document.getElementById("chat-close");
  var log = document.getElementById("chat-log");
  var form = document.getElementById("chat-form");
  var input = document.getElementById("chat-input");
  var clear = document.getElementById("chat-clear");

  function scrollLog() {
    if (log) log.scrollTop = log.scrollHeight;
  }

  function bubble(text, role) {
    var empty = document.getElementById("chat-empty");
    if (empty) empty.remove();
    var node = document.createElement("article");
    node.className = "rise max-w-[90%] rounded-2xl px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap " + (
      role === "user"
        ? "ml-auto bg-slate-900 text-white dark:bg-teal-500 dark:text-slate-950"
        : "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-100"
    );
    node.textContent = text;
    log.appendChild(node);
    scrollLog();
    return node;
  }

  function csrf() {
    var match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  if (opener && panel) {
    opener.addEventListener("click", function () {
      panel.classList.add("is-open");
      opener.classList.add("hidden");
      scrollLog();
      if (input) input.focus();
    });
    closer.addEventListener("click", function () {
      panel.classList.remove("is-open");
      opener.classList.remove("hidden");
    });
  }

  if (clear) {
    clear.addEventListener("click", function () {
      log.innerHTML = "";
      var note = document.createElement("p");
      note.id = "chat-empty";
      note.className = "text-sm text-slate-500 dark:text-slate-400";
      note.textContent = "Ask about a stock, the banks, or the whole market.";
      log.appendChild(note);
      fetch("/chat/", {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-CSRFToken": csrf()},
        body: JSON.stringify({clear: true})
      });
    });
  }

  if (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var question = (input.value || "").trim();
      if (!question) return;
      input.value = "";
      bubble(question, "user");
      var pending = document.createElement("article");
      pending.className = "rise typing inline-flex items-center gap-1 rounded-2xl bg-slate-100 px-3 py-3 dark:bg-slate-800";
      pending.innerHTML = '<span class="inline-block h-1.5 w-1.5 rounded-full bg-teal-700 dark:bg-teal-300"></span><span class="inline-block h-1.5 w-1.5 rounded-full bg-teal-700 dark:bg-teal-300"></span><span class="inline-block h-1.5 w-1.5 rounded-full bg-teal-700 dark:bg-teal-300"></span>';
      log.appendChild(pending);
      scrollLog();
      var send = document.getElementById("chat-send");
      send.disabled = true;
      fetch("/chat/", {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-CSRFToken": csrf()},
        body: JSON.stringify({message: question, focus: panel.getAttribute("data-focus") || ""})
      }).then(function (response) {
        return response.json().then(function (body) {
          pending.remove();
          if (!response.ok) bubble(body.error || "The chat could not answer.", "assistant");
          else bubble(body.answer || "", "assistant");
        });
      }).catch(function () {
        pending.remove();
        bubble("The chat could not answer.", "assistant");
      }).finally(function () {
        send.disabled = false;
      });
    });
  }

  drawCharts();
  scrollLog();
})();
