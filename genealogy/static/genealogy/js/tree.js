/*
 * Interactive family graph.
 *
 * Renders /api/tree/ data with Cytoscape.js and a layered (dagre) layout.
 * Couples connect through a small "union" node, so each generation sits on
 * its own row with children hanging below their parents.
 */
(function () {
  "use strict";

  // The cytoscape-dagre UMD build registers itself when the global `cytoscape` exists;
  // register explicitly only if that didn't happen.
  function ensureDagre() {
    try {
      cytoscape({ headless: true }).layout({ name: "dagre" });
    } catch (error) {
      if (window.cytoscapeDagre) cytoscape.use(window.cytoscapeDagre);
    }
  }
  if (window.cytoscape) ensureDagre();

  const LINEAGE_COLORS = ["#0f766e", "#b45309", "#be185d", "#4338ca", "#15803d", "#a16207", "#0e7490", "#9f1239", "#6d28d9"];

  function token(name, alpha) {
    const value = getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim().split(/\s+/).join(",");
    return alpha === undefined ? `rgb(${value})` : `rgba(${value},${alpha})`;
  }

  function lineageColor(name) {
    if (!name) return token("muted", 0.6);
    let hash = 0;
    for (const ch of name.toLowerCase()) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
    return LINEAGE_COLORS[hash % LINEAGE_COLORS.length];
  }

  function stylesheet(colorMode) {
    const genderColors = { M: token("brand"), F: token("rose"), O: token("accent"), U: token("muted") };
    const borderColor = (ele) =>
      colorMode === "lineage" ? lineageColor(ele.data("lineage")) : genderColors[ele.data("gender")] || genderColors.U;

    return [
      {
        selector: "node[kind = 'person']",
        style: {
          shape: "round-rectangle",
          width: 190,
          height: 60,
          "background-color": token("surface"),
          "border-width": 2,
          "border-color": borderColor,
          label: (ele) => (ele.data("lifespan") ? `${ele.data("label")}\n${ele.data("lifespan")}` : ele.data("label")),
          "text-wrap": "wrap",
          "text-max-width": 164,
          "text-valign": "center",
          "text-halign": "center",
          "font-family": "Inter, system-ui, sans-serif",
          "font-size": 12.5,
          "font-weight": 600,
          "line-height": 1.4,
          color: token("ink"),
          "transition-property": "opacity, border-width",
          "transition-duration": 200,
        },
      },
      {
        selector: "node[kind = 'person'][photo]",
        style: {
          "background-image": "data(photo)",
          "background-fit": "none",
          "background-width": 42,
          "background-height": 42,
          "background-position-x": 9,
          "background-position-y": 9,
          "background-clip": "node",
          "text-margin-x": 22,
          "text-max-width": 124,
        },
      },
      {
        selector: "node[kind = 'person'][!living]",
        style: { "border-style": "dashed", "background-color": token("bg"), color: token("muted") },
      },
      {
        selector: "node[?root]",
        style: {
          "border-width": 3.5,
          "underlay-color": token("accent"),
          "underlay-opacity": 0.22,
          "underlay-padding": 7,
          "underlay-shape": "round-rectangle",
        },
      },
      {
        selector: "node[kind = 'union']",
        style: { shape: "ellipse", width: 11, height: 11, "background-color": token("accent"), "border-width": 0, label: "" },
      },
      {
        selector: "edge",
        style: {
          width: 1.7,
          "line-color": token("muted", 0.5),
          "curve-style": "taxi",
          "taxi-direction": "downward",
          "taxi-turn": "50%",
          "transition-property": "opacity, line-color, width",
          "transition-duration": 200,
        },
      },
      { selector: "edge[kind = 'partner']", style: { "line-color": token("accent", 0.75), width: 2 } },
      { selector: "edge[rtype = 'adopted'], edge[rtype = 'step'], edge[rtype = 'foster']", style: { "line-style": "dashed" } },
      { selector: "node:selected", style: { "underlay-color": token("brand"), "underlay-opacity": 0.25, "underlay-padding": 9, "underlay-shape": "round-rectangle" } },
      { selector: ".faded", style: { opacity: 0.16 } },
      { selector: "edge.highlight", style: { "line-color": token("brand"), width: 2.6 } },
      { selector: "edge.highlight[kind = 'partner']", style: { "line-color": token("accent") } },
    ];
  }

  const LAYOUT = {
    name: "dagre",
    rankDir: "TB",
    nodeSep: 26,
    rankSep: 56,
    edgeSep: 12,
    ranker: "network-simplex",
    fit: true,
    padding: 48,
    animationDuration: 380,
  };

  function createGraph(container, options) {
    const opts = Object.assign({ colorMode: "gender", mini: false }, options);
    let colorMode = opts.colorMode;

    const cy = cytoscape({
      container,
      elements: [],
      style: stylesheet(colorMode),
      minZoom: 0.1,
      maxZoom: 2.5,
      wheelSensitivity: 0.3,
      boxSelectionEnabled: false,
      autoungrabify: true,
      selectionType: "single",
    });

    function clearHighlight() {
      cy.elements().removeClass("faded highlight");
    }

    function highlightLine(node) {
      clearHighlight();
      const unions = node.outgoers("node[kind = 'union']");
      const partners = unions.incomers("node[kind = 'person']");
      const keep = node
        .union(node.predecessors())
        .union(node.successors())
        .union(unions)
        .union(unions.connectedEdges())
        .union(partners);
      cy.elements().not(keep).addClass("faded");
      keep.edges().addClass("highlight");
    }

    cy.on("tap", "node[kind = 'person']", (event) => {
      const node = event.target;
      if (opts.mini) {
        opts.onSelect && opts.onSelect(node.data());
        return;
      }
      highlightLine(node);
      opts.onSelect && opts.onSelect(node.data());
    });
    cy.on("tap", (event) => {
      if (event.target === cy) {
        clearHighlight();
        opts.onSelect && opts.onSelect(null);
      }
    });
    cy.on("mouseover", "node[kind = 'person']", () => (container.style.cursor = "pointer"));
    cy.on("mouseout", "node[kind = 'person']", () => (container.style.cursor = ""));

    function runLayout() {
      return new Promise((resolve) => {
        // Browsers pause animation frames in background tabs, so only animate when visible
        // and never let a stalled animation block the page.
        const animate = !opts.mini && !document.hidden && cy.nodes().length < 250;
        const layout = cy.layout(Object.assign({}, LAYOUT, { animate }));
        let done = false;
        const finish = () => {
          if (!done) {
            done = true;
            resolve();
          }
        };
        layout.one("layoutstop", finish);
        setTimeout(finish, LAYOUT.animationDuration + 600);
        layout.run();
      });
    }

    async function load(params) {
      const url = new URL(opts.endpoint, window.location.origin);
      Object.entries(params || {}).forEach(([key, value]) => {
        if (value !== null && value !== undefined && value !== "") url.searchParams.set(key, value);
      });
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`Tree request failed with status ${response.status}`);
      const data = await response.json();
      cy.elements().remove();
      cy.add(data.elements);
      await runLayout();
      if (data.root && !opts.mini && cy.nodes().length > 30) {
        const root = cy.$id(`p${data.root}`);
        if (root.nonempty()) cy.animate({ center: { eles: root }, zoom: 0.85 }, { duration: 350 });
      }
      return data;
    }

    return {
      cy,
      load,
      clearHighlight,
      setColorMode(mode) {
        colorMode = mode;
        cy.style(stylesheet(colorMode));
      },
      refreshTheme() {
        cy.style(stylesheet(colorMode));
      },
      fit() {
        cy.animate({ fit: { eles: cy.elements(), padding: 48 } }, { duration: 300 });
      },
      zoomBy(factor) {
        cy.animate(
          { zoom: { level: cy.zoom() * factor, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } } },
          { duration: 180 }
        );
      },
      focus(pk) {
        const node = cy.$id(`p${pk}`);
        if (node.empty()) return false;
        cy.$(":selected").unselect();
        node.select();
        highlightLine(node);
        cy.animate({ center: { eles: node }, zoom: Math.max(cy.zoom(), 1) }, { duration: 400 });
        opts.onSelect && opts.onSelect(node.data());
        return true;
      },
      png() {
        return cy.png({ full: true, scale: 2, bg: token("bg") });
      },
    };
  }

  // Alpine component for the full tree page.
  window.treeExplorer = function (config) {
    let graph = null; // kept outside Alpine's reactive proxy

    return {
      loading: true,
      error: "",
      count: 0,
      rootId: config.rootId,
      rootName: config.rootName,
      showAll: !config.rootId,
      up: config.up,
      down: config.down,
      colorMode: "gender",
      canEdit: config.canEdit,
      selected: null,
      panelOpen: false,
      controlsOpen: window.matchMedia("(min-width: 1024px)").matches,
      query: "",
      results: [],

      init() {
        graph = createGraph(this.$refs.canvas, {
          endpoint: config.endpoint,
          onSelect: (data) => {
            this.selected = data;
            this.panelOpen = Boolean(data);
          },
        });
        window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => graph.refreshTheme());
        this.reload().then(() => {
          if (this.rootId && !this.showAll) graph.focus(this.rootId);
        });
      },

      async reload() {
        this.loading = true;
        this.error = "";
        try {
          const params = this.showAll ? {} : { root: this.rootId, up: this.up, down: this.down };
          const data = await graph.load(params);
          this.count = data.count;
          this.syncUrl();
        } catch (err) {
          console.error(err);
          this.error = "We couldn't load the family tree. Please check your connection and try again.";
        } finally {
          this.loading = false;
        }
      },

      syncUrl() {
        const url = new URL(window.location.href);
        url.search = "";
        if (!this.showAll && this.rootId) {
          url.searchParams.set("root", this.rootId);
          url.searchParams.set("up", this.up);
          url.searchParams.set("down", this.down);
        }
        window.history.replaceState(null, "", url);
      },

      async search() {
        const q = this.query.trim();
        if (q.length < 2) {
          this.results = [];
          return;
        }
        const response = await fetch(`${config.searchEndpoint}?q=${encodeURIComponent(q)}`, {
          headers: { Accept: "application/json" },
        });
        this.results = (await response.json()).results;
      },

      choose(person) {
        this.query = "";
        this.results = [];
        if (!graph.focus(person.pk)) this.centerOn(person);
        if (!window.matchMedia("(min-width: 1024px)").matches) this.controlsOpen = false;
      },

      async centerOn(person) {
        this.rootId = person.pk;
        this.rootName = person.name;
        this.showAll = false;
        await this.reload();
        graph.focus(person.pk);
      },

      setShowAll(value) {
        if (value === this.showAll) return;
        if (!value && !this.rootId) {
          const fallback = this.selected || { pk: config.defaultRootId, name: config.defaultRootName };
          if (!fallback.pk) return;
          this.rootId = fallback.pk;
          this.rootName = fallback.name;
        }
        this.showAll = value;
        this.reload();
      },

      setColorMode(mode) {
        this.colorMode = mode;
        graph.setColorMode(mode);
      },

      fit() {
        graph.fit();
      },
      zoomIn() {
        graph.zoomBy(1.25);
      },
      zoomOut() {
        graph.zoomBy(0.8);
      },

      download() {
        const link = document.createElement("a");
        link.href = graph.png();
        link.download = "family-tree.png";
        link.click();
      },

      closePanel() {
        this.panelOpen = false;
        this.selected = null;
        graph.clearHighlight();
      },
    };
  };

  window.FamilyGraph = { create: createGraph };
})();
