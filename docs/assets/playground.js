const NODE_W = 96, NODE_H = 40;
const COL_GAP = 130, ROW_GAP = 90;

// "join" preset below reuses this same object as the default graph on page load
const DEFAULT_GRAPH = {
  nodes: [
    { id: "src", type: "fetch_internal" },
    { id: "a", type: "select" },
    { id: "b", type: "select" },
    { id: "join", type: "join" },
    { id: "sink", type: "push_internal" }
  ],
  connections: [
    { from: "src", to: "a" },
    { from: "src", to: "b" },
    { from: "a", to: "join" },
    { from: "b", to: "join" },
    { from: "join", to: "sink" }
  ]
};

// Presets shown as chips above the graph input, roughly simple -> complex
const GRAPH_PRESETS = {
  chain: {
    nodes: [
      { id: "src", type: "fetch_internal" },
      { id: "clean", type: "select" },
      { id: "sink", type: "push_internal" }
    ],
    connections: [
      { from: "src", to: "clean" },
      { from: "clean", to: "sink" }
    ]
  },
  fanout: {
    nodes: [
      { id: "src", type: "fetch_internal" },
      { id: "a", type: "select" },
      { id: "b", type: "filter" },
      { id: "sinkA", type: "push_internal" },
      { id: "sinkB", type: "push_internal" }
    ],
    connections: [
      { from: "src", to: "a" },
      { from: "src", to: "b" },
      { from: "a", to: "sinkA" },
      { from: "b", to: "sinkB" }
    ]
  },
  join: DEFAULT_GRAPH,
  union3: {
    nodes: [
      { id: "s1", type: "fetch_internal" },
      { id: "s2", type: "fetch_internal" },
      { id: "s3", type: "fetch_internal" },
      { id: "merge", type: "union" },
      { id: "sink", type: "push_internal" }
    ],
    connections: [
      { from: "s1", to: "merge" },
      { from: "s2", to: "merge" },
      { from: "s3", to: "merge" },
      { from: "merge", to: "sink" }
    ]
  },
  chained: {
    nodes: [
      { id: "src", type: "fetch_internal" },
      { id: "a", type: "select" },
      { id: "b", type: "filter" },
      { id: "join1", type: "join" },
      { id: "c", type: "derive" },
      { id: "d", type: "select" },
      { id: "join2", type: "join" },
      { id: "sink", type: "push_internal" }
    ],
    connections: [
      { from: "src", to: "a" },
      { from: "src", to: "b" },
      { from: "a", to: "join1" },
      { from: "b", to: "join1" },
      { from: "join1", to: "c" },
      { from: "join1", to: "d" },
      { from: "c", to: "join2" },
      { from: "d", to: "join2" },
      { from: "join2", to: "sink" }
    ]
  },
  cycle: {
    nodes: [
      { id: "src", type: "fetch_internal" },
      { id: "a", type: "select" },
      { id: "b", type: "filter" },
      { id: "c", type: "derive" }
    ],
    connections: [
      { from: "src", to: "a" },
      { from: "a", to: "b" },
      { from: "b", to: "c" },
      { from: "c", to: "a" }
    ]
  }
};

const COMBINED_CODE = [
  "function validate(graph):",
  "  check_node_types(graph)",
  "  check_connections(graph)",
  "  check_entry_exists(graph)",
  "  color = {node: WHITE for node in graph}",
  "  color[node] = BLACK   # fully explored, backtrack",
  "  color[node] = GRAY   # entered, now on this path",
  "  visit(child)   # step into each unvisited child",
  "  # every reachable node visited, no repeats -> valid",
  "  if color[child] == GRAY: raise CycleError",
  "  for node in graph.nodes:",
  "    node.operator.validate()   # Operator checks its own params",
  "    check_ports(node, node.operator.valid_ports())",
  "",
  "function run_node(node, source, plan):",
  "  if node.fan_in == false:",
  "    return node.operator.forward(plan)   # hand off to the Operator",
  "  node.buffer[source] = plan",
  "  if len(node.buffer) < node.in_degree:",
  "    return NONE   # still waiting on another branch",
  "  return node.operator.forward_many(node.buffer)   # every branch arrived",
  "",
  "function execute(graph):",
  "  queue = [(n, NONE, initial_plan) for n in entry_nodes(graph)]",
  "  while queue:",
  "    (node, source, plan) = queue.pop_left()",
  "    result = run_node(node, source, plan)",
  "    if result == NONE:",
  "      continue",
  "    (new_plan, next_nodes) = result   # the Operator's output",
  "    for next in graph.children(node):",
  "      queue.append((next, node, new_plan))",
];

