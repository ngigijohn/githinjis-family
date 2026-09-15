/*
 * Interactive family graph.
 *
 * Renders /api/tree/ data with Cytoscape.js and a layered (dagre) layout.
 * Each person is drawn as a card (an SVG image, so PNG export keeps working).
 * Couples meet at a small rings symbol between the partners, children hang
 * from a shared line below them, and faint bands behind the graph mark each
 * generation.
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

  // Mid-tone colours that stay readable on both light and dark grounds.
  const PALETTE = ["#2f8f83", "#c47f1a", "#8a63c9", "#c2566f", "#4f8a3a", "#3f7fbf", "#b5613a", "#5f7f8f"];

  // The card is 220×72; the node is larger to leave room for the shadow and selection ring.
  const CARD_W = 236;
  const CARD_H = 88;
  const UNION_SIZE = 26;
  // SVG images can't use the page's web fonts, so cards use system fonts and are measured with them.
  const CARD_FONT = '"Segoe UI", system-ui, -apple-system, Helvetica, Arial, sans-serif';
  const TEXT_MAX = 140;

  const LAYOUT = {
    name: "dagre",
    rankDir: "TB",
    nodeSep: 16,
    rankSep: 30,
    edgeSep: 10,
    ranker: "network-simplex",
    fit: false,
    animate: false,
    padding: 40,
  };

  function token(name, alpha) {
    const value = getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim().split(/\s+/).join(",");
    return alpha === undefined ? `rgb(${value})` : `rgba(${value},${alpha})`;
  }

  function readTheme() {
    const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    return {
      bg: token("bg"),
      surface: token("surface"),
      stage: token("stage"),
      line: token("line"),
      ink: token("ink"),
      muted: token("muted"),
      mutedLine: token("muted", 0.55),
      brand: token("brand"),
      brandBand: token("brand", 0.045),
      accent: token("accent"),
      accentLine: token("accent", 0.7),
      male: token("male"),
      maleSoft: token("male-soft"),
      rose: token("rose"),
      roseSoft: token("rose-soft"),
      shadow: dark ? "#000000" : "rgb(60,45,20)",
      shadowOpacity: dark ? 0.5 : 0.14,
    };
  }

  function hashColor(name) {
    if (!name) return null;
    let hash = 0;
    for (const ch of name.toLowerCase()) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
    return PALETTE[hash % PALETTE.length];
  }

  const measurer = document.createElement("canvas").getContext("2d");
  function fitText(text, size, weight, max) {
    measurer.font = `${weight} ${size}px ${CARD_FONT}`;
    if (measurer.measureText(text).width <= max) return text;
    let cut = text;
    while (cut.length > 1 && measurer.measureText(`${cut}…`).width > max) cut = cut.slice(0, -1);
    return `${cut.trimEnd()}…`;
  }

  const XML_ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" };
  const xml = (value) => String(value).replace(/[&<>"']/g, (ch) => XML_ESCAPES[ch]);

  function svgUri(body, width, height) {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${body}</svg>`;
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  }

  const imageCache = new Map();
  function cached(key, build) {
    if (!imageCache.has(key)) {
      if (imageCache.size > 3000) imageCache.clear();
      imageCache.set(key, build());
    }
    return imageCache.get(key);
  }

  function cardImage(d, tone, selected, colors) {
    const dead = !d.living;
    const key = [d.label, d.lifespan, dead, d.initials, d.photoData ? d.photo : "", tone.ring, tone.fill, tone.fillOpacity, selected, colors.surface, colors.shadow].join("|");
    return cached(key, () => {
      const font = `font-family='${CARD_FONT.replace(/"/g, "")}'`;
      const name = xml(fitText(d.label, 13.5, 600, TEXT_MAX));
      const sub = xml(fitText(d.lifespan || (dead ? "Deceased" : "Dates not recorded"), 12, 400, TEXT_MAX));
      const parts = [];
      if (!dead) {
        parts.push(
          `<defs><filter id="s" x="-15%" y="-25%" width="130%" height="160%"><feDropShadow dx="0" dy="4" stdDeviation="4.5" flood-color="${colors.shadow}" flood-opacity="${colors.shadowOpacity}"/></filter></defs>`
        );
      }
      if (selected) {
        parts.push(`<rect x="3" y="2" width="230" height="82" rx="19" fill="none" stroke="${colors.brand}" stroke-width="3" stroke-opacity="0.5"/>`);
      }
      parts.push(
        dead
          ? `<rect x="8" y="7" width="220" height="72" rx="15" fill="${colors.bg}" stroke="${colors.mutedLine}" stroke-dasharray="5 4"/>`
          : `<rect x="8" y="7" width="220" height="72" rx="15" fill="${colors.surface}" stroke="${colors.line}" filter="url(#s)"/>`
      );
      parts.push(`<circle cx="44" cy="43" r="22" fill="${tone.fill}" fill-opacity="${tone.fillOpacity}"/>`);
      if (d.photoData) {
        parts.push(
          `<clipPath id="c"><circle cx="44" cy="43" r="21"/></clipPath><image x="22" y="21" width="44" height="44" preserveAspectRatio="xMidYMid slice" clip-path="url(#c)" href="${d.photoData}" xlink:href="${d.photoData}"/>`
        );
      } else {
        parts.push(`<text x="44" y="47.5" text-anchor="middle" ${font} font-size="13" font-weight="700" fill="${tone.ring}">${xml(d.initials || "?")}</text>`);
      }
      parts.push(`<circle cx="44" cy="43" r="22" fill="none" stroke="${tone.ring}" stroke-width="2.5"${dead ? ' stroke-dasharray="3 3"' : ""}/>`);
      parts.push(`<text x="78" y="39" ${font} font-size="13.5" font-weight="600" fill="${dead ? colors.muted : colors.ink}">${name}</text>`);
      parts.push(`<text x="78" y="58" ${font} font-size="12" fill="${colors.muted}">${sub}</text>`);
      return svgUri(parts.join(""), CARD_W, CARD_H);
    });
  }

  function unionImage(colors) {
    return cached(`union|${colors.surface}|${colors.accent}`, () =>
      svgUri(
        `<circle cx="13" cy="13" r="12" fill="${colors.surface}" stroke="${colors.line}"/>` +
          `<circle cx="9.8" cy="13" r="5.3" fill="none" stroke="${colors.accent}" stroke-width="2"/>` +
          `<circle cx="16.2" cy="13" r="5.3" fill="none" stroke="${colors.accent}" stroke-width="2"/>`,
        UNION_SIZE,
        UNION_SIZE
      )
    );
  }

  function createGraph(container, options) {
    const opts = Object.assign({ colorMode: "gender", mini: false }, options);
    let colorMode = opts.colorMode;
    let colors = readTheme();
    let rows = [];
    let branches = [];

    if (getComputedStyle(container).position === "static") container.style.position = "relative";
    const bands = document.createElement("canvas");
    bands.setAttribute("aria-hidden", "true");
    Object.assign(bands.style, { position: "absolute", inset: "0", width: "100%", height: "100%", pointerEvents: "none" });
    container.prepend(bands);

    const cy = cytoscape({
      container,
      elements: [],
      minZoom: 0.1,
      maxZoom: 2.5,
      wheelSensitivity: 0.3,
      boxSelectionEnabled: false,
      autoungrabify: true,
      selectionType: "single",
    });

    // ---- Colours -----------------------------------------------------------

    const neutralTone = () => ({ ring: colors.muted, fill: colors.line, fillOpacity: 0.7 });
    const hexTone = (hex) => ({ ring: hex, fill: hex, fillOpacity: 0.16 });
    const branchColor = (node) => {
      const index = node.scratch("_branch");
      return index === undefined ? null : PALETTE[index % PALETTE.length];
    };

    function toneFor(node) {
      if (colorMode === "branch") {
        const color = branchColor(node);
        return color ? hexTone(color) : neutralTone();
      }
      if (colorMode === "lineage") {
        const color = hashColor(node.data("lineage"));
        return color ? hexTone(color) : neutralTone();
      }
      const gender = node.data("gender");
      if (gender === "M") return { ring: colors.male, fill: colors.maleSoft, fillOpacity: 1 };
      if (gender === "F") return { ring: colors.rose, fill: colors.roseSoft, fillOpacity: 1 };
      return neutralTone();
    }

    const descentColor = (edge) => (colorMode === "branch" && branchColor(edge.target())) || colors.mutedLine;

    function stylesheet() {
      const card = (selected) => (node) => cardImage(node.data(), toneFor(node), selected, colors);
      const haloSelector = opts.mini ? "node[kind = 'person']:selected, node[kind = 'person'][?root]" : "node[kind = 'person']:selected";
      return [
        { selector: "node", style: { "overlay-opacity": 0 } },
        {
          selector: "node[kind = 'person']",
          style: {
            shape: "round-rectangle",
            width: CARD_W,
            height: CARD_H,
            "background-opacity": 0,
            "border-width": 0,
            "background-image": card(false),
            "background-width": "100%",
            "background-height": "100%",
            label: "",
            "transition-property": "opacity",
            "transition-duration": 200,
          },
        },
        { selector: haloSelector, style: { "background-image": card(true) } },
        {
          selector: "node[kind = 'union']",
          style: {
            shape: "ellipse",
            width: UNION_SIZE,
            height: UNION_SIZE,
            "background-opacity": 0,
            "border-width": 0,
            "background-image": unionImage(colors),
            "background-width": "100%",
            "background-height": "100%",
            label: "",
            events: "no",
            "transition-property": "opacity",
            "transition-duration": 200,
          },
        },
        {
          selector: "edge",
          style: {
            width: 1.8,
            "line-color": descentColor,
            "curve-style": "round-taxi",
            "taxi-direction": "downward",
            "taxi-turn": "-22px",
            "taxi-turn-min-distance": 8,
            "taxi-radius": 12,
            "transition-property": "opacity, line-color, width",
            "transition-duration": 200,
          },
        },
        { selector: "edge[kind = 'partner']", style: { "curve-style": "straight", "line-color": colors.accentLine, width: 2 } },
        { selector: "edge[rtype = 'adopted'], edge[rtype = 'step'], edge[rtype = 'foster']", style: { "line-style": "dashed", "line-dash-pattern": [6, 4] } },
        { selector: ".faded", style: { opacity: 0.18 } },
        { selector: "edge.highlight", style: { "line-color": (edge) => (colorMode === "branch" && branchColor(edge.target())) || colors.brand, width: 2.8 } },
        { selector: "edge.highlight[kind = 'partner']", style: { "line-color": colors.accent, width: 2.6 } },
      ];
    }

    const applyStyle = () => cy.style(stylesheet());
    applyStyle();

    // ---- Family structure --------------------------------------------------

    const partnersOf = (node) => node.outgoers("node[kind = 'union']").incomers("node[kind = 'person']").difference(node);
    const childrenOf = (node) => node.outgoers("node[kind = 'union']").outgoers("node").union(node.outgoers("node[kind = 'person']"));
    const hasParents = (node) => node.incomers("edge[kind = 'child']").nonempty();

    // Branches start at the first couple (walking down from the founders with the
    // most descendants) that has more than one child. Everyone above stays neutral.
    function computeBranches() {
      const people = cy.nodes("[kind = 'person']");
      people.forEach((node) => node.removeScratch("_branch"));
      branches = [];
      const founders = people.filter((node) => !hasParents(node));
      if (founders.empty()) return;

      const size = (node) => node.successors("node[kind = 'person']").length;
      let current = founders.toArray().sort((a, b) => size(b) - size(a) || a.data("pk") - b.data("pk"))[0];
      const trunk = new Set();
      const addTrunk = (node) => {
        trunk.add(node.id());
        partnersOf(node).forEach((partner) => trunk.add(partner.id()));
      };
      addTrunk(current);
      let kids = childrenOf(current);
      while (kids.length === 1 && !trunk.has(kids[0].id())) {
        current = kids[0];
        addTrunk(current);
        kids = childrenOf(current);
      }
      if (kids.length < 2) return;

      kids
        .toArray()
        .sort((a, b) => a.position("x") - b.position("x"))
        .forEach((kid, index) => {
          branches.push({ label: `${kid.data("name")}'s family`, color: PALETTE[index % PALETTE.length] });
          const queue = [kid];
          while (queue.length) {
            const node = queue.shift();
            if (trunk.has(node.id()) || node.scratch("_branch") !== undefined) continue;
            node.scratch("_branch", index);
            partnersOf(node).forEach((partner) => {
              if (!trunk.has(partner.id()) && partner.scratch("_branch") === undefined) partner.scratch("_branch", index);
            });
            childrenOf(node).forEach((child) => queue.push(child));
          }
        });
    }

    // dagre doesn't know partners belong together and can leave a sibling between a couple.
    // Reorder each row so partners sit next to each other, reusing the row's x positions.
    function arrangeCouples() {
      const rowsByY = new Map();
      cy.nodes("[kind = 'person']").forEach((node) => {
        const y = Math.round(node.position("y"));
        if (!rowsByY.has(y)) rowsByY.set(y, []);
        rowsByY.get(y).push(node);
      });
      rowsByY.forEach((row) => {
        if (row.length < 3) return;
        const slots = row.map((node) => node.position("x")).sort((a, b) => a - b);
        const order = row.slice().sort((a, b) => a.position("x") - b.position("x"));
        const inRow = new Set(order.map((node) => node.id()));
        cy.nodes("[kind = 'union']").forEach((union) => {
          const partners = union.incomers("node[kind = 'person']").filter((partner) => inRow.has(partner.id()));
          if (partners.length !== 2) return;
          // Move whoever married in (no recorded parents) next to the partner born into the family.
          let [anchor, mover] = partners.toArray();
          if (!hasParents(anchor) && hasParents(mover)) [anchor, mover] = [mover, anchor];
          if (Math.abs(order.indexOf(anchor) - order.indexOf(mover)) === 1) return;
          order.splice(order.indexOf(mover), 1);
          const at = order.indexOf(anchor);
          const right = order[at + 1];
          order.splice(right && partnersOf(anchor).has(right) ? at : at + 1, 0, mover);
        });
        order.forEach((node, i) => node.position("x", slots[i]));
      });
    }

    // Put each couple's rings between the partners, on their row.
    function tidyUnions() {
      cy.nodes("[kind = 'union']").forEach((union) => {
        const partners = union.incomers("node[kind = 'person']");
        if (partners.length !== 2) return;
        const [a, b] = partners.map((partner) => partner.position());
        const sideBySide = Math.abs(a.y - b.y) < 1 && Math.abs(a.x - b.x) <= CARD_W + LAYOUT.nodeSep + 2;
        if (sideBySide) union.position({ x: (a.x + b.x) / 2, y: a.y });
      });
    }

    function computeRows() {
      const byY = new Map();
      cy.nodes("[kind = 'person']").forEach((node) => {
        const y = Math.round(node.position("y"));
        const row = byY.get(y) || { y, generation: Infinity };
        const generation = node.data("generation");
        if (generation) row.generation = Math.min(row.generation, generation);
        byY.set(y, row);
      });
      rows = [...byY.values()].sort((a, b) => a.y - b.y);
    }

    // ---- Generation bands --------------------------------------------------

    function drawBands() {
      const width = container.clientWidth;
      const height = container.clientHeight;
      const ratio = window.devicePixelRatio || 1;
      if (bands.width !== Math.round(width * ratio) || bands.height !== Math.round(height * ratio)) {
        bands.width = Math.round(width * ratio);
        bands.height = Math.round(height * ratio);
      }
      const ctx = bands.getContext("2d");
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.clearRect(0, 0, width, height);
      if (!rows.length) return;

      const zoom = cy.zoom();
      const pan = cy.pan();
      const ys = rows.map((row) => row.y * zoom + pan.y);
      const fallbackHalf = 90 * zoom;
      ctx.font = `600 10.5px Inter, ${CARD_FONT}`;
      ctx.textAlign = "right";
      if ("letterSpacing" in ctx) ctx.letterSpacing = "1.6px";

      rows.forEach((row, i) => {
        const top = i ? (ys[i - 1] + ys[i]) / 2 : ys[i] - (ys.length > 1 ? (ys[1] - ys[0]) / 2 : fallbackHalf);
        const bottom = i < ys.length - 1 ? (ys[i] + ys[i + 1]) / 2 : ys[i] + (i ? (ys[i] - ys[i - 1]) / 2 : fallbackHalf);
        if (bottom < 0 || top > height) return;
        if (i % 2) {
          ctx.fillStyle = colors.brandBand;
          ctx.fillRect(0, top, width, bottom - top);
        }
        if (i) {
          ctx.fillStyle = colors.line;
          ctx.fillRect(0, Math.round(top), width, 1);
        }
        if (!opts.mini && Number.isFinite(row.generation) && bottom - top > 70) {
          ctx.fillStyle = colors.muted;
          ctx.fillText(`GENERATION ${row.generation}`, width - 16, Math.max(top, 0) + 22);
        }
      });
    }

    let bandFrame = 0;
    const scheduleBands = () => {
      if (!bandFrame) {
        bandFrame = requestAnimationFrame(() => {
          bandFrame = 0;
          drawBands();
        });
      }
    };
    cy.on("viewport resize", scheduleBands);

    // ---- Photos ------------------------------------------------------------

    // Card images can't load external files, so each photo is cropped into a data URI first.
    const photoCache = new Map();
    function loadPhotos() {
      cy.nodes("[kind = 'person'][photo]").forEach((node) => {
        const src = node.data("photo");
        if (photoCache.has(src)) {
          node.data("photoData", photoCache.get(src));
          return;
        }
        const img = new Image();
        img.onload = () => {
          const canvas = document.createElement("canvas");
          canvas.width = canvas.height = 96;
          const side = Math.min(img.naturalWidth, img.naturalHeight);
          canvas.getContext("2d").drawImage(img, (img.naturalWidth - side) / 2, (img.naturalHeight - side) / 2, side, side, 0, 0, 96, 96);
          try {
            const uri = canvas.toDataURL("image/jpeg", 0.85);
            photoCache.set(src, uri);
            if (!node.removed()) node.data("photoData", uri);
          } catch (error) {
            console.warn("Could not prepare photo for the tree", src, error);
          }
        };
        img.src = src;
      });
    }

    // ---- Interaction -------------------------------------------------------

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
      if (!opts.mini) highlightLine(node);
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
        const layout = cy.layout(LAYOUT);
        layout.one("layoutstop", () => {
          arrangeCouples();
          tidyUnions();
          computeRows();
          computeBranches();
          applyStyle();
          cy.fit(cy.elements(), LAYOUT.padding);
          drawBands();
          resolve();
        });
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
      loadPhotos();
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
        applyStyle();
      },
      refreshTheme() {
        colors = readTheme();
        applyStyle();
        drawBands();
      },
      people() {
        return cy.nodes("[kind = 'person']").map((node) => node.data());
      },
      branches() {
        return branches.slice();
      },
      fit() {
        cy.animate({ fit: { eles: cy.elements(), padding: LAYOUT.padding } }, { duration: 300 });
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
        return cy.png({ full: true, scale: 2, bg: colors.stage });
      },
    };
  }

  // ---- Search helpers ------------------------------------------------------

  const normalize = (text) =>
    String(text || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/\p{Diacritic}/gu, "");

  const initialsOf = (label) =>
    String(label || "")
      .replace(/\(.*?\)/g, "")
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((word) => word[0].toUpperCase())
      .join("");

  // Alpine component for the full tree page.
  window.treeExplorer = function (config) {
    let graph = null; // kept outside Alpine's reactive proxy
    let remoteTimer = 0;

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
      branches: [],
      canEdit: config.canEdit,
      selected: null,
      panelOpen: false,
      controlsOpen: window.matchMedia("(min-width: 1024px)").matches,
      query: "",
      results: [],
      active: -1,
      searched: false,

      init() {
        graph = createGraph(this.$refs.canvas, {
          endpoint: config.endpoint,
          onSelect: (data) => {
            this.selected = data;
            this.panelOpen = Boolean(data);
            this.query = data ? data.label : "";
            this.results = [];
            this.searched = false;
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
          this.branches = graph.branches();
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

      // Filters the people already on the tree as you type. In a focused view it also
      // asks the server, so relatives outside the view can still be found.
      search() {
        const query = normalize(this.query.trim());
        this.active = -1;
        clearTimeout(remoteTimer);
        if (!query) {
          this.results = [];
          this.searched = false;
          return;
        }
        const words = query.split(/\s+/);
        const score = (person) => {
          const label = normalize(person.label);
          if (label.startsWith(query)) return 0;
          return label.split(/\s+/).some((word) => word.startsWith(words[0])) ? 1 : 2;
        };
        this.results = graph
          .people()
          .filter((person) => {
            const haystack = normalize(`${person.label} ${person.name}`);
            return words.every((word) => haystack.includes(word));
          })
          .sort((a, b) => score(a) - score(b) || a.label.localeCompare(b.label))
          .slice(0, 8);
        this.searched = true;

        if (!this.showAll && query.length >= 2) {
          const asked = this.query;
          remoteTimer = setTimeout(async () => {
            try {
              const response = await fetch(`${config.searchEndpoint}?q=${encodeURIComponent(asked.trim())}`, {
                headers: { Accept: "application/json" },
              });
              if (!response.ok || asked !== this.query) return;
              const shown = new Set(this.results.map((person) => person.pk));
              const outside = (await response.json()).results
                .filter((person) => !shown.has(person.pk) && !graph.cy.$id(`p${person.pk}`).nonempty())
                .map((person) => Object.assign({}, person, { outside: true }));
              this.results = this.results.concat(outside).slice(0, 10);
            } catch (error) {
              console.warn("Search request failed", error);
            }
          }, 200);
        }
      },

      move(step) {
        if (!this.results.length) return this.search();
        this.active = (this.active + step + this.results.length) % this.results.length;
        const option = document.getElementById(`tree-result-${this.active}`);
        option && option.scrollIntoView({ block: "nearest" });
      },

      choose(person) {
        clearTimeout(remoteTimer);
        this.results = [];
        this.active = -1;
        this.searched = false;
        if (!person) return;
        this.query = person.label;
        if (!person.outside && graph.focus(person.pk)) {
          if (!window.matchMedia("(min-width: 1024px)").matches) this.controlsOpen = false;
        } else {
          this.centerOn(person);
        }
      },

      clearLine() {
        this.query = "";
        this.results = [];
        this.searched = false;
        this.closePanel();
      },

      toneClass(person) {
        if (!person) return "";
        if (person.gender === "M") return "bg-male-soft text-male";
        if (person.gender === "F") return "bg-rose-soft text-rose";
        return "bg-line/70 text-muted";
      },

      initials(person) {
        return (person && (person.initials || initialsOf(person.label))) || "?";
      },

      async centerOn(person) {
        this.rootId = person.pk;
        this.rootName = person.name || person.label;
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
        this.query = "";
        graph.cy.$(":selected").unselect();
        graph.clearHighlight();
      },
    };
  };

  window.FamilyGraph = { create: createGraph };
})();
