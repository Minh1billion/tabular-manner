const NODE_W = 96, NODE_H = 40;
const COL_GAP = 150, ROW_GAP = 64;

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

const COMBINED_CODE = [
  "# Phase 1: structural check (cycle detection)",
  "function validate(graph):",
  "  color = {n: WHITE for n in graph}",
  "  for start in graph:",
  "    if color[start] == WHITE:",
  "      dfs(start)",
  "      # dfs marks GRAY on entry, BLACK on exit",
  "      # revisiting a GRAY node means a cycle",
  "",
  "# Phase 2: execution order (only if valid)",
  "function execute(graph):",
  "  ready = entry_nodes(graph)",
  "  completed = set()",
  "  while ready:",
  "    node = ready.pop_left()",
  "    run_node(node)",
  "    completed.add(node)",
  "    for next in graph.children(node):",
  "      if all(p in completed for p in parents(next)):",
  "        ready.append(next)",
  "  emit(completed)",
];

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
  spec.nodes.forEach(n => { nodes[n.id] = { type: n.type || "node" }; });
  return { nodes, edges };
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
      x: 30 + l * COL_GAP,
      y: 30 + rowCounters[l] * ROW_GAP,
    };
    rowCounters[l] += 1;
  });
  const maxLayer = Math.max(0, ...Object.values(layer));
  const maxRows = Math.max(1, ...Object.values(rowCounters));
  const viewW = 30 + (maxLayer + 1) * COL_GAP + 30;
  const viewH = 30 + maxRows * ROW_GAP + 20;
  return { positions, viewW, viewH };
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

  push1(2, "All nodes start WHITE.");
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
        push1(4, "'" + node + "' -> GRAY (on the current path).", node);
      }
      let advanced = false;
      for (const next of children(graph, node)) {
        if (color[next] === "WHITE") {
          edgeStates[edgeKey(node, next)] = "traversed";
          stack.push(next);
          push1(5, "Descend into '" + next + "' (WHITE).", next);
          advanced = true;
          break;
        }
        if (color[next] === "GRAY") {
          edgeStates[edgeKey(node, next)] = "cycle";
          const path = [...stack, next];
          push1(7, "'" + next + "' is GRAY and still on the stack.", node, path);
          steps.push({
            line: 7,
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
      push1(3, "'" + node + "' has no unvisited children -> BLACK.", node);
      stack.pop();
    }
  }
  if (cycleResult) return { code: COMBINED_CODE, steps };

  push1(6, "No cycle found. Graph is valid, structural check complete.");

  let ready = ids.filter(id => parents(graph, id).length === 0);
  const completed = new Set();
  ids.forEach(id => nodeStates[id] = "idle");
  const push2 = (line, note, activeId) => {
    ready.forEach(id => { if (!completed.has(id)) nodeStates[id] = "in-queue"; });
    steps.push({
      line, note, activeId,
      nodeStates: { ...nodeStates },
      edgeStates: { ...edgeStates },
      queue: [...ready],
      visited: [...completed],
      inspector: activeId ? { id: activeId, type: graph.nodes[activeId].type } : null,
    });
  };
  push2(11, "Entry nodes have no parents -> first in the ready queue.");
  while (ready.length > 0) {
    const node = ready.shift();
    nodeStates[node] = "active";
    push2(14, "Run node '" + node + "'.", node);
    completed.add(node);
    nodeStates[node] = "done";
    push2(15, "'" + node + "' completed.", node);
    for (const next of children(graph, node)) {
      edgeStates[edgeKey(node, next)] = "traversed";
      if (parents(graph, next).every(p => completed.has(p))) {
        ready.push(next);
        push2(18, "All parents of '" + next + "' are done -> ready to run.", node);
      }
    }
  }
  push2(19, "All nodes finished -> execution complete.");
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

  graph.edges.forEach(([a, b]) => {
    const pa = layout.positions[a], pb = layout.positions[b];
    const x1 = pa.x + NODE_W, y1 = pa.y + NODE_H / 2;
    const x2 = pb.x, y2 = pb.y + NODE_H / 2;
    const line = document.createElementNS(ns, "line");
    line.setAttribute("x1", x1); line.setAttribute("y1", y1);
    line.setAttribute("x2", x2); line.setAttribute("y2", y2);
    const state = step ? step.edgeStates[edgeKey(a, b)] : "idle";
    line.setAttribute("class", "edge-line" + (state === "traversed" ? " traversed" : state === "cycle" ? " cycle" : ""));
    svg.appendChild(line);
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

function renderCode(container, code, activeLine) {
  container.innerHTML = "";
  code.forEach((line, i) => {
    const div = document.createElement("div");
    div.className = "code-line" + (i === activeLine ? " active" : line.startsWith("#") ? " dim" : "");
    div.textContent = line;
    container.appendChild(div);
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
document.getElementById("btnRun").addEventListener("click", runGraph);
document.getElementById("speed").addEventListener("input", updateSpeedLabel);
updateSpeedLabel();

document.getElementById("graphInput").value = JSON.stringify(DEFAULT_GRAPH, null, 2);
runGraph();