const FAN_IN_TYPES = ["join", "union", "merge"];

function parseGraph(text) {
  let spec;
  try {
    spec = JSON.parse(text);
  } catch (e) {
    throw new Error("Invalid JSON: " + e.message);
  }
  if (!spec.nodes || !Array.isArray(spec.nodes)) {
    throw new Error("Missing 'nodes' array");
  }
  const conns = spec.connections || spec.edges || [];
  if (!Array.isArray(conns)) {
    throw new Error("'connections' must be an array");
  }
  const ids = new Set();
  spec.nodes.forEach(n => {
    if (!n.id) throw new Error("Every node needs an 'id'");
    if (ids.has(n.id)) throw new Error("Duplicate node id '" + n.id + "'");
    ids.add(n.id);
  });
  const edges = conns.map(c => {
    const from = c.from, to = c.to;
    if (!ids.has(from)) throw new Error("Connection 'from' unknown id '" + from + "'");
    if (!ids.has(to)) throw new Error("Connection 'to' unknown id '" + to + "'");
    return [from, to];
  });
  const nodes = {};
  spec.nodes.forEach(n => {
    nodes[n.id] = { type: n.type || "node", fanIn: FAN_IN_TYPES.includes(n.type) };
  });
  const graph = { nodes, edges };
  ids.forEach(id => { graph.nodes[id].inDegree = parents(graph, id).length || 1; });
  return graph;
}

function children(graph, id) {
  return graph.edges.filter(e => e[0] === id).map(e => e[1]);
}
function parents(graph, id) {
  return graph.edges.filter(e => e[1] === id).map(e => e[0]);
}
function edgeKey(a, b) { return a + "->" + b; }

function computeLayout(graph) {
  const ids = Object.keys(graph.nodes);
  const inDegree = {};
  ids.forEach(id => inDegree[id] = parents(graph, id).length);
  const layer = {};
  let queue = ids.filter(id => inDegree[id] === 0);
  queue.forEach(id => layer[id] = 0);
  const remaining = new Set(ids);
  const localIn = { ...inDegree };
  while (queue.length > 0) {
    const node = queue.shift();
    remaining.delete(node);
    for (const next of children(graph, node)) {
      layer[next] = Math.max(layer[next] || 0, layer[node] + 1);
      localIn[next] -= 1;
      if (localIn[next] === 0) queue.push(next);
    }
  }
  let extraLayer = (Math.max(0, ...Object.values(layer)) || 0) + 1;
  remaining.forEach(id => { layer[id] = extraLayer; extraLayer += 1; });

  const rowCounters = {};
  const positions = {};
  ids.forEach(id => {
    const l = layer[id] || 0;
    rowCounters[l] = (rowCounters[l] || 0);
    positions[id] = {
      x: 30 + rowCounters[l] * COL_GAP,
      y: 30 + l * ROW_GAP,
    };
    rowCounters[l] += 1;
  });
  const maxLayer = Math.max(0, ...Object.values(layer));
  const maxRows = Math.max(1, ...Object.values(rowCounters));

  // An edge whose target sits at the same layer or above its source can't be drawn as a
  // simple downward arrow - this is exactly what a cycle's back-edge looks like, and drawing
  // it as a straight line just overlaps the forward edges below it and disappears. Flag these
  // so renderGraph bows them out to the side instead.
  const backEdgeSet = new Set();
  graph.edges.forEach(([a, b]) => {
    if (positions[b].y <= positions[a].y) backEdgeSet.add(edgeKey(a, b));
  });
  const rightEdge = Math.max(...Object.values(positions).map(p => p.x + NODE_W));
  const bulgeExtra = backEdgeSet.size ? 60 + (backEdgeSet.size - 1) * 34 + 30 : 0;

  const viewW = Math.max(30 + maxRows * COL_GAP + 30, rightEdge + 30) + bulgeExtra;
  const viewH = 30 + (maxLayer + 1) * ROW_GAP + 20;
  return { positions, viewW, viewH, backEdgeSet, rightEdge };
}

