(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const parts = new Map(window.PARTS.map((p) => [p.slug, p]));

  let current = null;   // selected part
  let stlFile = null;   // last STL produced (what the viewer shows)
  let sliceFile = null; // what the slicer should chew on: STL, or the
                        // multicolour project when the part has one
  let sliced = null;    // last sliced file
  let mappings = null;  // IFS channel map for a multi-colour job

  // ---------------------------------------------------------------- viewer

  const viewer = (() => {
    const host = $("viewer");
    const hint = document.createElement("div");
    hint.className = "hint";
    hint.textContent = "Aquí verás la pieza cuando la generes";
    host.appendChild(hint);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x101217);

    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    host.appendChild(renderer.domElement);

    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    scene.add(new THREE.HemisphereLight(0xffffff, 0x202430, 1.1));
    const key = new THREE.DirectionalLight(0xffffff, 0.75);
    key.position.set(1, 1, 1);
    scene.add(key);

    let mesh = null;
    let grid = null;

    const resize = () => {
      const w = host.clientWidth;
      const h = host.clientHeight;
      if (!w || !h) return;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h, false);
    };
    window.addEventListener("resize", resize);
    resize();

    (function animate() {
      requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    })();

    return {
      load(url) {
        new THREE.STLLoader().load(url, (geometry) => {
          if (mesh) {
            scene.remove(mesh);
            mesh.geometry.dispose();
            mesh.material.dispose();
          }
          if (grid) scene.remove(grid);
          hint.remove();

          geometry.computeBoundingBox();
          geometry.center();

          mesh = new THREE.Mesh(
            geometry,
            new THREE.MeshStandardMaterial({
              color: 0xe8893a,
              roughness: 0.55,
              metalness: 0.05,
            })
          );
          // STL is Z-up, three.js is Y-up.
          mesh.rotation.x = -Math.PI / 2;
          scene.add(mesh);

          const size = geometry.boundingBox.getSize(new THREE.Vector3());
          const span = Math.max(size.x, size.y, size.z) || 10;

          grid = new THREE.GridHelper(
            Math.ceil((span * 2.2) / 10) * 10, 20, 0x3a4150, 0x252a33
          );
          grid.position.y = -size.z / 2;
          scene.add(grid);

          camera.position.set(span * 1.1, span * 0.95, span * 1.4);
          controls.target.set(0, 0, 0);
          controls.update();
          resize();
        });
      },
    };
  })();

  // ------------------------------------------------------------------ form

  function fieldFor(param) {
    const wrap = document.createElement("div");
    wrap.className = param.kind === "bool" ? "field check" : "field";

    const label = document.createElement("label");
    label.textContent = param.label;
    label.htmlFor = "f-" + param.name;

    const row = document.createElement("div");
    row.className = "row";

    const input = document.createElement("input");
    input.id = "f-" + param.name;
    input.name = param.name;
    input.dataset.kind = param.kind;

    if (param.kind === "bool") {
      input.type = "checkbox";
      input.checked = Boolean(param.default);
      row.append(input, label);
      wrap.append(row);
      return wrap;
    }

    if (param.kind === "choice") {
      const select = document.createElement("select");
      select.id = input.id;
      select.name = param.name;
      select.dataset.kind = "choice";
      (param.options || []).forEach((opt) => {
        const option = document.createElement("option");
        option.value = opt;
        option.textContent = opt;
        option.selected = opt === param.default;
        select.append(option);
      });
      row.append(select);
      wrap.append(label, row);
      return wrap;
    }

    if (param.kind === "text") {
      input.type = "text";
      input.value = param.default;
    } else {
      input.type = "number";
      input.value = param.default;
      input.step = param.step;
      if (param.min !== null) input.min = param.min;
      if (param.max !== null) input.max = param.max;
    }

    const unit = document.createElement("span");
    unit.className = "unit";
    unit.textContent = param.unit || "";

    row.append(input, unit);
    wrap.append(label, row);
    return wrap;
  }

  function select(slug) {
    current = parts.get(slug);
    if (!current) return;

    document.querySelectorAll(".part").forEach((b) =>
      b.setAttribute("aria-current", String(b.dataset.slug === slug))
    );

    $("empty-state").hidden = true;
    $("params").hidden = false;
    $("part-name").textContent = current.name;
    $("part-notes").textContent = current.notes || current.description;

    $("fields").replaceChildren(...current.params.map(fieldFor));
  }

  function readValues() {
    const values = {};
    $("fields").querySelectorAll("input, select").forEach((field) => {
      values[field.name] =
        field.dataset.kind === "bool" ? field.checked : field.value;
    });
    return values;
  }

  // ----------------------------------------------------------------- calls

  function say(text, kind) {
    const line = $("status-line");
    line.textContent = text;
    line.style.color =
      kind === "err" ? "#f0a9a9" : kind === "ok" ? "#8fd3ae" : "";
  }

  async function call(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "Error " + response.status);
    return data;
  }

  async function withBusy(button, label, task) {
    const original = button.textContent;
    button.disabled = true;
    button.textContent = label;
    try {
      await task();
    } catch (error) {
      say(error.message, "err");
    } finally {
      button.textContent = original;
      button.disabled = false;
    }
  }

  $("params").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.submitter || event.target.querySelector("button");

    await withBusy(button, "Generando…", async () => {
      const data = await call("/api/build", {
        slug: current.slug,
        values: readValues(),
      });

      stlFile = data.file;
      sliceFile = data.slice_file || data.file;
      partNames = data.parts || [];
      sliced = null;
      mappings = null;
      $("ifs").hidden = true;

      $("result").hidden = false;
      $("r-size").textContent = data.size;
      $("r-volume").textContent = data.volume_cm3 + " cm³";
      $("r-file").textContent = data.file;
      $("a-download").href = data.url;
      $("a-download").textContent = "Descargar STL";

      $("warnings").replaceChildren(
        ...data.warnings.map((text) => {
          const div = document.createElement("div");
          div.className = "alert alert--warn";
          div.textContent = text;
          return div;
        })
      );

      $("r-time").textContent = window.SLICER_READY ? "calculando…" : "—";
      updateSendButtons();
      viewer.load(data.url);
      const colores = (data.parts || []).length;
      say(
        window.SLICER_READY
          ? "Pieza generada" + (colores > 1 ? " en " + colores + " colores" : "") +
            ". Calculando cuánto tarda en imprimirse…"
          : "STL listo. Descárgalo y ábrelo en Orca para laminar.",
        "ok"
      );
    });

    // The real figure comes from the slicer, and it only takes a few seconds,
    // so do it without making the user ask.
    if (stlFile && window.SLICER_READY) await laminar();
  });

  async function laminar() {
    if (!sliceFile) return;
    await withBusy($("a-slice"), "Calculando tiempo…", async () => {
      const material = $("material");
      const quality = $("quality");
      const data = await call("/api/slice", {
        file: sliceFile,
        material: material ? material.value : undefined,
        quality: quality ? quality.value : undefined,
      });
      sliced = data.file;
      updateSendButtons();
      await loadGcodeInfo(sliced);
      const bits = [data.layers ? data.layers + " capas" : null,
                    data.filament_cm3 ? data.filament_cm3 + " cm³" : null,
                    data.estimate ? data.estimate : null].filter(Boolean);
      $("r-time").textContent = data.estimate || "—";
      say("Listo: " + bits.join(" · ") + ". Ya puedes mandarlo a la impresora.", "ok");
    });
  }

  $("a-slice").addEventListener("click", laminar);

  async function send(printNow) {
    if (!sliced) return;
    if (!flagClashes()) return;
    const button = printNow ? $("a-print") : $("a-send");
    await withBusy(button, "Enviando…", async () => {
      const data = await call("/api/send", {
        file: sliced,
        print_now: printNow,
        mappings: mappings,
      });
      say(data.message, "ok");
      refreshPrinter();
    });
  }

  $("a-send").addEventListener("click", () => send(false));
  $("a-print").addEventListener("click", () => send(true));

  // Sending only works for files the printer actually accepts. A plain
  // .gcode is taken and silently discarded, so do not offer it.
  function updateSendButtons() {
    const send = $("a-send");
    const print = $("a-print");

    const queue = $("a-queue");
    if (!sliced) {
      for (const b of [send, print, queue]) {
        b.disabled = true;
        b.title = "Primero lamina la pieza";
      }
      return;
    }
    queue.disabled = false;
    queue.title = "";

    for (const b of [send, print]) {
      b.disabled = false;
      b.title = "";
    }
  }

  // ------------------------------------------------------------------- IFS

  let slots = [];       // spools the printer reports, by bay

  // With the printer unreachable we cannot know what is loaded, but the user
  // does: offer the four bays anyway rather than hiding the choice.
  const BAYS_UNKNOWN = [1, 2, 3, 4].map((slot_id) => ({
    slot_id, colour: "#6b7280", material: "?", loaded: true, unknown: true,
  }));

  function bays() {
    return slots.length ? slots : BAYS_UNKNOWN;
  }
  let lastInfo = null;  // tools of the file on screen
  let partNames = [];   // "Placa", "Letras"… when the part has colours

  function swatch(slot, chosen, onPick) {
    const label = document.createElement("label");
    label.className = "swatch" + (chosen ? " chosen" : "") + (slot.loaded ? "" : " empty");

    const input = document.createElement("input");
    input.type = "radio";
    input.name = "slot";
    input.value = String(slot.slot_id);
    input.checked = chosen;
    input.disabled = !slot.loaded;
    input.addEventListener("change", () => onPick(slot.slot_id));

    const dot = document.createElement("span");
    dot.className = "dot";
    dot.style.background = slot.colour;

    const text = document.createElement("span");
    text.textContent =
      "Canal " + slot.slot_id +
      (slot.unknown ? "" : " · " + (slot.loaded ? slot.material : "vacío"));

    label.append(input, dot, text);
    return label;
  }

  function mappingFor(toolId, slotId, tool) {
    const slot = bays().find((s) => s.slot_id === slotId);
    return {
      toolId,
      slotId,
      materialName: (slot && slot.material) || (tool && tool.material) || "PLA",
      toolMaterialColor: (tool && tool.colour) || (slot && slot.colour) || "#FFFFFF",
      slotMaterialColor: (slot && slot.colour) || "#FFFFFF",
    };
  }

  function renderIfs(info) {
    lastInfo = info;
    const panel = $("ifs");
    const rows = $("ifs-rows");
    rows.replaceChildren();

    if (!info) {
      panel.hidden = true;
      mappings = null;
      updateSendButtons();
      return;
    }

    panel.hidden = false;
    const disponibles = bays();
    const aCiegas = !slots.length;

    if (!info.multicolour) {
      // One colour: pick which spool prints it.
      $("ifs-title").textContent = "¿De qué color?";
      $("ifs-help").textContent = aCiegas
        ? "La impresora no responde, así que no puedo mostrarte los colores " +
          "cargados. Elige el canal de memoria: se imprimirá con esa bobina."
        : "Elige la bobina. Se imprime entera de ese color.";

      const tool = info.tools && info.tools[0];
      const current = (mappings && mappings[0] && mappings[0].slotId) ||
        (disponibles.find((s) => s.loaded) || { slot_id: 1 }).slot_id;
      mappings = [mappingFor(0, current, tool)];

      const box = document.createElement("div");
      box.className = "swatches";
      const pick = (slotId) => {
        mappings = [mappingFor(0, slotId, tool)];
        renderIfs(info);
      };
      disponibles.forEach((s) => box.append(swatch(s, s.slot_id === current, pick)));
      rows.append(box);

      updateSendButtons();
      return;
    }

    // Several colours: say which bay each one lives in.
    $("ifs-title").textContent = "Canales del IFS";
    $("ifs-help").textContent = partNames.length
      ? "Elige con qué bobina sale cada parte."
      : "Di en qué canal está cada color. El número que pone Orca junto a un " +
        "color no es el canal.";

    mappings = info.tools.map((tool, index) =>
      mappingFor(tool.tool_id, (mappings && mappings[index] && mappings[index].slotId) || index + 1, tool)
    );

    info.tools.forEach((tool, index) => {
      const row = document.createElement("div");
      row.className = "ifs-row";

      const dot = document.createElement("span");
      dot.className = "ifs-swatch";
      // Show the colour of the chosen spool, not the placeholder the slicer
      // wrote: that is what will actually come out.
      const elegido = disponibles.find((s) => s.slot_id === mappings[index].slotId);
      dot.style.background = (elegido && elegido.colour) || tool.colour;

      const name = document.createElement("span");
      name.className = "name";
      name.textContent = partNames[index] || tool.material + " " + tool.colour;

      const select = document.createElement("select");
      disponibles.forEach((s) => {
        const option = document.createElement("option");
        option.value = String(s.slot_id);
        option.textContent =
          "Canal " + s.slot_id +
          (s.unknown ? "" : s.loaded ? " · " + s.material : " · vacío");
        option.selected = mappings[index].slotId === s.slot_id;
        select.append(option);
      });
      select.addEventListener("change", () => {
        mappings[index] = mappingFor(tool.tool_id, Number(select.value), tool);
        const nuevo = disponibles.find((s) => s.slot_id === Number(select.value));
        if (nuevo) dot.style.background = nuevo.colour;
        flagClashes();
      });

      row.append(dot, name, select);
      rows.append(row);
    });

    flagClashes();
  }

  function flagClashes() {
    // Two colours on one channel is the mistake worth catching before sending.
    if (!mappings || mappings.length < 2) {
      updateSendButtons();
      return true;
    }
    const counts = new Map();
    mappings.forEach((m) => counts.set(m.slotId, (counts.get(m.slotId) || 0) + 1));

    let clean = true;
    $("ifs-rows").querySelectorAll("select").forEach((select) => {
      const clash = counts.get(Number(select.value)) > 1;
      select.classList.toggle("clash", clash);
      if (clash) clean = false;
    });

    if (!clean) {
      say("Dos colores apuntan al mismo canal del IFS.", "err");
      $("a-send").disabled = true;
      $("a-print").disabled = true;
    } else {
      updateSendButtons();
    }
    return clean;
  }

  async function loadGcodeInfo(file) {
    try {
      const info = await call("/api/gcode-info", { file });
      mappings = null;  // a new file starts with a fresh choice
      renderIfs(info);
      return info;
    } catch (error) {
      renderIfs(null);
      say(error.message, "err");
      $("a-send").disabled = true;
      $("a-print").disabled = true;
      $("a-send").title = $("a-print").title = "No se ha podido leer el fichero";
      return null;
    }
  }

  // ---------------------------------------------------------------- import

  $("import-file").addEventListener("change", async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const body = new FormData();
    body.append("file", file);
    try {
      const response = await fetch("/api/import", { method: "POST", body });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "No se pudo traer");

      $("result").hidden = false;
      $("r-file").textContent = data.file;
      $("a-download").href = "/salida/" + data.file;
      $("warnings").replaceChildren();

      if (data.kind === "model") {
        // A downloaded model: it still needs slicing before it can be sent.
        stlFile = data.file;
        sliceFile = data.file;
        sliced = null;
        mappings = null;
        $("ifs").hidden = true;
        $("r-size").textContent = "—";
        $("r-volume").textContent = "—";
        $("a-download").textContent = "Descargar modelo";
        updateSendButtons();

        if (data.file.toLowerCase().endsWith(".stl")) {
          viewer.load("/salida/" + data.file);
        }
        $("r-time").textContent = window.SLICER_READY ? "calculando…" : "—";
        if (window.SLICER_READY) {
          say(
            data.file + " traído" + (data.note ? ", " + data.note : "") +
              ". Calculando cuánto tarda…",
            "ok"
          );
          await laminar();
        } else {
          say(
            data.file + " traído" + (data.note ? ", " + data.note : "") +
              ". Falta Orca para prepararlo.",
            "ok"
          );
        }
        return;
      }

      // Already sliced: ready to send once the channels are sorted.
      sliced = data.file;
      stlFile = null;
      sliceFile = null;
      partNames = [];
      $("r-size").textContent = "—";
      $("r-volume").textContent = "—";
      $("a-download").textContent = "Descargar fichero";
      updateSendButtons();

      const info = await loadGcodeInfo(sliced);
      if (!info) return;  // loadGcodeInfo already explained what is wrong

      $("r-time").textContent = info.estimate || "—";
      const bits = [info.layers ? info.layers + " capas" : null,
                    info.estimate,
                    info.multicolour ? info.tools.length + " colores" : null]
        .filter(Boolean);
      say(data.file + " listo" + (bits.length ? " · " + bits.join(" · ") : ""), "ok");
    } catch (error) {
      say(error.message, "err");
    } finally {
      event.target.value = "";
    }
  });


  // ------------------------------------------------------------- trabajos

  let trabajosAbierto = false;
  let refrescoTrabajos = null;

  function tiempo(segundos) {
    if (!segundos || segundos < 0) return null;
    const h = Math.floor(segundos / 3600);
    const m = Math.round((segundos % 3600) / 60);
    return h ? h + "h " + m + "m" : m + "m";
  }

  function dato(etiqueta, valor) {
    const row = document.createElement("div");
    row.className = "t-dato";
    const a = document.createElement("span");
    a.textContent = etiqueta;
    const b = document.createElement("span");
    b.textContent = valor;
    row.append(a, b);
    return row;
  }

  function pintarActual(data) {
    const caja = $("t-actual-cuerpo");
    caja.replaceChildren();

    if (!data.configured) {
      caja.textContent = "La impresora no está configurada en el .env.";
      return;
    }
    if (data.error || !data.actual) {
      caja.textContent = data.error || "No responde.";
      return;
    }

    const a = data.actual;
    if (!a.busy) {
      caja.textContent = "Libre (" + a.state + "). Lista para el siguiente.";
      return;
    }

    const titulo = document.createElement("div");
    titulo.style.fontSize = "13.5px";
    titulo.style.marginBottom = "2px";
    titulo.textContent = a.job || "(trabajo sin nombre)";
    caja.append(titulo);

    if (a.done != null) {
      const barra = document.createElement("div");
      barra.className = "barra";
      const relleno = document.createElement("div");
      relleno.style.width = Math.round(a.done * 100) + "%";
      barra.append(relleno);
      caja.append(barra);
    }

    if (a.layer && a.total_layers) {
      caja.append(dato("Capa", a.layer + " de " + a.total_layers +
        (a.done != null ? "  (" + Math.round(a.done * 100) + "%)" : "")));
    }
    const queda = tiempo(a.remaining_s);
    if (queda) caja.append(dato("Le queda", queda));
    const lleva = tiempo(a.elapsed_s);
    if (lleva) caja.append(dato("Lleva", lleva));
    if (a.nozzle != null) {
      caja.append(dato("Temperaturas",
        Math.round(a.nozzle) + "° boquilla · " + Math.round(a.bed || 0) + "° cama"));
    }
  }

  function pintarCola(data) {
    const caja = $("t-cola");
    caja.replaceChildren();
    const cuenta = $("cola-cuenta");
    const pendientes = data.cola.filter((t) => t.state === "pendiente").length;
    cuenta.hidden = pendientes === 0;
    cuenta.textContent = String(pendientes);

    if (!data.cola.length) {
      const vacio = document.createElement("p");
      vacio.className = "muted";
      vacio.textContent = "Nada en cola. Genera una pieza y dale a «Añadir a la cola».";
      caja.append(vacio);
      return;
    }

    data.cola.forEach((t, i) => {
      const fila = document.createElement("div");
      fila.className = "t-trabajo " + t.state;

      const punto = document.createElement("span");
      punto.className = "punto";
      punto.style.background = (t.mappings && t.mappings[0]?.slotMaterialColor) || "#6b7280";

      const texto = document.createElement("div");
      texto.className = "texto";
      texto.textContent = t.label || t.file;
      const sub = document.createElement("small");
      sub.textContent =
        t.state === "pendiente" ? "en espera · añadido " + t.added
        : t.state === "enviado" ? (t.detail || "enviado")
        : t.state === "error" ? "falló: " + t.detail
        : t.state;
      texto.append(sub);

      const orden = document.createElement("div");
      orden.className = "orden";
      if (t.state === "pendiente") {
        [["▲", -1], ["▼", 1]].forEach(([signo, delta]) => {
          const b = document.createElement("button");
          b.textContent = signo;
          b.title = delta < 0 ? "Subir" : "Bajar";
          b.addEventListener("click", async () => {
            await call("/api/cola/mover", { index: i, delta });
            cargarTrabajos();
          });
          orden.append(b);
        });
      }

      const quitar = document.createElement("button");
      quitar.className = "quitar";
      quitar.textContent = "✕";
      quitar.title = "Quitar de la cola";
      quitar.addEventListener("click", async () => {
        const r = await fetch("/api/cola/" + i, { method: "DELETE" });
        if (r.ok) cargarTrabajos();
      });

      fila.append(punto, texto, orden, quitar);
      caja.append(fila);
    });
  }

  function pintarAlmacenados(data) {
    const caja = $("t-almacenados");
    caja.replaceChildren();
    if (!data.almacenados.length) {
      caja.textContent = "—";
      return;
    }
    data.almacenados.forEach((f) => {
      const c = document.createElement("code");
      c.textContent = f;
      caja.append(c);
    });
  }

  async function cargarTrabajos() {
    try {
      const data = await (await fetch("/api/trabajos")).json();
      pintarActual(data);
      pintarCola(data);
      pintarAlmacenados(data);
      $("t-auto").checked = data.auto;
    } catch {
      $("t-actual-cuerpo").textContent = "No se ha podido consultar.";
    }
  }

  function abrirTrabajos(abrir) {
    trabajosAbierto = abrir;
    $("trabajos").hidden = !abrir;
    clearInterval(refrescoTrabajos);
    if (abrir) {
      cargarTrabajos();
      // While a job is running the numbers move; keep them fresh.
      refrescoTrabajos = setInterval(cargarTrabajos, 10000);
    }
  }

  $("abrir-trabajos").addEventListener("click", () => abrirTrabajos(!trabajosAbierto));
  $("cerrar-trabajos").addEventListener("click", () => abrirTrabajos(false));
  $("t-auto").addEventListener("change", async (e) => {
    await call("/api/cola/auto", { auto: e.target.checked });
    cargarTrabajos();
  });
  $("t-limpiar").addEventListener("click", async () => {
    await call("/api/cola/limpiar", {});
    cargarTrabajos();
  });

  $("a-queue").addEventListener("click", async () => {
    if (!sliced) return;
    await withBusy($("a-queue"), "Añadiendo…", async () => {
      const data = await call("/api/cola", {
        file: sliced,
        mappings: mappings,
        label: ($("r-file").textContent || sliced).replace(/\.(gcode|3mf|stl)$/i, ""),
      });
      say("En la cola: " + data.added + " (" + data.pending + " esperando)", "ok");
      cargarTrabajos();
    });
  });

  // --------------------------------------------------------------- printer

  async function refreshPrinter() {
    const chip = $("printer-chip");
    try {
      const response = await fetch("/api/printer");
      const data = await response.json();

      // Discovery answers over UDP even with the HTTP API closed, so it can
      // say "it is there, LAN mode is off" instead of a blank "no responde".
      const seen = (data.found || [])
        .map((p) => p.model + " en " + p.ip)
        .join(", ");

      if (!data.configured) {
        chip.className = "chip chip--unknown";
        chip.textContent = seen
          ? "Encontrada: " + seen + " · falta configurar el .env"
          : "Impresora sin configurar (.env)";
        return;
      }
      if (!data.online) {
        chip.className = "chip chip--off";
        chip.textContent = seen
          ? seen + " · sin modo LAN"
          : "Impresora no responde";
        chip.title = data.error || "";
        return;
      }

      slots = data.slots || [];
      if (lastInfo && $("ifs").hidden && slots.length) renderIfs(lastInfo);

      chip.className = "chip chip--on";
      const temps = [
        data.nozzle != null ? "boquilla " + Math.round(data.nozzle) + "°" : null,
        data.bed != null ? "cama " + Math.round(data.bed) + "°" : null,
      ]
        .filter(Boolean)
        .join(" · ");
      // Layers, not the progress field: that one lags far behind.
      const capas =
        data.layer && data.total_layers
          ? "capa " + data.layer + " de " + data.total_layers
          : null;
      chip.textContent =
        data.machine + ": " + data.state +
        (capas ? " · " + capas : "") + (temps ? " · " + temps : "");
      chip.title = data.job ? "Imprimiendo " + data.job : "";
    } catch {
      chip.className = "chip chip--unknown";
      chip.textContent = "Estado desconocido";
    }
  }

  document.querySelectorAll(".part").forEach((button) =>
    button.addEventListener("click", () => select(button.dataset.slug))
  );

  refreshPrinter();
  setInterval(refreshPrinter, 15000);
})();
