(function () {
  function themeColors() {
    var dark = document.documentElement.classList.contains("dark");
    return {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      "margin.l": 88,
      "margin.r": 36,
      "margin.t": 48,
      "margin.b": 72,
      "xaxis.automargin": true,
      "yaxis.automargin": true,
      "font.color": dark ? "#e2e8f0" : "#334155",
      "title.font.color": dark ? "#f8fafc" : "#0f172a",
      "xaxis.gridcolor": dark ? "#1e293b" : "#e2e8f0",
      "yaxis.gridcolor": dark ? "#1e293b" : "#e2e8f0",
      "xaxis.linecolor": dark ? "#334155" : "#cbd5e1",
      "yaxis.linecolor": dark ? "#334155" : "#cbd5e1",
      "legend.font.color": dark ? "#e2e8f0" : "#334155",
      "hoverlabel.bgcolor": dark ? "#0f172a" : "#ffffff",
      "hoverlabel.bordercolor": dark ? "#cbd5e1" : "#0f172a",
      "hoverlabel.font.color": dark ? "#f8fafc" : "#0f172a",
      "hoverlabel.font.size": 13,
    };
  }

  function styleHover(node) {
    var dark = document.documentElement.classList.contains("dark");
    var bg = dark ? "#0f172a" : "#ffffff";
    var fg = dark ? "#f8fafc" : "#0f172a";
    var border = dark ? "#cbd5e1" : "#0f172a";
    Plotly.restyle(node, {
      hoverinfo: "none",
      hovertemplate: "",
      "hoverlabel.bgcolor": bg,
      "hoverlabel.bordercolor": border,
      "hoverlabel.font.color": fg,
      "hoverlabel.font.size": 13,
    });
  }

  function returnPoint(point, node) {
    if (node && node.dataset.tipkind === "return") return true;
    var layoutMeta = node && node.layout && node.layout.meta;
    if (layoutMeta && layoutMeta.tip === "return") return true;
    var meta = (point.fullData && point.fullData.meta) || (point.data && point.data.meta);
    return meta === "return" || (meta && meta.tip === "return");
  }

  function closePrice(point) {
    var index = point.pointNumber;
    var stored = [];
    stored.push(point.customdata, point.text);
    if (point.data) {
      if (point.data.customdata) stored.push(point.data.customdata[index]);
      if (point.data.text) stored.push(point.data.text[index]);
    }
    if (point.fullData) {
      if (point.fullData.customdata) stored.push(point.fullData.customdata[index]);
      if (point.fullData.text) stored.push(point.fullData.text[index]);
    }
    for (var i = 0; i < stored.length; i++) {
      var raw = stored[i];
      if (Array.isArray(raw)) raw = raw[0];
      var price = Number(raw);
      if (isFinite(price)) return price;
    }
    return NaN;
  }

  function shillings(price) {
    return "KSh " + price.toLocaleString("en-KE", {
      minimumFractionDigits: Math.abs(price) < 1 ? 3 : 2,
      maximumFractionDigits: Math.abs(price) < 1 ? 3 : 2,
    });
  }

  var tip = document.createElement("div");
  tip.setAttribute("id", "chart-tip");
  tip.style.display = "none";
  tip.style.position = "fixed";
  tip.style.zIndex = "60";
  tip.style.maxHeight = "calc(100vh - 16px)";
  tip.style.overflowY = "auto";
  tip.style.pointerEvents = "none";
  tip.style.borderRadius = "16px";
  tip.style.borderWidth = "1px";
  tip.style.borderStyle = "solid";
  tip.style.padding = "10px 12px";
  tip.style.fontSize = "13px";
  tip.style.lineHeight = "1.35";
  tip.style.boxShadow = "0 12px 32px rgba(15,23,42,.28)";
  document.body.appendChild(tip);

  function hideTip() {
    tip.style.display = "none";
    tip.replaceChildren();
  }

  function customRow(point) {
    var index = point.pointNumber;
    var stored = [point.customdata];
    if (point.data && point.data.customdata) stored.push(point.data.customdata[index]);
    if (point.fullData && point.fullData.customdata) stored.push(point.fullData.customdata[index]);
    for (var i = 0; i < stored.length; i++) {
      if (Array.isArray(stored[i]) && stored[i].length > 1) return stored[i];
    }
    return [];
  }

  function tipLine(label, value) {
    var row = document.createElement("div");
    row.style.display = "flex";
    row.style.justifyContent = "space-between";
    row.style.gap = "16px";
    var name = document.createElement("span");
    name.textContent = label;
    var amount = document.createElement("span");
    amount.textContent = value;
    row.appendChild(name);
    row.appendChild(amount);
    return row;
  }

  function placeTip(data) {
    var mouse = data.event || {};
    var left = (mouse.clientX || 0) + 16;
    var top = (mouse.clientY || 0) + 16;
    tip.style.left = left + "px";
    tip.style.top = top + "px";
    var box = tip.getBoundingClientRect();
    if (left + box.width > window.innerWidth - 8) left = Math.max(8, (mouse.clientX || 0) - box.width - 16);
    if (top + box.height > window.innerHeight - 8) top = Math.max(8, window.innerHeight - box.height - 8);
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  }

  function showRankTip(point) {
    var row = customRow(point);
    var company = row[0] || String(point.y || "");
    var gain = Number(row[1]);
    var pct = Number(point.x);
    var heading = document.createElement("div");
    heading.style.fontWeight = "650";
    heading.style.marginBottom = "6px";
    heading.textContent = company + (point.y ? " · " + point.y : "");
    tip.appendChild(heading);
    if (isFinite(pct)) {
      var sign = pct > 0 ? "+" : "";
      tip.appendChild(tipLine("Return", sign + pct.toLocaleString("en-KE", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }) + "%"));
    }
    if (isFinite(gain)) tip.appendChild(tipLine("Profit / loss", shillings(gain)));
    if (row[2] && row[3]) tip.appendChild(tipLine("Dates", row[2] + " → " + row[3]));
  }

  function showTip(data, node) {
    var points = (data && data.points) || [];
    if (!points.length) return;
    var dark = document.documentElement.classList.contains("dark");
    tip.style.display = "block";
    tip.style.background = dark ? "#0f172a" : "#ffffff";
    tip.style.color = dark ? "#f8fafc" : "#0f172a";
    tip.style.borderColor = dark ? "#cbd5e1" : "#0f172a";
    tip.replaceChildren();
    if (node && node.dataset.tipkind === "rank") {
      showRankTip(points[0]);
      placeTip(data);
      return;
    }
    var when = document.createElement("div");
    when.style.fontWeight = "650";
    when.style.marginBottom = "6px";
    var rawDate = points[0].x;
    var parsed = new Date(rawDate);
    when.textContent = isNaN(parsed.getTime())
      ? String(rawDate)
      : parsed.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
    tip.appendChild(when);
    points.forEach(function (point) {
      var row = document.createElement("div");
      row.style.display = "flex";
      row.style.justifyContent = "space-between";
      row.style.gap = "16px";
      var name = document.createElement("span");
      name.textContent = point.data.name || "Price";
      var value = document.createElement("span");
      var number = Number(point.y);
      var price = closePrice(point);
      if (returnPoint(point, node) && isFinite(price)) {
        var change = "";
        if (isFinite(number)) {
          var sign = number > 0 ? "+" : "";
          change = "  ·  " + sign + number.toLocaleString("en-KE", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
          }) + "%";
        }
        value.textContent = shillings(price) + change;
      } else {
        value.textContent = isFinite(number)
          ? number.toLocaleString("en-KE", { maximumFractionDigits: 2 })
          : String(point.y);
      }
      row.appendChild(name);
      row.appendChild(value);
      tip.appendChild(row);
    });
    placeTip(data);
  }

  function bindTip(node) {
    if (node.dataset.tip === "1" || !node.on) return;
    node.dataset.tip = "1";
    node.on("plotly_hover", function (data) { showTip(data, node); });
    node.addEventListener("mouseleave", hideTip);
  }

  function drawCharts() {
    if (!window.Plotly) return;
    document.querySelectorAll("[data-chart]").forEach(function (node) {
      var source = document.getElementById(node.getAttribute("data-chart"));
      if (!source || node.dataset.ready === "1") return;
      var figure = JSON.parse(source.textContent);
      if (figure.layout && figure.layout.meta && figure.layout.meta.tip) {
        node.dataset.tipkind = figure.layout.meta.tip;
      }
      Plotly.newPlot(node, figure.data, figure.layout, {responsive: true, displayModeBar: false});
      node.dataset.ready = "1";
    });
    document.querySelectorAll("[data-chart]").forEach(function (node) {
      if (node.dataset.ready === "1") {
        Plotly.relayout(node, themeColors());
        styleHover(node);
        bindTip(node);
      }
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