function genSteps(graph) {
  const ids = Object.keys(graph.nodes);
  const color = {};
  ids.forEach(id => color[id] = "WHITE");
  const stack = [];
  const nodeStates = {};
  ids.forEach(id => nodeStates[id] = "idle");
  const edgeStates = {};
  graph.edges.forEach(([a, b]) => edgeStates[edgeKey(a, b)] = "idle");

  const colorToState = c => c === "WHITE" ? "idle" : c === "GRAY" ? "in-queue" : "done";
  const steps = [];
  const push1 = (line, note, activeId, path) => {
    ids.forEach(id => nodeStates[id] = colorToState(color[id]));
    if (activeId) nodeStates[activeId] = "active";
    steps.push({
      line, note, activeId,
      nodeStates: { ...nodeStates },
      edgeStates: { ...edgeStates },
      queue: [...stack],
      visited: ids.filter(id => color[id] === "BLACK"),
      inspector: activeId ? { id: activeId, type: graph.nodes[activeId].type, color: color[activeId] } : null,
      path: path || [...stack],
    });
  };

  push1(4, "All nodes start WHITE.");
  let cycleResult = null;
  for (const start of ids) {
    if (cycleResult) break;
    if (color[start] !== "WHITE") continue;
    stack.push(start);
    outer:
    while (stack.length > 0) {
      const node = stack[stack.length - 1];
      if (color[node] === "WHITE") {
        color[node] = "GRAY";
        push1(6, "'" + node + "' -> GRAY (on the current path).", node);
      }
      let advanced = false;
      for (const next of children(graph, node)) {
        if (color[next] === "WHITE") {
          edgeStates[edgeKey(node, next)] = "traversed";
          stack.push(next);
          push1(7, "Descend into '" + next + "' (WHITE).", next);
          advanced = true;
          break;
        }
        if (color[next] === "GRAY") {
          edgeStates[edgeKey(node, next)] = "cycle";
          const path = [...stack, next];
          push1(9, "'" + next + "' is GRAY and still on the stack.", node, path);
          steps.push({
            line: 9,
            note: "Cycle detected: " + path.join(" -> ") + ". Graph is invalid, execution order is not computed.",
            warn: true,
            activeId: node,
            nodeStates: { ...nodeStates },
            edgeStates: { ...edgeStates },
            queue: [...stack],
            visited: ids.filter(id => color[id] === "BLACK"),
            inspector: { id: node, type: graph.nodes[node].type, color: color[node] },
            path,
            cycleFound: true,
          });
          cycleResult = true;
          break outer;
        }
      }
      if (cycleResult) break;
      if (advanced) continue outer;
      color[node] = "BLACK";
      push1(5, "'" + node + "' has no unvisited children -> BLACK.", node);
      stack.pop();
    }
  }
  if (cycleResult) return { code: COMBINED_CODE, steps };

  push1(8, "No cycle found. Graph structure is valid.");
  for (const id of ids) {
    push1(11, "'" + id + "'.operator.validate() checks its required/optional params.", id);
    push1(12, "'" + id + "'.operator.valid_ports() checked against its outgoing connections.", id);
  }

  let queue = ids.filter(id => parents(graph, id).length === 0).map(id => [id, null]);
  const buffer = {};
  ids.forEach(id => buffer[id] = {});
  const completed = new Set();
  ids.forEach(id => nodeStates[id] = "idle");
  const push2 = (line, note, activeId) => {
    queue.forEach(([id]) => { if (nodeStates[id] !== "done") nodeStates[id] = "in-queue"; });
    steps.push({
      line, note, activeId,
      nodeStates: { ...nodeStates },
      edgeStates: { ...edgeStates },
      queue: queue.map(q => q[0]),
      visited: [...completed],
      inspector: activeId ? {
        id: activeId,
        type: graph.nodes[activeId].type,
        fan_in: graph.nodes[activeId].fanIn,
        in_degree: graph.nodes[activeId].inDegree,
        buffer: Object.keys(buffer[activeId]).join(",") || "-",
      } : null,
    });
  };

  push2(23, "Entry nodes go straight into the queue.");
  while (queue.length > 0) {
    const [node, source] = queue.shift();
    nodeStates[node] = "active";
    push2(25, "Pop '" + node + "' from the queue.", node);
    push2(26, "call run_node('" + node + "').", node);

    if (graph.nodes[node].fanIn) {
      buffer[node][source] = true;
      if (Object.keys(buffer[node]).length < graph.nodes[node].inDegree) {
        nodeStates[node] = "waiting";
        push2(19, "'" + node + "' buffer incomplete -> return NONE, wait for more input.", node);
        continue;
      }
      push2(20, "'" + node + "' buffer full -> operator.forward_many() runs.", node);
    } else {
      push2(16, "'" + node + "' -> operator.forward() runs.", node);
    }

    completed.add(node);
    nodeStates[node] = "done";
    push2(29, "'" + node + "' forwarded, result ready.", node);

    for (const next of children(graph, node)) {
      edgeStates[edgeKey(node, next)] = "traversed";
      queue.push([next, node]);
      push2(31, "Queue '" + next + "', source='" + node + "'.", node);
    }
  }
  push2(24, "Queue empty -> execution complete.");
  return { code: COMBINED_CODE, steps };
}

