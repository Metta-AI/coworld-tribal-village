"use strict";

const TribalVillageView = (() => {
  const TILE = 16;
  const MIN_TILE_SCALE = 1;
  const MAX_TILE_SCALE = 48;
  const NO_THING = 255;
  const SPRITE_FRAME_KIND = "tribal-village-sprite-cells-v1";
  const OFF = {
    terrain: 0,
    r: 1,
    g: 2,
    b: 3,
    thing: 4,
    orientation: 5,
    agentId: 6,
    teamId: 7,
    hp: 8,
    maxHp: 9,
    ore: 10,
    battery: 11,
    water: 12,
    wheat: 13,
    wood: 14,
    spear: 15,
    lantern: 16,
    armor: 17,
    bread: 18,
    count: 19,
    cooldown: 20,
    frozen: 21,
    flags: 22,
  };

  const THING = {
    agent: 0,
    wall: 1,
    mine: 2,
    converter: 3,
    assembler: 4,
    spawner: 5,
    tumor: 6,
    armory: 7,
    forge: 8,
    clayOven: 9,
    weavingLoom: 10,
    plantedLantern: 11,
  };

  const TERRAIN = {
    empty: 0,
    water: 1,
    bridge: 2,
    wheat: 3,
    tree: 4,
    fertile: 5,
  };

  const directionSprite = ["n", "s", "w", "e", "w", "e", "w", "e"];
  const assetKeys = [
    "agents/agent.n",
    "agents/agent.s",
    "agents/agent.w",
    "agents/agent.e",
    "agents/frozen",
    "agents/tumor.color.n",
    "agents/tumor.color.s",
    "agents/tumor.color.w",
    "agents/tumor.color.e",
    "agents/tumor.n",
    "agents/tumor.s",
    "agents/tumor.w",
    "agents/tumor.e",
    "objects/altar",
    "objects/armory",
    "objects/bridge",
    "objects/clay_oven",
    "objects/converter",
    "objects/fertile",
    "objects/forge",
    "objects/lantern",
    "objects/mine",
    "objects/palm_tree",
    "objects/spawner",
    "objects/water",
    "objects/weaving_loom",
    "objects/wheat_field",
    "resources/armor",
    "resources/battery",
    "resources/bread",
    "resources/ore",
    "resources/spear",
    "resources/water",
    "resources/wheat",
    "resources/wood",
    "ui/heart",
    "selection",
    ...[
      "",
      "e",
      "s",
      "se",
      "w",
      "we",
      "ws",
      "wse",
      "n",
      "ne",
      "ns",
      "nse",
      "nw",
      "nwe",
      "nws",
      "nwse",
      "fill",
    ].map((suffix) => suffix ? `objects/wall.${suffix}` : "objects/wall"),
  ];
  const tintCanvas = document.createElement("canvas");
  tintCanvas.width = TILE;
  tintCanvas.height = TILE;
  const tintCtx = tintCanvas.getContext("2d");

  function routedHttpAddress(clientPath, routePath) {
    const target = new URL(window.location.href);
    target.pathname = target.pathname.replace(clientPath, routePath);
    target.search = "";
    target.hash = "";
    return target.toString().replace(/\/$/, "");
  }

  function websocketAddress(clientPath, socketPath) {
    const pageUrl = new URL(window.location.href);
    const address = pageUrl.searchParams.get("address");
    const target = new URL(address || window.location.href, window.location.href);
    if (target.protocol === "http:") target.protocol = "ws:";
    if (target.protocol === "https:") target.protocol = "wss:";
    if (!address) target.pathname = target.pathname.replace(clientPath, socketPath);
    target.hash = "";
    return target.toString();
  }

  function assetBaseAddress(assetBase) {
    if (!assetBase || assetBase.startsWith("/")) {
      return routedHttpAddress(/\/client\/(?:global|player|replay)(?:\/.*)?$/, assetBase || "/assets");
    }
    return new URL(assetBase, window.location.href).toString().replace(/\/$/, "");
  }

  function playerSocketAddress() {
    const pageUrl = new URL(window.location.href);
    const target = new URL(websocketAddress(/\/client\/player$/, "/player"));
    for (const key of ["slot", "token"]) {
      const value = pageUrl.searchParams.get(key);
      if (value !== null) target.searchParams.set(key, value);
    }
    return target.toString();
  }

  function cssRgb(data, idx) {
    return `rgb(${data[idx + OFF.r]}, ${data[idx + OFF.g]}, ${data[idx + OFF.b]})`;
  }

  function rgba(hex, alpha) {
    const normalized = hex.startsWith("#") ? hex.slice(1) : hex;
    const r = parseInt(normalized.slice(0, 2), 16);
    const g = parseInt(normalized.slice(2, 4), 16);
    const b = parseInt(normalized.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function loadImage(src) {
    return new Promise((resolve) => {
      const image = new Image();
      image.decoding = "async";
      image.onload = () => resolve(image);
      image.onerror = () => resolve(null);
      image.src = src;
    });
  }

  async function loadAssets(assetBase) {
    const entries = await Promise.all(
      assetKeys.map(async (key) => [key, await loadImage(`${assetBase}/${key}.png`)])
    );
    return Object.fromEntries(entries);
  }

  function drawSprite(ctx, image, x, y, alpha = 1) {
    if (!image) return;
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.drawImage(image, x, y, 1, 1);
    ctx.restore();
  }

  function drawTintedSprite(ctx, image, x, y, color, alpha = 1) {
    if (!image) {
      ctx.fillStyle = color;
      ctx.fillRect(x + 0.1, y + 0.1, 0.8, 0.8);
      return;
    }
    tintCtx.clearRect(0, 0, TILE, TILE);
    tintCtx.globalCompositeOperation = "source-over";
    tintCtx.drawImage(image, 0, 0, TILE, TILE);
    tintCtx.globalCompositeOperation = "source-atop";
    tintCtx.fillStyle = color;
    tintCtx.fillRect(0, 0, TILE, TILE);
    tintCtx.globalCompositeOperation = "source-over";
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.drawImage(tintCanvas, x, y, 1, 1);
    ctx.restore();
  }

  class WorldRenderer {
    constructor(canvas, options = {}) {
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.minimap = options.minimap || null;
      this.tileScale = 6;
      this.offsetX = 0;
      this.offsetY = 0;
      this.followSlot = options.followSlot ?? null;
      this.hasFit = false;
      this.dragging = false;
      this.dragStart = {x: 0, y: 0};
      this.dragOrigin = {x: 0, y: 0};
      this.assets = {};
      this.assetBase = null;
      this.message = null;
      this.frame = null;
      this.cells = null;
      this.attachInput();
      window.addEventListener("resize", () => this.draw());
    }

    async ensureAssets(assetBase) {
      if (this.assetBase === assetBase) return;
      this.assetBase = assetBase;
      this.assets = await loadAssets(assetBase);
      this.draw();
    }

    attachInput() {
      this.canvas.addEventListener("wheel", (event) => {
        event.preventDefault();
        const before = this.screenToWorld(event.offsetX, event.offsetY);
        const factor = event.deltaY < 0 ? 1.16 : 0.86;
        this.tileScale = clamp(this.tileScale * factor, MIN_TILE_SCALE, MAX_TILE_SCALE);
        const after = this.screenToWorld(event.offsetX, event.offsetY);
        this.offsetX += (after.x - before.x) * this.tileScale;
        this.offsetY += (after.y - before.y) * this.tileScale;
        this.draw();
      }, {passive: false});
      this.canvas.addEventListener("pointerdown", (event) => {
        this.dragging = true;
        this.canvas.setPointerCapture(event.pointerId);
        this.canvas.classList.add("dragging");
        this.dragStart = {x: event.clientX, y: event.clientY};
        this.dragOrigin = {x: this.offsetX, y: this.offsetY};
      });
      this.canvas.addEventListener("pointermove", (event) => {
        if (this.dragging) {
          this.offsetX = this.dragOrigin.x + event.clientX - this.dragStart.x;
          this.offsetY = this.dragOrigin.y + event.clientY - this.dragStart.y;
          this.draw();
          return;
        }
      });
      this.canvas.addEventListener("pointerup", (event) => {
        this.dragging = false;
        this.canvas.releasePointerCapture(event.pointerId);
        this.canvas.classList.remove("dragging");
      });
      this.canvas.addEventListener("pointerleave", () => {
        this.dragging = false;
        this.canvas.classList.remove("dragging");
      });
    }

    setFollowSlot(slot) {
      this.followSlot = slot;
      this.draw();
    }

    setFrame(message, buffer) {
      this.message = message;
      this.frame = message.frame;
      if (!this.frame || this.frame.kind !== SPRITE_FRAME_KIND) {
        throw new Error(`unsupported Tribal Village sprite frame kind: ${this.frame?.kind}`);
      }
      const expectedBytes = this.frame.width * this.frame.height * this.frame.stride;
      if (buffer.byteLength !== expectedBytes) {
        throw new Error(`sprite frame byte length ${buffer.byteLength} does not match ${expectedBytes}`);
      }
      this.cells = new Uint8Array(buffer);
      void this.ensureAssets(assetBaseAddress(this.frame.asset_base));
      this.resizeCanvas();
      if (!this.hasFit) this.fitWorld();
      this.draw();
    }

    resizeCanvas() {
      const dpr = window.devicePixelRatio || 1;
      const width = Math.max(1, Math.floor(this.canvas.clientWidth * dpr));
      const height = Math.max(1, Math.floor(this.canvas.clientHeight * dpr));
      if (this.canvas.width !== width || this.canvas.height !== height) {
        this.canvas.width = width;
        this.canvas.height = height;
      }
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      this.ctx.imageSmoothingEnabled = false;
    }

    cssSize() {
      return {
        width: this.canvas.width / (window.devicePixelRatio || 1),
        height: this.canvas.height / (window.devicePixelRatio || 1),
      };
    }

    fitWorld() {
      if (!this.frame) return;
      const size = this.cssSize();
      this.tileScale = Math.max(MIN_TILE_SCALE, Math.min(size.width / this.frame.width, size.height / this.frame.height));
      this.offsetX = (size.width - this.frame.width * this.tileScale) / 2;
      this.offsetY = (size.height - this.frame.height * this.tileScale) / 2;
      this.hasFit = true;
    }

    screenToWorld(screenX, screenY) {
      return {
        x: (screenX - this.offsetX) / this.tileScale,
        y: (screenY - this.offsetY) / this.tileScale,
      };
    }

    cellIndex(x, y) {
      return (y * this.frame.width + x) * this.frame.stride;
    }

    cellValue(x, y, offset) {
      return this.cells[this.cellIndex(x, y) + offset];
    }

    isWall(x, y) {
      return (
        this.frame &&
        x >= 0 &&
        y >= 0 &&
        x < this.frame.width &&
        y < this.frame.height &&
        this.cellValue(x, y, OFF.thing) === THING.wall
      );
    }

    draw() {
      if (!this.frame || !this.cells) return;
      this.resizeCanvas();
      const ctx = this.ctx;
      const size = this.cssSize();
      ctx.clearRect(0, 0, size.width, size.height);
      ctx.fillStyle = "#080b0a";
      ctx.fillRect(0, 0, size.width, size.height);
      ctx.save();
      ctx.translate(this.offsetX, this.offsetY);
      ctx.scale(this.tileScale, this.tileScale);
      ctx.imageSmoothingEnabled = false;
      this.drawFloor(ctx);
      this.drawTerrain(ctx);
      this.drawWalls(ctx);
      this.drawThings(ctx);
      this.drawGrid(ctx);
      ctx.restore();
      this.drawLabels(ctx);
      this.drawMinimap();
    }

    drawFloor(ctx) {
      for (let y = 0; y < this.frame.height; y += 1) {
        for (let x = 0; x < this.frame.width; x += 1) {
          ctx.fillStyle = cssRgb(this.cells, this.cellIndex(x, y));
          ctx.fillRect(x, y, 1, 1);
        }
      }
    }

    drawTerrain(ctx) {
      for (let y = 0; y < this.frame.height; y += 1) {
        for (let x = 0; x < this.frame.width; x += 1) {
          const idx = this.cellIndex(x, y);
          const terrain = this.cells[idx + OFF.terrain];
          if (terrain === TERRAIN.water) drawSprite(ctx, this.assets["objects/water"], x, y);
          if (terrain === TERRAIN.bridge) drawSprite(ctx, this.assets["objects/bridge"], x, y);
          if (terrain === TERRAIN.wheat) drawSprite(ctx, this.assets["objects/wheat_field"], x, y);
          if (terrain === TERRAIN.tree) drawSprite(ctx, this.assets["objects/palm_tree"], x, y);
          if (terrain === TERRAIN.fertile) drawSprite(ctx, this.assets["objects/fertile"], x, y);
          if ((this.cells[idx + OFF.flags] & 4) !== 0) {
            ctx.fillStyle = "rgba(245, 82, 82, .42)";
            ctx.fillRect(x, y, 1, 1);
          }
        }
      }
    }

    wallSprite(mask) {
      let suffix = "";
      if ((mask & 8) !== 0) suffix += "n";
      if ((mask & 4) !== 0) suffix += "w";
      if ((mask & 2) !== 0) suffix += "s";
      if ((mask & 1) !== 0) suffix += "e";
      return suffix ? this.assets[`objects/wall.${suffix}`] : this.assets["objects/wall"];
    }

    drawWalls(ctx) {
      for (let y = 0; y < this.frame.height; y += 1) {
        for (let x = 0; x < this.frame.width; x += 1) {
          if (!this.isWall(x, y)) continue;
          const mask = (this.isWall(x, y - 1) ? 8 : 0) |
            (this.isWall(x - 1, y) ? 4 : 0) |
            (this.isWall(x, y + 1) ? 2 : 0) |
            (this.isWall(x + 1, y) ? 1 : 0);
          drawTintedSprite(ctx, this.wallSprite(mask), x, y, "rgb(76, 76, 76)");
        }
      }
    }

    drawThings(ctx) {
      for (let y = 0; y < this.frame.height; y += 1) {
        for (let x = 0; x < this.frame.width; x += 1) {
          const idx = this.cellIndex(x, y);
          const kind = this.cells[idx + OFF.thing];
          if (kind === NO_THING || kind === THING.wall) continue;
          if (kind === THING.agent) this.drawAgent(ctx, x, y, idx);
          if (kind === THING.mine) drawSprite(ctx, this.assets["objects/mine"], x, y);
          if (kind === THING.converter) drawSprite(ctx, this.assets["objects/converter"], x, y);
          if (kind === THING.assembler) this.drawAssembler(ctx, x, y, idx);
          if (kind === THING.spawner) drawSprite(ctx, this.assets["objects/spawner"], x, y);
          if (kind === THING.tumor) this.drawTumor(ctx, x, y, idx);
          if (kind === THING.armory) drawSprite(ctx, this.assets["objects/armory"], x, y);
          if (kind === THING.forge) drawSprite(ctx, this.assets["objects/forge"], x, y);
          if (kind === THING.clayOven) drawSprite(ctx, this.assets["objects/clay_oven"], x, y);
          if (kind === THING.weavingLoom) drawSprite(ctx, this.assets["objects/weaving_loom"], x, y);
          if (kind === THING.plantedLantern) this.drawLantern(ctx, x, y, idx);
          if (this.cells[idx + OFF.frozen] > 0) drawSprite(ctx, this.assets["agents/frozen"], x, y, 0.84);
        }
      }
    }

    teamColor(idx) {
      const colors = this.frame.team_colors || [];
      return colors[idx % colors.length] || "#e7ece4";
    }

    drawAgent(ctx, x, y, idx) {
      const dir = directionSprite[this.cells[idx + OFF.orientation] || 0];
      const team = this.cells[idx + OFF.teamId];
      drawTintedSprite(ctx, this.assets[`agents/agent.${dir}`], x, y, this.teamColor(team));
      const hp = this.cells[idx + OFF.hp];
      const maxHp = Math.max(1, this.cells[idx + OFF.maxHp]);
      for (let i = 0; i < 5; i += 1) {
        ctx.fillStyle = i < Math.ceil((hp / maxHp) * 5) ? "#2fbf64" : "rgba(28, 36, 31, .72)";
        ctx.fillRect(x + 0.12 + i * 0.15, y + 0.07, 0.11, 0.06);
      }
      this.drawInventory(ctx, x, y, idx);
    }

    drawInventory(ctx, x, y, idx) {
      const items = [
        ["resources/armor", OFF.armor, 0.05, 0.05],
        ["resources/water", OFF.water, 0.42, 0.02],
        ["resources/spear", OFF.spear, 0.74, 0.05],
        ["resources/bread", OFF.bread, 0.05, 0.40],
        ["resources/battery", OFF.battery, 0.40, 0.40],
        ["objects/lantern", OFF.lantern, 0.74, 0.40],
        ["resources/wheat", OFF.wheat, 0.05, 0.74],
        ["resources/ore", OFF.ore, 0.42, 0.76],
        ["resources/wood", OFF.wood, 0.74, 0.74],
      ];
      for (const [key, offset, dx, dy] of items) {
        const count = this.cells[idx + offset];
        if (count <= 0) continue;
        const image = this.assets[key];
        if (image) ctx.drawImage(image, x + dx, y + dy, 0.22, 0.22);
        if (count > 1) {
          ctx.fillStyle = "rgba(0, 0, 0, .74)";
          ctx.fillRect(x + dx + 0.11, y + dy + 0.11, 0.14, 0.12);
          ctx.fillStyle = "#fff6d6";
          ctx.font = "0.14px ui-monospace, monospace";
          ctx.fillText(String(count), x + dx + 0.12, y + dy + 0.21);
        }
      }
    }

    drawAssembler(ctx, x, y, idx) {
      const nearest = this.nearestAgentTeam(x, y);
      const color = this.teamColor(nearest);
      drawTintedSprite(ctx, this.assets["objects/altar"], x, y, color);
      const hearts = this.cells[idx + OFF.count];
      for (let i = 0; i < Math.min(hearts, 5); i += 1) {
        const heart = this.assets["ui/heart"];
        if (heart) ctx.drawImage(heart, x + 0.08 + i * 0.13, y + 0.05, 0.13, 0.13);
      }
    }

    nearestAgentTeam(x, y) {
      let bestTeam = 0;
      let bestDistance = Number.POSITIVE_INFINITY;
      for (const agent of this.message.agents || []) {
        const dx = Number(agent.x) - x;
        const dy = Number(agent.y) - y;
        const distance = dx * dx + dy * dy;
        if (distance < bestDistance) {
          bestDistance = distance;
          bestTeam = Number(agent.team || 0);
        }
      }
      return bestTeam;
    }

    drawTumor(ctx, x, y, idx) {
      const dir = directionSprite[this.cells[idx + OFF.orientation] || 0];
      const claimed = (this.cells[idx + OFF.flags] & 1) !== 0;
      const key = claimed ? `agents/tumor.${dir}` : `agents/tumor.color.${dir}`;
      drawSprite(ctx, this.assets[key], x, y);
    }

    drawLantern(ctx, x, y, idx) {
      const healthy = (this.cells[idx + OFF.flags] & 2) !== 0;
      const team = this.cells[idx + OFF.teamId];
      drawTintedSprite(
        ctx,
        this.assets["objects/lantern"],
        x,
        y,
        healthy ? this.teamColor(team) : "rgb(128, 128, 128)"
      );
    }

    drawGrid(ctx) {
      if (this.tileScale < 8) return;
      ctx.strokeStyle = "rgba(255, 255, 255, .07)";
      ctx.lineWidth = 1 / this.tileScale;
      ctx.beginPath();
      for (let x = 0; x <= this.frame.width; x += 1) {
        ctx.moveTo(x, 0);
        ctx.lineTo(x, this.frame.height);
      }
      for (let y = 0; y <= this.frame.height; y += 1) {
        ctx.moveTo(0, y);
        ctx.lineTo(this.frame.width, y);
      }
      ctx.stroke();
    }

    drawLabels(ctx) {
      if (!Array.isArray(this.message.agents) || this.tileScale < 5) return;
      ctx.font = "10px ui-monospace, SFMono-Regular, Menlo, monospace";
      ctx.textBaseline = "bottom";
      for (const agent of this.message.agents) {
        const slot = Number(agent.slot || 0);
        const team = Number(agent.team || 0);
        const label = `#${slot} ${agent.name || `Agent ${slot}`}`;
        const x = this.offsetX + (Number(agent.x) + 0.5) * this.tileScale;
        const y = this.offsetY + Number(agent.y) * this.tileScale - 2;
        if (x < -80 || y < 0 || x > this.cssSize().width + 80 || y > this.cssSize().height + 16) continue;
        const width = ctx.measureText(label).width;
        ctx.fillStyle = "rgba(8, 12, 10, .76)";
        ctx.fillRect(Math.round(x - width / 2 - 2), Math.round(y - 11), Math.ceil(width + 4), 12);
        ctx.fillStyle = this.teamColor(team);
        ctx.fillText(label, Math.round(x - width / 2), Math.round(y));
      }
    }

    drawMinimap() {
      if (!this.minimap || !this.frame || !this.cells) return;
      const ctx = this.minimap.getContext("2d");
      const width = this.minimap.width;
      const height = this.minimap.height;
      ctx.clearRect(0, 0, width, height);
      const sx = width / this.frame.width;
      const sy = height / this.frame.height;
      for (let y = 0; y < this.frame.height; y += 1) {
        for (let x = 0; x < this.frame.width; x += 1) {
          const idx = this.cellIndex(x, y);
          const terrain = this.cells[idx + OFF.terrain];
          ctx.fillStyle = terrain === TERRAIN.water ? "#295e85" : cssRgb(this.cells, idx);
          ctx.fillRect(x * sx, y * sy, Math.ceil(sx), Math.ceil(sy));
        }
      }
      for (const agent of this.message.agents || []) {
        ctx.fillStyle = this.teamColor(Number(agent.team || 0));
        ctx.fillRect(Number(agent.x) * sx - 1, Number(agent.y) * sy - 1, 3, 3);
      }
      const size = this.cssSize();
      const left = clamp(-this.offsetX / this.tileScale, 0, this.frame.width);
      const top = clamp(-this.offsetY / this.tileScale, 0, this.frame.height);
      const right = clamp((size.width - this.offsetX) / this.tileScale, 0, this.frame.width);
      const bottom = clamp((size.height - this.offsetY) / this.tileScale, 0, this.frame.height);
      const rectX = left * sx;
      const rectY = top * sy;
      const rectW = Math.max(2, (right - left) * sx);
      const rectH = Math.max(2, (bottom - top) * sy);
      ctx.fillStyle = "rgba(255, 243, 191, .10)";
      ctx.strokeStyle = "rgba(255, 243, 191, .95)";
      ctx.lineWidth = 2;
      ctx.fillRect(rectX, rectY, rectW, rectH);
      ctx.strokeRect(rectX + 1, rectY + 1, Math.max(1, rectW - 2), Math.max(1, rectH - 2));
    }

  }

  function attachWorldSocket(ws, renderer, onState) {
    let pending = null;
    ws.binaryType = "arraybuffer";
    ws.onmessage = (event) => {
      if (typeof event.data === "string") {
        pending = JSON.parse(event.data);
        if (onState) onState(pending);
        return;
      }
      if (event.data instanceof ArrayBuffer && pending) {
        renderer.setFrame(pending, event.data);
        pending = null;
      }
    };
  }

  return {
    SPRITE_FRAME_KIND,
    WorldRenderer,
    attachWorldSocket,
    assetBaseAddress,
    routedHttpAddress,
    websocketAddress,
    playerSocketAddress,
  };
})();
