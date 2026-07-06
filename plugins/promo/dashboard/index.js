/* МАЯК plugin — точка входа для Hermes dashboard */
/* global window, document */

(function () {
  if (typeof window === "undefined" || !window.__HERMES_PLUGINS__) {
    console.warn("[promo] window.__HERMES_PLUGINS__ недоступен, плагин не загрузится");
    return;
  }

  const SDK = window.__HERMES_PLUGIN_SDK__ || {};
  const h = SDK.h || ((tag, props, ...children) => {
    const el = document.createElement(tag);
    if (props) {
      Object.entries(props).forEach(([k, v]) => {
        if (k === "onClick" || k.startsWith("on")) el[k.toLowerCase()] = v;
        else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
        else if (k === "className") el.className = v;
        else if (k !== "key") el.setAttribute(k, v);
      });
    }
    children.flat().forEach((c) => {
      if (c == null || c === false) return;
      if (typeof c === "string" || typeof c === "number") {
        el.appendChild(document.createTextNode(String(c)));
      } else if (c instanceof Node) {
        el.appendChild(c);
      }
    });
    return el;
  });

  // Простое state-management через data-атрибуты
  function useState(initial) {
    const ref = { value: initial, listeners: [] };
    const get = () => ref.value;
    const set = (v) => {
      ref.value = typeof v === "function" ? v(ref.value) : v;
      ref.listeners.forEach((l) => l());
    };
    return [get, set, ref];
  }

  function useEffect(fn, deps) {
    // Минимальная реализация: вызываем fn один раз при mount
    if (typeof deps === "undefined" || deps === null) {
      fn();
      return;
    }
    fn();
  }

  // ─── Source row component ───────────────────────────────────────
  function SourceRow({ source, onDelete }) {
    const platformColors = {
      threads: "#ff6b35",
      youtube: "#ff0000",
      reddit: "#ff4500",
      x: "#1da1f2",
      telegram: "#0088cc",
    };

    return h(
      "div",
      {
        style: {
          display: "flex",
          alignItems: "center",
          padding: "10px 14px",
          borderBottom: "1px solid rgba(255,255,255,0.06)",
          gap: 12,
        },
      },
      h(
        "span",
        {
          style: {
            display: "inline-block",
            minWidth: 80,
            padding: "2px 8px",
            borderRadius: 4,
            fontSize: 11,
            fontWeight: 600,
            background: platformColors[source.platform] || "#888",
            color: "#fff",
            textTransform: "uppercase",
          },
        },
        source.platform
      ),
      h(
        "span",
        { style: { flex: 1, fontFamily: "ui-monospace, monospace" } },
        source.handle
      ),
      source.label &&
        h(
          "span",
          { style: { color: "#888", fontSize: 12, fontStyle: "italic" } },
          `«${source.label}»`
        ),
      h(
        "button",
        {
          onClick: () => onDelete(source.id),
          style: {
            padding: "4px 10px",
            borderRadius: 4,
            border: "1px solid rgba(255, 80, 80, 0.4)",
            background: "transparent",
            color: "#ff6464",
            cursor: "pointer",
            fontSize: 12,
          },
        },
        "Удалить"
      )
    );
  }

  // ─── Add source form ───────────────────────────────────────────
  function AddSourceForm({ onAdd }) {
    const [platform, setPlatform] = useState("threads");
    const [handle, setHandle] = useState("");
    const [label, setLabel] = useState("");
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState("");

    const submit = async (e) => {
      if (e && e.preventDefault) e.preventDefault();
      if (!handle().trim()) {
        setErr("Handle не может быть пустым");
        return;
      }
      setBusy(true);
      setErr("");
      try {
        const res = await fetch("/api/plugins/promo/sources", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            platform: platform(),
            handle: handle().trim(),
            label: label().trim() || null,
          }),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.detail || `HTTP ${res.status}`);
        }
        setHandle("");
        setLabel("");
        await onAdd();
      } catch (e) {
        setErr(String(e.message || e));
      } finally {
        setBusy(false);
      }
    };

    return h(
      "form",
      {
        onSubmit: submit,
        style: { display: "flex", gap: 8, padding: "12px 14px", flexWrap: "wrap" },
      },
      h(
        "select",
        {
          value: platform(),
          onChange: (e) => setPlatform(e.target.value),
          style: {
            padding: "6px 10px",
            borderRadius: 4,
            background: "var(--card-bg, #1a1a2e)",
            color: "inherit",
            border: "1px solid rgba(255,255,255,0.15)",
          },
        },
        h("option", { value: "threads" }, "Threads"),
        h("option", { value: "youtube" }, "YouTube"),
        h("option", { value: "reddit" }, "Reddit"),
        h("option", { value: "x" }, "X / Twitter"),
        h("option", { value: "telegram" }, "Telegram")
      ),
      h("input", {
        type: "text",
        value: handle(),
        placeholder: "@username / channel URL / r/Subreddit",
        onChange: (e) => setHandle(e.target.value),
        style: {
          flex: 1,
          minWidth: 220,
          padding: "6px 10px",
          borderRadius: 4,
          background: "var(--card-bg, #1a1a2e)",
          color: "inherit",
          border: "1px solid rgba(255,255,255,0.15)",
        },
      }),
      h("input", {
        type: "text",
        value: label(),
        placeholder: "Подпись (опционально)",
        onChange: (e) => setLabel(e.target.value),
        style: {
          width: 180,
          padding: "6px 10px",
          borderRadius: 4,
          background: "var(--card-bg, #1a1a2e)",
          color: "inherit",
          border: "1px solid rgba(255,255,255,0.15)",
        },
      }),
      h(
        "button",
        {
          type: "submit",
          onClick: submit,
          style: {
            padding: "6px 14px",
            borderRadius: 4,
            border: "none",
            background: "#ff6b35",
            color: "#fff",
            fontWeight: 600,
            cursor: busy() ? "wait" : "pointer",
          },
        },
        busy() ? "Добавляю…" : "+ Добавить"
      ),
      err() && h("div", { style: { color: "#ff6464", fontSize: 12, width: "100%" } }, `⚠️ ${err()}`)
    );
  }

  // ─── Sources section ────────────────────────────────────────────
  function SourcesSection() {
    const [sources, setSources] = useState([]);
    const [stats, setStats] = useState({ total: 0, by_platform: {} });
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");

    const refresh = async () => {
      setLoading(true);
      try {
        const res = await fetch("/api/plugins/promo/sources");
        const data = await res.json();
        setSources(data.sources || []);
        setStats({ total: data.total, by_platform: data.by_platform || {} });
      } catch (e) {
        setErr(String(e));
      } finally {
        setLoading(false);
      }
    };

    useEffect(refresh, null);

    const remove = async (id) => {
      if (!confirm("Удалить источник?")) return;
      await fetch(`/api/plugins/promo/sources/${id}`, { method: "DELETE" });
      await refresh();
    };

    return h(
      "div",
      null,
      h(
        "div",
        { style: { padding: "10px 14px", display: "flex", gap: 14, alignItems: "center", borderBottom: "1px solid rgba(255,255,255,0.08)" } },
        h("h3", { style: { margin: 0, fontSize: 16 } }, "🛰 Источники мониторинга"),
        h("span", { style: { color: "#888", fontSize: 12 } }, `всего: ${stats.total()}`),
        Object.entries(stats.by_platform()).map(([p, n]) =>
          h(
            "span",
            {
              key: p,
              style: {
                fontSize: 11,
                padding: "2px 6px",
                background: "rgba(255,255,255,0.06)",
                borderRadius: 3,
              },
            },
            `${p}: ${n}`
          )
        )
      ),
      h(AddSourceForm, { onAdd: refresh }),
      loading()
        ? h("div", { style: { padding: 14, color: "#888" } }, "Загрузка…")
        : err()
        ? h("div", { style: { padding: 14, color: "#ff6464" } }, `Ошибка: ${err()}`)
        : sources().length === 0
        ? h("div", { style: { padding: 14, color: "#888", fontStyle: "italic" } }, "Источников пока нет — добавь первый выше")
        : sources().map((s) => h(SourceRow, { key: s.id, source: s, onDelete: remove }))
    );
  }

  function SessionSection() {
    const [session, setSession] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(async () => {
      try {
        const r = await fetch("/api/plugins/promo/sessions");
        setSession(await r.json());
      } catch (e) {
        setSession({ active: false, reason: String(e) });
      } finally {
        setLoading(false);
      }
    }, null);

    if (loading())
      return h("div", { style: { padding: 14, color: "#888" } }, "Загрузка сессии…");
    if (!session() || !session().active) {
      return h(
        "div",
        { style: { padding: 14 } },
        h("h3", { style: { margin: "0 0 8px 0" } }, "🎙 Текущая сессия интервьюера"),
        h("div", { style: { color: "#888" } }, session()?.reason || "Нет активной сессии — следующий cron-тик стартует новую")
      );
    }

    const s = session();
    return h(
      "div",
      { style: { padding: 14 } },
      h("h3", { style: { margin: "0 0 8px 0" } }, "🎙 Текущая сессия"),
      h("div", null, h("strong", null, "Плоскость:"), " ", s.plane || "—"),
      h("div", null, h("strong", null, "Вопросов задано:"), " ", s.questions_asked),
      h("div", null, h("strong", null, "Стартовала:"), " ", s.started_at || "—"),
      s.stats &&
        h(
          "div",
          { style: { marginTop: 8, padding: 8, background: "rgba(255,255,255,0.04)", borderRadius: 4 } },
          h("div", null, `Всего вопросов: ${s.stats.total_questions} | ответов: ${s.stats.total_answers}`),
          s.stats.completion_rate !== null &&
            h("div", null, `Completion rate: ${(s.stats.completion_rate * 100).toFixed(0)}%`),
          s.stats.content_potential_avg !== null &&
            h(
              "div",
              null,
              `Средний content_potential: ${s.stats.content_potential_avg.toFixed(1)}/10`
            )
        )
    );
  }

  function WeeklySection() {
    const [weekly, setWeekly] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(async () => {
      try {
        const r = await fetch("/api/plugins/promo/weekly");
        setWeekly(await r.json());
      } catch (e) {
        setWeekly({ found: false });
      } finally {
        setLoading(false);
      }
    }, null);

    if (loading()) return h("div", { style: { padding: 14, color: "#888" } }, "Загрузка…");
    if (!weekly() || !weekly().found)
      return h(
        "div",
        { style: { padding: 14, color: "#888" } },
        "Weekly-планов пока нет — dreamer ещё не отработал"
      );

    return h(
      "div",
      { style: { padding: 14 } },
      h("h3", { style: { margin: "0 0 8px 0" } }, "📋 Последний weekly plan"),
      h("div", { style: { color: "#888", fontSize: 12 } }, weekly().path),
      h(
        "pre",
        {
          style: {
            background: "rgba(255,255,255,0.04)",
            padding: 10,
            borderRadius: 4,
            overflow: "auto",
            maxHeight: 400,
            fontSize: 12,
            marginTop: 8,
            whiteSpace: "pre-wrap",
          },
        },
        weekly().content
      )
    );
  }

  function DraftsSection() {
    const [drafts, setDrafts] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(async () => {
      try {
        const r = await fetch("/api/plugins/promo/drafts");
        const d = await r.json();
        setDrafts(d.drafts || []);
      } catch (e) {
        setDrafts([]);
      } finally {
        setLoading(false);
      }
    }, null);

    if (loading()) return h("div", { style: { padding: 14, color: "#888" } }, "Загрузка…");
    if (drafts().length === 0)
      return h("div", { style: { padding: 14, color: "#888" } }, "Черновиков за последние 7 дней нет");

    return h(
      "div",
      { style: { padding: 14 } },
      h("h3", { style: { margin: "0 0 8px 0" } }, `📝 Черновики (${drafts().length})`),
      drafts().map((d) =>
        h(
          "div",
          {
            key: d.path,
            style: { padding: "6px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" },
          },
          h("div", { style: { fontFamily: "ui-monospace, monospace" } }, d.title),
          h("div", { style: { fontSize: 11, color: "#888" } }, d.path)
        )
      )
    );
  }

  // ─── Main component ─────────────────────────────────────────────
  function PromoApp(root) {
    const [tab, setTab] = useState("sources");

    const tabs = [
      { id: "sources", label: "🛰 Источники" },
      { id: "session", label: "🎙 Сессия" },
      { id: "weekly", label: "📋 Weekly" },
      { id: "drafts", label: "📝 Drafts" },
    ];

    root.innerHTML = "";

    const container = h(
      "div",
      {
        style: {
          padding: 20,
          maxWidth: 1100,
          margin: "0 auto",
          color: "inherit",
        },
      },
      h(
        "div",
        {
          style: {
            display: "flex",
            alignItems: "baseline",
            gap: 12,
            marginBottom: 16,
          },
        },
        h("h1", { style: { margin: 0, fontSize: 24 } }, "🪩 МАЯК"),
        h(
          "span",
          { style: { color: "#888", fontSize: 13 } },
          "personal promo pipeline Кирилла Вечкасова"
        )
      ),
      h(
        "div",
        {
          style: {
            display: "flex",
            gap: 4,
            borderBottom: "1px solid rgba(255,255,255,0.08)",
            marginBottom: 16,
          },
        },
        tabs.map((t) =>
          h(
            "button",
            {
              key: t.id,
              onClick: () => {
                setTab(t.id);
                render();
              },
              style: {
                padding: "8px 16px",
                border: "none",
                borderBottom:
                  tab() === t.id ? "2px solid #ff6b35" : "2px solid transparent",
                background: "transparent",
                color: tab() === t.id ? "#ff6b35" : "inherit",
                cursor: "pointer",
                fontWeight: tab() === t.id ? 600 : 400,
                fontSize: 13,
              },
            },
            t.label
          )
        )
      )
    );

    let content;
    if (tab() === "sources") content = h(SourcesSection);
    else if (tab() === "session") content = h(SessionSection);
    else if (tab() === "weekly") content = h(WeeklySection);
    else if (tab() === "drafts") content = h(DraftsSection);

    container.appendChild(content);
    root.appendChild(container);

    function render() {
      PromoApp(root);
    }
  }

  // ─── Register ────────────────────────────────────────────────────
  // Регистрируем через стандартный SDK Hermes
  if (window.__HERMES_PLUGINS__.register) {
    window.__HERMES_PLUGINS__.register("promo", function (root) {
      PromoApp(root);
    });
    console.log("[promo] плагин МАЯК зарегистрирован в Hermes dashboard");
  }
})();