let currentGraph = null;
let currentLayout = null;
let currentSteps = [];
let stepIndex = 0;
let playing = false;
let timer = null;

function renderGraph(svg, graph, layout, step) {
  svg.querySelectorAll(".edge-line, .node-box, .node-label").forEach(el => el.remove());
  svg.setAttribute("viewBox", "0 0 " + layout.viewW + " " + layout.viewH);
  const ns = svg.namespaceURI;

  let backIdx = 0;
  graph.edges.forEach(([a, b]) => {
    const pa = layout.positions[a], pb = layout.positions[b];
    const state = step ? step.edgeStates[edgeKey(a, b)] : "idle";
    const stateClass = state === "traversed" ? " traversed" : state === "cycle" ? " cycle" : "";

    if (!layout.backEdgeSet.has(edgeKey(a, b))) {
      const x1 = pa.x + NODE_W / 2, y1 = pa.y + NODE_H;
      const x2 = pb.x + NODE_W / 2, y2 = pb.y;
      const line = document.createElementNS(ns, "line");
      line.setAttribute("x1", x1); line.setAttribute("y1", y1);
      line.setAttribute("x2", x2); line.setAttribute("y2", y2);
      line.setAttribute("class", "edge-line" + stateClass);
      svg.appendChild(line);
      return;
    }

    // Back-edge (this is what a cycle looks like): bow it out to the right, clear of the
    // node column, instead of drawing it straight where it would sit on top of - and be
    // hidden by - the forward edges.
    const x1 = pa.x + NODE_W, y1 = pa.y + NODE_H / 2;
    const x2 = pb.x + NODE_W, y2 = pb.y + NODE_H / 2;
    const ctrlX = layout.rightEdge + 40 + backIdx * 34;
    backIdx += 1;
    const path = document.createElementNS(ns, "path");
    path.setAttribute("d", `M ${x1} ${y1} C ${ctrlX} ${y1} ${ctrlX} ${y2} ${x2} ${y2}`);
    path.setAttribute("class", "edge-line edge-back" + stateClass);
    svg.appendChild(path);
  });

  Object.keys(graph.nodes).forEach(id => {
    const n = layout.positions[id];
    const state = step ? step.nodeStates[id] : "idle";
    const textColor = (state === "active" || state === "done" || state === "error") ? "#fff" : "#343A3C";
    const rect = document.createElementNS(ns, "rect");
    rect.setAttribute("x", n.x); rect.setAttribute("y", n.y);
    rect.setAttribute("width", NODE_W); rect.setAttribute("height", NODE_H);
    rect.setAttribute("rx", 8);
    rect.setAttribute("class", "node-box" + (state !== "idle" ? " " + state : ""));
    svg.appendChild(rect);

    const label = document.createElementNS(ns, "text");
    label.setAttribute("x", n.x + NODE_W / 2);
    label.setAttribute("y", n.y + NODE_H / 2 - 3);
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("class", "node-label");
    label.setAttribute("fill", textColor);
    label.textContent = id;
    svg.appendChild(label);

    const sub = document.createElementNS(ns, "text");
    sub.setAttribute("x", n.x + NODE_W / 2);
    sub.setAttribute("y", n.y + NODE_H / 2 + 12);
    sub.setAttribute("text-anchor", "middle");
    sub.setAttribute("class", "node-label");
    sub.setAttribute("fill", textColor);
    sub.setAttribute("font-size", "9");
    sub.setAttribute("font-weight", "400");
    sub.textContent = graph.nodes[id].type;
    svg.appendChild(sub);
  });
}

