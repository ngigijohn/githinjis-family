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

  // The card is 220×82; the node is larger to leave room for the shadow and selection ring.
  const CARD_W = 236;
  const CARD_H = 98;
  const UNION_SIZE = 26;
  // SVG images can't use the page's web fonts, so cards use system fonts and are measured with them.
  const CARD_FONT = '"Segoe UI", system-ui, -apple-system, Helvetica, Arial, sans-serif';
  const TEXT_MAX = 140;

  // Network physics, adjustable from the tree page. Values mirror the sliders people see.
  const PHYSICS_DEFAULTS = { centre: 0.1, repel: 10, linkForce: 0.5, linkDistance: 72, generations: true };
  const PHYSICS_KEY = "familyTree.physics";
  function loadPhysics() {
    try {
      return Object.assign({}, PHYSICS_DEFAULTS, JSON.parse(localStorage.getItem(PHYSICS_KEY) || "{}"));
    } catch (error) {
      return Object.assign({}, PHYSICS_DEFAULTS);
    }
  }

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
      onBrand: token("on-brand"),
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
    const badgeText = d.birthOrder || (d.tags && d.tags[0]) || "";
    const key = [d.label, d.lifespan, dead, d.initials, d.photoData ? d.photo : "", badgeText, tone.ring, tone.fill, tone.fillOpacity, selected, colors.surface, colors.shadow].join("|");
    return cached(key, () => {
      const font = `font-family='${CARD_FONT.replace(/"/g, "")}'`;
      const name = xml(fitText(d.label, 13.5, 600, TEXT_MAX));
      const sub = xml(fitText(d.lifespan || (dead ? "Deceased" : "Dates not recorded"), 12, 400, TEXT_MAX));
      const badge = badgeText ? xml(fitText(badgeText, 11, 600, TEXT_MAX)) : "";
      const [nameY, subY] = badge ? [39, 56] : [46, 64];
      const parts = [];
      if (!dead) {
        parts.push(
          `<defs><filter id="s" x="-15%" y="-25%" width="130%" height="160%"><feDropShadow dx="0" dy="4" stdDeviation="4.5" flood-color="${colors.shadow}" flood-opacity="${colors.shadowOpacity}"/></filter></defs>`
        );
      }
      if (selected) {
        parts.push(`<rect x="3" y="2" width="230" height="92" rx="19" fill="none" stroke="${colors.brand}" stroke-width="3" stroke-opacity="0.5"/>`);
      }
      parts.push(
        dead
          ? `<rect x="8" y="7" width="220" height="82" rx="15" fill="${colors.bg}" stroke="${colors.mutedLine}" stroke-dasharray="5 4"/>`
          : `<rect x="8" y="7" width="220" height="82" rx="15" fill="${colors.surface}" stroke="${colors.line}" filter="url(#s)"/>`
      );
      parts.push(`<circle cx="44" cy="48" r="22" fill="${tone.fill}" fill-opacity="${tone.fillOpacity}"/>`);
      if (d.photoData) {
        parts.push(
          `<clipPath id="c"><circle cx="44" cy="48" r="21"/></clipPath><image x="22" y="26" width="44" height="44" preserveAspectRatio="xMidYMid slice" clip-path="url(#c)" href="${d.photoData}" xlink:href="${d.photoData}"/>`
        );
      } else {
        parts.push(`<text x="44" y="52.5" text-anchor="middle" ${font} font-size="13" font-weight="700" fill="${tone.ring}">${xml(d.initials || "?")}</text>`);
      }
      parts.push(`<circle cx="44" cy="48" r="22" fill="none" stroke="${tone.ring}" stroke-width="2.5"${dead ? ' stroke-dasharray="3 3"' : ""}/>`);
      parts.push(`<text x="78" y="${nameY}" ${font} font-size="13.5" font-weight="600" fill="${dead ? colors.muted : colors.ink}">${name}</text>`);
      parts.push(`<text x="78" y="${subY}" ${font} font-size="12" fill="${colors.muted}">${sub}</text>`);
      if (badge) {
        parts.push(`<text x="78" y="74" ${font} font-size="11" font-weight="600" fill="${colors.accent}">${badge}</text>`);
      }
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
    const opts = Object.assign({ colorMode: "gender", layout: "tree", mini: false }, options);
    let colorMode = opts.colorMode;
    let layoutMode = opts.layout === "network" ? "network" : "tree";
    let colors = readTheme();
    let rows = [];
    let branches = [];
    let simulation = null;
    let simNodes = new Map();
    let physics = Object.assign({}, PHYSICS_DEFAULTS, opts.physics);
    let gatherTimer = 0;
    let placeNodes = () => {};

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
      autoungrabify: layoutMode !== "network",
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
      const tree = [
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
          selector: "node[kind = 'person'][role]",
          style: {
            label: "data(role)",
            "font-family": `Inter, ${CARD_FONT}`,
            "font-size": 11,
            "font-weight": 700,
            color: colors.onBrand,
            "text-valign": "top",
            "text-halign": "center",
            "text-margin-y": 16,
            "text-background-color": colors.brand,
            "text-background-opacity": 1,
            "text-background-shape": "round-rectangle",
            "text-background-padding": 4,
            "text-events": "no",
          },
        },
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
      ];
      const network = [
        {
          selector: "node[kind = 'person']",
          style: {
            shape: "ellipse",
            width: "data(size)",
            height: "data(size)",
            "background-color": (node) => toneFor(node).ring,
            "background-opacity": (node) => (node.data("living") ? 1 : 0.35),
            "border-width": (node) => (node.data("living") ? 0 : 2),
            "border-style": "dashed",
            "border-color": (node) => toneFor(node).ring,
            label: "data(label)",
            "font-family": `Inter, ${CARD_FONT}`,
            "font-size": 11,
            color: colors.ink,
            "text-valign": "bottom",
            "text-halign": "center",
            "text-margin-y": 5,
            "text-outline-color": colors.stage,
            "text-outline-width": 2.5,
            "min-zoomed-font-size": 9,
            "transition-property": "opacity",
            "transition-duration": 150,
          },
        },
        { selector: "node[kind = 'person'][photoData]", style: { "background-image": "data(photoData)", "background-fit": "cover", "background-opacity": 1 } },
        {
          selector: "node[kind = 'person'][role]",
          style: { label: (node) => `${node.data("role")} · ${node.data("label")}`, "font-weight": 700, color: colors.brand, "min-zoomed-font-size": 0 },
        },
        { selector: "node[kind = 'person']:selected", style: { "border-width": 3, "border-style": "solid", "border-color": colors.brand } },
        {
          selector: "edge",
          style: {
            "curve-style": "straight",
            width: 1.2,
            "line-color": descentColor,
            opacity: 0.6,
            "transition-property": "opacity, line-color, width",
            "transition-duration": 150,
          },
        },
        { selector: "edge[kind = 'partner']", style: { "line-color": colors.accentLine, width: 2 } },
        { selector: "edge[rtype = 'adopted'], edge[rtype = 'step'], edge[rtype = 'foster']", style: { "line-style": "dashed", "line-dash-pattern": [5, 4] } },
      ];
      const interaction = [
        { selector: ".faded", style: { opacity: 0.18 } },
        { selector: "edge.highlight", style: { "line-color": (edge) => (colorMode === "branch" && branchColor(edge.target())) || colors.brand, width: 2.8, opacity: 1 } },
        { selector: "edge.highlight[kind = 'partner']", style: { "line-color": colors.accent, width: 2.6 } },
        { selector: ".dimmed", style: { opacity: 0.1 } },
        { selector: "node.near", style: { opacity: 1, "min-zoomed-font-size": 0, "font-weight": 600, "z-index": 10 } },
        { selector: "edge.near", style: { opacity: 1, "line-color": colors.brand, width: 2.6, "z-index": 9 } },
        { selector: "edge.near[kind = 'partner']", style: { "line-color": colors.accent } },
      ];
      return [{ selector: "node", style: { "overlay-opacity": 0 } }, ...(layoutMode === "network" ? network : tree), ...interaction];
    }

    const applyStyle = () => cy.style(stylesheet());
    applyStyle();

    // ---- Family structure --------------------------------------------------

    const partnersOf = (node) => node.outgoers("node[kind = 'union']").incomers("node[kind = 'person']").difference(node);
    const childrenOf = (node) => node.outgoers("node[kind = 'union']").outgoers("node").union(node.outgoers("node[kind = 'person']"));
    const hasParents = (node) => node.incomers("edge[kind = 'child']").nonempty();

    // Branches start at the first couple (walking down from the founders with the
    // most descendants) that has more than one child. Everyone above stays neutral.
    // Works on the tree's family structure, so the network computes it before flattening.
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

    // dagre doesn't know partners belong together and can leave other people between a couple.
    // Reorder each row so partners are neighbours, pull each couple to a fixed distance,
    // then push apart anyone overlapping while keeping the row centred where dagre put it.
    function arrangeCouples() {
      const gap = CARD_W + LAYOUT.nodeSep;
      const rowsByY = new Map();
      cy.nodes("[kind = 'person']").forEach((node) => {
        const y = Math.round(node.position("y"));
        if (!rowsByY.has(y)) rowsByY.set(y, []);
        rowsByY.get(y).push(node);
      });
      rowsByY.forEach((row) => {
        if (row.length < 2) return;
        const slots = row.map((node) => node.position("x")).sort((a, b) => a - b);
        const order = row.slice().sort((a, b) => a.position("x") - b.position("x"));
        const inRow = new Set(order.map((node) => node.id()));
        const couples = [];
        cy.nodes("[kind = 'union']").forEach((union) => {
          const partners = union.incomers("node[kind = 'person']").filter((partner) => inRow.has(partner.id()));
          if (partners.length === 2) couples.push(partners.toArray());
        });
        for (let pass = 0; pass < 3; pass++) {
          let moved = false;
          couples.forEach(([first, second]) => {
            // Move whoever married in (no recorded parents) next to the partner born into the family.
            let [anchor, mover] = [first, second];
            if (!hasParents(anchor) && hasParents(mover)) [anchor, mover] = [mover, anchor];
            if (Math.abs(order.indexOf(anchor) - order.indexOf(mover)) === 1) return;
            moved = true;
            order.splice(order.indexOf(mover), 1);
            const at = order.indexOf(anchor);
            const right = order[at + 1];
            order.splice(right && partnersOf(anchor).has(right) ? at : at + 1, 0, mover);
          });
          if (!moved) break;
        }
        const paired = new Set(couples.flatMap(([a, b]) => [`${a.id()}|${b.id()}`, `${b.id()}|${a.id()}`]));
        const xs = slots.slice();
        for (let i = 0; i < order.length - 1; i++) {
          if (paired.has(`${order[i].id()}|${order[i + 1].id()}`)) {
            const middle = (xs[i] + xs[i + 1]) / 2;
            xs[i] = middle - gap / 2;
            xs[i + 1] = middle + gap / 2;
          }
        }
        for (let i = 1; i < xs.length; i++) xs[i] = Math.max(xs[i], xs[i - 1] + gap);
        const shift = (slots.reduce((sum, x) => sum + x, 0) - xs.reduce((sum, x) => sum + x, 0)) / xs.length;
        order.forEach((node, i) => node.position("x", xs[i] + shift));
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

    // Flatten couples for the network: partners link to each other and each parent links
    // straight to each child, so a person's neighbours are exactly their closest relatives.
    function networkElements(elements) {
      const nodes = [];
      const edges = [];
      const ids = new Set();
      const partners = new Map();
      const degree = new Map();
      const unionTypes = new Map();
      const link = (source, target, data) => {
        const id = `n-${source}-${target}`;
        if (ids.has(id) || ids.has(`n-${target}-${source}`)) return;
        ids.add(id);
        edges.push({ group: "edges", data: Object.assign({ id, source, target }, data) });
        [source, target].forEach((pid) => degree.set(pid, (degree.get(pid) || 0) + 1));
      };
      elements.forEach((element) => {
        const data = element.data;
        if (data.kind === "person") nodes.push({ group: "nodes", data: Object.assign({}, data) });
        if (data.kind === "union") unionTypes.set(data.id, data.type);
        if (data.kind === "partner") {
          if (!partners.has(data.target)) partners.set(data.target, []);
          partners.get(data.target).push(data.source);
        }
      });
      partners.forEach((pair, unionId) => {
        if (pair.length === 2) link(pair[0], pair[1], { kind: "partner", type: unionTypes.get(unionId) });
      });
      elements.forEach((element) => {
        const data = element.data;
        if (data.kind !== "child") return;
        (partners.get(data.source) || [data.source]).forEach((parent) => link(parent, data.target, { kind: "child", rtype: data.rtype }));
      });
      nodes.forEach((node) => {
        node.data.size = Math.round(Math.min(48, 14 + 6 * Math.sqrt(degree.get(node.data.id) || 0)));
      });
      return nodes.concat(edges);
    }

    // ---- Physics (network layout) -------------------------------------------

    function stopSimulation() {
      if (simulation) simulation.stop();
      simulation = null;
      simNodes = new Map();
    }

    function applyForces(sim) {
      const p = physics;
      sim
        .force("link")
        .distance((link) => (link.kind === "partner" ? Math.max(24, p.linkDistance * 0.45) : p.linkDistance))
        .strength((link) => Math.min(1, (link.kind === "partner" ? 1.8 : 1) * p.linkForce));
      sim.force("charge").strength(-p.repel * 17);
      sim.force("x").strength(p.centre * 0.15);
      sim
        .force("y")
        .y((d) => (p.generations ? d.generation * 120 : 0))
        .strength(p.generations ? 0.03 + p.centre * 0.2 : p.centre * 0.15);
    }

    function startSimulation() {
      return new Promise((resolve) => {
        stopSimulation();
        rows = [];
        drawBands();
        const spread = Math.sqrt(cy.nodes().length) * 60;
        const nodes = cy.nodes().map((node) => {
          const generation = node.data("generation") || 1;
          return { id: node.id(), node, r: node.data("size") / 2, generation, x: (Math.random() - 0.5) * spread, y: generation * 120 + (Math.random() - 0.5) * 40 };
        });
        simNodes = new Map(nodes.map((d) => [d.id, d]));
        const links = cy.edges().map((edge) => ({ source: edge.source().id(), target: edge.target().id(), kind: edge.data("kind") }));
        const sim = d3
          .forceSimulation(nodes)
          .force("link", d3.forceLink(links).id((d) => d.id))
          .force("charge", d3.forceManyBody().distanceMax(650))
          .force("collide", d3.forceCollide((d) => d.r + 10).strength(0.9))
          .force("x", d3.forceX(0))
          .force("y", d3.forceY())
          .alphaDecay(0.025);
        applyForces(sim);
        simulation = sim;

        // Settle most of the way straight away, so the first view is laid out even where animation
        // frames are paused (a background tab), then let the last of the movement play out live.
        sim.stop();
        for (let i = 0; i < 160 && sim.alpha() > 0.08; i++) sim.tick();
        const place = () => cy.batch(() => nodes.forEach((d) => d.node.grabbed() || d.node.position({ x: d.x, y: d.y })));
        placeNodes = place;
        place();
        cy.fit(cy.elements(), LAYOUT.padding);
        sim.on("tick", place);
        sim.alpha(Math.max(sim.alpha(), 0.12)).restart();
        resolve();
      });
    }

    cy.on("grab", "node[kind = 'person']", (event) => {
      const d = simNodes.get(event.target.id());
      if (!simulation || !d) return;
      d.fx = d.x;
      d.fy = d.y;
      simulation.alphaTarget(0.3).restart();
    });
    cy.on("drag", "node[kind = 'person']", (event) => {
      const d = simNodes.get(event.target.id());
      if (!d) return;
      const { x, y } = event.target.position();
      d.fx = x;
      d.fy = y;
    });
    cy.on("free", "node[kind = 'person']", (event) => {
      const d = simNodes.get(event.target.id());
      if (!simulation || !d) return;
      d.fx = null;
      d.fy = null;
      simulation.alphaTarget(0);
    });

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

    // ---- Close family (hover) ---------------------------------------------------

    const ROLE_WORDS = {
      parent: { M: "Father", F: "Mother", other: "Parent" },
      child: { M: "Son", F: "Daughter", other: "Child" },
      partner: { M: "Husband", F: "Wife", other: "Partner" },
      sibling: { M: "Brother", F: "Sister", other: "Sibling" },
    };

    function roleName(kind, node, detail) {
      const words = ROLE_WORDS[kind];
      const word = words[node.data("gender")] || words.other;
      if (kind === "partner") return detail === "partnership" ? "Partner" : word;
      if (detail === "half") return `Half-${word.toLowerCase()}`;
      if (detail === "step") return `Step${word.toLowerCase()}`;
      if (detail === "adopted") return `${kind === "parent" ? "Adoptive" : "Adopted"} ${word.toLowerCase()}`;
      if (detail === "foster") return `Foster ${word.toLowerCase()}`;
      return word;
    }

    // Works on both layouts: in the tree, couples meet at a union node; in the network, links are direct.
    function parentLinks(node) {
      const links = [];
      node.incomers("edge[kind = 'child']").forEach((edge) => {
        const source = edge.source();
        const rtype = edge.data("rtype");
        if (source.data("kind") === "union") {
          source.incomers("node[kind = 'person']").forEach((parent) => links.push({ node: parent, rtype, via: source }));
        } else {
          links.push({ node: source, rtype, via: null });
        }
      });
      return links;
    }

    function childLinks(node) {
      const links = node.outgoers("edge[kind = 'child']").map((edge) => ({ node: edge.target(), rtype: edge.data("rtype"), via: null }));
      node.outgoers("node[kind = 'union']").forEach((union) => {
        union.outgoers("edge[kind = 'child']").forEach((edge) => links.push({ node: edge.target(), rtype: edge.data("rtype"), via: union }));
      });
      return links;
    }

    function partnerLinks(node) {
      if (layoutMode === "network") {
        return node.connectedEdges("[kind = 'partner']").map((edge) => ({
          node: edge.source().same(node) ? edge.target() : edge.source(),
          type: edge.data("type"),
          via: null,
        }));
      }
      return node
        .outgoers("node[kind = 'union']")
        .map((union) => union.incomers("node[kind = 'person']").difference(node).map((partner) => ({ node: partner, type: union.data("type"), via: union })))
        .flat();
    }

    function birthParentIds(node) {
      const links = parentLinks(node);
      const biological = links.filter((link) => (link.rtype || "biological") === "biological");
      return new Set((biological.length ? biological : links).map((link) => link.node.id()));
    }

    // Parents, partners, children and siblings, each named relative to ``node``.
    function closeFamily(node) {
      const roles = new Map();
      let near = node;
      const add = (link, role) => {
        if (link.node.same(node) || roles.has(link.node.id())) return;
        roles.set(link.node.id(), role);
        near = near.union(link.node);
        if (link.via) near = near.union(link.via);
      };
      const parents = parentLinks(node);
      parents.forEach((link) => add(link, roleName("parent", link.node, link.rtype)));
      partnerLinks(node).forEach((link) => add(link, roleName("partner", link.node, link.type)));
      childLinks(node).forEach((link) => add(link, roleName("child", link.node, link.rtype)));

      const mine = birthParentIds(node);
      parents.forEach((parent) => {
        childLinks(parent.node).forEach((link) => {
          if (link.node.same(node) || roles.has(link.node.id())) return;
          const theirs = birthParentIds(link.node);
          const full = theirs.size === mine.size && [...theirs].every((id) => mine.has(id));
          add(link, roleName("sibling", link.node, full ? "" : "half"));
        });
      });
      return { near: near.union(near.edgesWith(near)), roles };
    }

    // Every ancestor and descendant, plus the person's partners.
    function lineOf(node) {
      if (layoutMode !== "network") {
        const unions = node.outgoers("node[kind = 'union']");
        return node
          .union(node.predecessors())
          .union(node.successors())
          .union(unions)
          .union(unions.connectedEdges())
          .union(unions.incomers("node[kind = 'person']"));
      }
      const climb = (step) => {
        let seen = node;
        let frontier = node;
        while (frontier.nonempty()) {
          frontier = step(frontier).difference(seen);
          seen = seen.union(frontier);
        }
        return seen;
      };
      const keep = climb((set) => set.incomers("edge[kind = 'child']").sources())
        .union(climb((set) => set.outgoers("edge[kind = 'child']").targets()))
        .union(node.connectedEdges("[kind = 'partner']").connectedNodes());
      return keep.union(keep.edgesWith(keep));
    }

    function siblingsOf(node) {
      let siblings = cy.collection();
      parentLinks(node).forEach((parent) => {
        childLinks(parent.node).forEach((link) => {
          if (!link.node.same(node)) siblings = siblings.union(link.node);
        });
      });
      return siblings;
    }

    // Double-clicking someone draws their brothers and sisters in around them: in the network by
    // pulling them together for a moment, in the tree (where rows are fixed) by framing the family.
    function gatherSiblings(node) {
      const siblings = siblingsOf(node);
      const count = siblings.length;
      if (!count) return { count };
      showNear(node);
      clearTimeout(gatherTimer);

      if (layoutMode !== "network" || !simulation) {
        cy.animate({ fit: { eles: node.union(siblings), padding: LAYOUT.padding } }, { duration: 500 });
        gatherTimer = setTimeout(clearNear, 2600);
        return { count };
      }

      const centre = simNodes.get(node.id());
      const pulled = siblings.map((person) => simNodes.get(person.id())).filter(Boolean);
      if (!centre || !pulled.length) return { count };
      const anchor = { x: centre.x, y: centre.y };
      simulation.force("gather", (alpha) => {
        pulled.forEach((d) => {
          d.vx += (anchor.x - d.x) * 0.35 * alpha;
          d.vy += (anchor.y - d.y) * 0.35 * alpha;
        });
        centre.vx += (anchor.x - centre.x) * 0.2 * alpha;
        centre.vy += (anchor.y - centre.y) * 0.2 * alpha;
      });
      simulation.alpha(0.6).alphaTarget(0.3).restart();
      if (document.hidden) {
        // No animation frames in a background tab, so settle it now instead.
        for (let i = 0; i < 90; i++) simulation.tick();
        placeNodes();
      }
      gatherTimer = setTimeout(() => {
        if (simulation) {
          simulation.force("gather", null);
          simulation.alphaTarget(0);
        }
        clearNear();
      }, 2400);
      return { count };
    }

    function clearHighlight() {
      cy.elements().removeClass("faded highlight");
    }

    function highlightLine(node) {
      clearHighlight();
      const keep = lineOf(node);
      cy.elements().not(keep).addClass("faded");
      keep.edges().addClass("highlight");
    }

    const clearNear = () =>
      cy.batch(() => {
        cy.elements().removeClass("dimmed near");
        cy.nodes("[role]").removeData("role");
      });
    function showNear(node) {
      const { near, roles } = closeFamily(node);
      cy.batch(() => {
        cy.elements().not(near).addClass("dimmed");
        near.addClass("near");
        roles.forEach((role, id) => cy.$id(id).data("role", role));
      });
    }

    let lastTap = { id: null, at: 0 };
    let lastGather = 0;

    function handleDoubleTap(node) {
      const now = Date.now();
      if (opts.mini || now - lastGather < 500) return;
      lastGather = now;
      lastTap = { id: null, at: 0 };
      const result = gatherSiblings(node);
      opts.onGather && opts.onGather(node.data(), result);
    }

    cy.on("tap", "node[kind = 'person']", (event) => {
      const node = event.target;
      const now = Date.now();
      if (!opts.mini && lastTap.id === node.id() && now - lastTap.at < 400) {
        handleDoubleTap(node);
        return;
      }
      lastTap = { id: node.id(), at: now };
      if (!opts.mini) highlightLine(node);
      opts.onSelect && opts.onSelect(node.data());
    });
    // Some builds emit their own double-tap event; the guard above keeps it from running twice.
    cy.on("dbltap", "node[kind = 'person']", (event) => handleDoubleTap(event.target));
    cy.on("tap", (event) => {
      if (event.target === cy) {
        clearHighlight();
        opts.onSelect && opts.onSelect(null);
      }
    });
    cy.on("mouseover", "node[kind = 'person']", (event) => {
      container.style.cursor = layoutMode === "network" ? "grab" : "pointer";
      showNear(event.target);
    });
    cy.on("mouseout", "node[kind = 'person']", () => {
      container.style.cursor = "";
      clearNear();
    });

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
      stopSimulation();
      cy.elements().remove();
      cy.add(data.elements);
      if (layoutMode === "network" && window.d3) {
        computeBranches();
        const branchOf = new Map(cy.nodes("[kind = 'person']").map((node) => [node.id(), node.scratch("_branch")]));
        cy.elements().remove();
        cy.add(networkElements(data.elements));
        cy.nodes().forEach((node) => {
          const index = branchOf.get(node.id());
          if (index !== undefined) node.scratch("_branch", index);
        });
        applyStyle();
        await startSimulation();
      } else {
        await runLayout();
      }
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
      setLayout(mode) {
        layoutMode = mode === "network" ? "network" : "tree";
        stopSimulation();
        cy.autoungrabify(layoutMode !== "network");
        applyStyle();
      },
      gather(pk) {
        const node = cy.$id(`p${pk}`);
        return node.nonempty() ? gatherSiblings(node) : { count: 0 };
      },
      setPhysics(values) {
        physics = Object.assign({}, PHYSICS_DEFAULTS, values);
        if (simulation) {
          applyForces(simulation);
          simulation.alpha(0.6).restart();
        }
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
    let gatherMessageTimer = 0;

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
      layout: config.layout === "network" ? "network" : "tree",
      physics: loadPhysics(),
      physicsControls: [
        { key: "centre", label: "Centre force", min: 0, max: 1, step: 0.01 },
        { key: "repel", label: "Repel force", min: 0, max: 20, step: 0.1 },
        { key: "linkForce", label: "Link force", min: 0, max: 1, step: 0.01 },
        { key: "linkDistance", label: "Link distance", min: 20, max: 300, step: 1 },
      ],
      branches: [],
      canEdit: config.canEdit,
      selected: null,
      panelOpen: false,
      controlsOpen: window.matchMedia("(min-width: 1024px)").matches,
      query: "",
      results: [],
      active: -1,
      searched: false,
      gathered: "",

      init() {
        graph = createGraph(this.$refs.canvas, {
          endpoint: config.endpoint,
          layout: config.layout,
          physics: Object.assign({}, this.physics),
          onGather: (person, result) => this.announceGather(person, result),
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
          if (this.rootId && !this.showAll) {
            graph.focus(this.rootId);
            // Open with the whole tree visible rather than dimming everyone outside their line.
            graph.clearHighlight();
          }
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
        if (this.layout === "network") url.searchParams.set("layout", "network");
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

      summaryLine(person) {
        return person ? [person.birthOrder, person.marital].filter(Boolean).join(" · ") : "";
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

      setLayout(mode) {
        if (mode === this.layout) return;
        this.layout = mode;
        graph.setLayout(mode);
        this.reload().then(() => {
          if (this.selected) graph.focus(this.selected.pk);
        });
      },

      announceGather(person, result) {
        const name = (person.name || person.label).split(" ")[0];
        this.gathered = result.count
          ? `Brought ${name}'s ${result.count} ${result.count === 1 ? "sibling" : "siblings"} closer.`
          : `No brothers or sisters are recorded for ${name}.`;
        clearTimeout(gatherMessageTimer);
        gatherMessageTimer = setTimeout(() => {
          this.gathered = "";
        }, 3200);
      },

      updatePhysics() {
        const values = JSON.parse(JSON.stringify(this.physics));
        graph.setPhysics(values);
        try {
          localStorage.setItem(PHYSICS_KEY, JSON.stringify(values));
        } catch (error) {
          // Private windows can refuse storage; the sliders still work for this visit.
        }
      },

      resetPhysics() {
        this.physics = Object.assign({}, PHYSICS_DEFAULTS);
        this.updatePhysics();
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