const KEYWORDS = ["function", "if", "else", "while", "for", "in", "return", "continue"];
const CONSTANTS = ["NONE", "WHITE", "GRAY", "BLACK"];
const VOCAB = { node: "tok-node", graph: "tok-graph", plan: "tok-plan" };

function highlight(line) {
  return line.replace(/[A-Za-z_][A-Za-z0-9_]*/g, (w, i) => {
    if (KEYWORDS.includes(w)) return "<span class=\"tok-key\">" + w + "</span>";
    if (CONSTANTS.includes(w)) return "<span class=\"tok-const\">" + w + "</span>";
    if (VOCAB[w]) return "<span class=\"" + VOCAB[w] + "\">" + w + "</span>";
    if (line[i + w.length] === "(") return "<span class=\"tok-fn\">" + w + "</span>";
    return w;
  });
}

function renderCode(container, code, activeLine) {
  container.innerHTML = "";
  let box = null;
  code.forEach((line, i) => {
    if (line === "") {
      box = null;
      return;
    }
    if (!box) {
      box = document.createElement("div");
      box.className = "code-box";
      container.appendChild(box);
    }
    const div = document.createElement("div");
    const isComment = line.trim().startsWith("#");
    div.className = "code-line" + (i === activeLine ? " active" : "");
    if (isComment) {
      div.innerHTML = "<span class=\"tok-com\">" + line + "</span>";
    } else {
      const hashIndex = line.indexOf("#");
      if (hashIndex === -1) {
        div.innerHTML = highlight(line);
      } else {
        div.innerHTML = highlight(line.slice(0, hashIndex)) + "<span class=\"tok-com\">" + line.slice(hashIndex) + "</span>";
      }
    }
    box.appendChild(div);
  });
}

function renderQueueWidget(step) {
  const row = document.getElementById("queueRow");
  row.innerHTML = "";
  (step.queue || []).forEach(id => {
    const el = document.createElement("div");
    el.className = "queue-item";
    el.textContent = id;
    row.appendChild(el);
  });
  const visited = document.getElementById("visitedRow");
  visited.innerHTML = "";
  (step.visited || []).forEach(id => {
    const el = document.createElement("div");
    el.className = "visited-dot";
    el.textContent = id;
    visited.appendChild(el);
  });
}

function renderInspector(step) {
  const body = document.getElementById("inspectorBody");
  body.innerHTML = "";
  if (step.inspector) {
    Object.entries(step.inspector).forEach(([k, v]) => {
      const div = document.createElement("div");
      div.className = "inspector-field";
      div.innerHTML = "<span class=\"k\">" + k + "</span><span class=\"v\">" + v + "</span>";
      body.appendChild(div);
    });
  } else {
    body.innerHTML = "<div class=\"inspector-field\"><span class=\"k\">Status</span><span class=\"v\">-</span></div>";
  }
  if (step.path && step.path.length > 0) {
    const trace = document.createElement("div");
    trace.className = "path-trace";
    step.path.forEach((id, i) => {
      if (i > 0) {
        const arrow = document.createElement("span");
        arrow.className = "path-arrow";
        arrow.textContent = "->";
        trace.appendChild(arrow);
      }
      const box = document.createElement("span");
      box.className = "path-node";
      box.textContent = id;
      trace.appendChild(box);
    });
    body.appendChild(trace);
  }
  if (step.note) {
    const note = document.createElement("div");
    note.className = "note-box" + (step.warn ? " warn" : "");
    note.textContent = step.note;
    body.appendChild(note);
  }
}

function renderStep() {
  const step = currentSteps[stepIndex];
  renderGraph(document.getElementById("graphCanvas"), currentGraph, currentLayout, step);
  renderCode(document.getElementById("pseudocode"), COMBINED_CODE, step.line);
  renderQueueWidget(step);
  renderInspector(step);
  document.getElementById("stepLabel").textContent = "Step " + (stepIndex + 1) + " / " + currentSteps.length;
}

function setControlsEnabled(enabled) {
  document.getElementById("btnPrev").disabled = !enabled;
  document.getElementById("btnPlay").disabled = !enabled;
  document.getElementById("btnNext").disabled = !enabled;
}

function runGraph() {
  pause();
  const text = document.getElementById("graphInput").value;
  const errorEl = document.getElementById("inputError");
  try {
    const graph = parseGraph(text);
    if (Object.keys(graph.nodes).length === 0) throw new Error("Graph has no nodes");
    currentGraph = graph;
    currentLayout = computeLayout(graph);
    const result = genSteps(graph);
    currentSteps = result.steps;
    stepIndex = 0;
    errorEl.textContent = "";
    setControlsEnabled(true);
    renderStep();
  } catch (e) {
    errorEl.textContent = e.message;
    setControlsEnabled(false);
  }
}

function goTo(i) {
  stepIndex = Math.max(0, Math.min(currentSteps.length - 1, i));
  renderStep();
}

function play() {
  if (currentSteps.length === 0) return;
  playing = true;
  document.getElementById("btnPlay").textContent = "Pause";
  const speed = () => 2300 - Number(document.getElementById("speed").value);
  const loopEl = document.getElementById("loopToggle");
  const tick = () => {
    if (stepIndex >= currentSteps.length - 1) {
      if (loopEl && loopEl.checked) {
        goTo(0);
        timer = setTimeout(tick, speed());
        return;
      }
      pause();
      return;
    }
    goTo(stepIndex + 1);
    timer = setTimeout(tick, speed());
  };
  timer = setTimeout(tick, speed());
}
function pause() {
  playing = false;
  document.getElementById("btnPlay").textContent = "Play";
  clearTimeout(timer);
}

function updateSpeedLabel() {
  const el = document.getElementById("speedLabel");
  if (!el) return;
  const delay = 2300 - Number(document.getElementById("speed").value);
  el.textContent = delay + "ms/step";
}

document.getElementById("btnPrev").addEventListener("click", () => { pause(); goTo(stepIndex - 1); });
document.getElementById("btnNext").addEventListener("click", () => { pause(); goTo(stepIndex + 1); });
document.getElementById("btnPlay").addEventListener("click", () => playing ? pause() : play());
document.getElementById("graphInput").addEventListener("input", runGraph);
document.getElementById("speed").addEventListener("input", updateSpeedLabel);
updateSpeedLabel();

document.querySelectorAll(".preset-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    const preset = GRAPH_PRESETS[btn.getAttribute("data-preset")];
    if (!preset) return;
    document.querySelectorAll(".preset-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("graphInput").value = JSON.stringify(preset, null, 2);
    runGraph();
  });
});
document.getElementById("graphInput").addEventListener("input", () => {
  document.querySelectorAll(".preset-btn").forEach(b => b.classList.remove("active"));
});

document.getElementById("graphInput").value = JSON.stringify(DEFAULT_GRAPH, null, 2);
runGraph();

const pgLegend = document.getElementById("pgLegend");
const pgLegendToggle = document.getElementById("pgLegendToggle");
if (pgLegend && pgLegendToggle) {
  pgLegendToggle.addEventListener("click", () => {
    const collapsed = pgLegend.classList.toggle("collapsed");
    pgLegendToggle.setAttribute("aria-expanded", String(!collapsed));
  });
}