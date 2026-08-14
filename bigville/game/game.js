/* Bigville's browser client. Phaser renders the world; Python remains the authority. */
const TILE = 16;
// Square simulation cells are presented at a readable 2x pixel-art scale.
// The style is 3/4 top-down: upright facades and sprites add depth, while the
// terrain itself remains square and walkable rather than becoming diamonds.
const DISPLAY_SCALE = 2;
const DEFAULT_ZOOM = 1.25;
// These are the initial viewport dimensions, not the world dimensions.  The
// world is drawn from whatever map grid the selected scenario exports.
const VIEWPORT_WIDTH = 52;
const VIEWPORT_HEIGHT = 40;
// Canonical Bigville map codes are deliberately separate from art-sheet frame
// numbers.  A different scenario can supply another grid without changing the
// renderer or pretending that the art is the geography.
const TILE_FRAMES = {0: 0, 1: 2, 2: 6, 3: 5, 4: 4, 5: 9, 6: 7, 7: 0};
const BUILDING_FRAMES = {
  house: 0, townhall: 1, church: 2, bank: 3, market: 4, press: 5,
  noticeboard: 6, school: 7, surgery: 8, inn: 9, granary: 10,
  root_cellar: 11, wellhouse: 12, latrine: 13, compost_yard: 14,
  smokehouse: 15, records_office: 16, watchhouse: 17, kitchen: 18,
  dairy: 19, wharf: 20, shambles: 21, dyehouse: 22, cooperage: 23,
  woodshop: 24, sawpit: 25, tannery: 26, cobbler: 27, tailorshop: 28,
  weavery: 29, forge: 30, bakery: 31, fishmonger: 32, mill: 33,
  printshop: 34, scriptorium: 35,
};
const ROLE_VARIANTS = {
  farmer: 3, smith: 4, cook: 5, clerk: 6, constable: 7, councillor: 8,
  merchant: 9, teacher: 10, doctor: 11, shepherd: 12, builder: 13,
  fisher: 14, craftsperson: 15
};

let state = null;
let scene = null;
let busy = false;
let selectedResidentId = null;

const $ = (id) => document.getElementById(id);
const pretty = (value) => String(value || '').replaceAll('_', ' ');

async function getState() {
  const response = await fetch('/api/state', {cache: 'no-store'});
  if (!response.ok) throw new Error(`state request failed (${response.status})`);
  return response.json();
}

async function submitTurn(payload) {
  if (busy) return;
  busy = true;
  $('status').textContent = 'The village is considering the turn…';
  try {
    const response = await fetch('/api/turn', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `turn failed (${response.status})`);
    state = result.state;
    renderAll();
  } catch (error) {
    $('status').textContent = error.message;
  } finally {
    busy = false;
    // Re-enable the action controls after the canonical turn response arrives.
    // The world and canvas were already refreshed above; only the controls
    // need to be rendered again here.
    renderSidebar();
  }
}

function player() {
  return state?.world?.residents?.find((r) => r.id === state.player);
}

function selectedResident() {
  const residents = state?.world?.residents || [];
  if (!selectedResidentId || !residents.some((r) => r.id === selectedResidentId)) {
    selectedResidentId = state?.player || residents[0]?.id || null;
  }
  return residents.find((r) => r.id === selectedResidentId) || null;
}

function itemIcon(kind) {
  const icons = scene?.assetManifest?.items?.icons || {};
  return icons[kind] || null;
}

function appendItemIcon(parent, kind) {
  const icon = document.createElement('span');
  icon.className = 'item-icon';
  const frame = itemIcon(kind);
  if (frame) icon.style.backgroundPosition = `-${frame.x * 24}px -${frame.y * 24}px`;
  icon.title = pretty(kind);
  parent.append(icon);
}

function renderInventory(resident) {
  const target = $('inventory');
  target.replaceChildren();
  if (!resident) {
    target.textContent = 'No resident selected.';
    target.className = 'inventory-empty';
    return;
  }
  target.className = 'inventory';
  const bulk = Object.entries(resident.inventory || {});
  const held = resident.held_items || [];
  if (!bulk.length && !held.length && !(resident.worn || []).length) {
    target.textContent = 'Empty hands and carrier.';
    target.className = 'inventory-empty';
    return;
  }
  for (const [kind, quantity] of bulk) {
    const row = document.createElement('div'); row.className = 'inventory-item';
    appendItemIcon(row, kind);
    row.append(`${pretty(kind)} × ${quantity}`);
    target.append(row);
  }
  for (const item of held) {
    const row = document.createElement('div'); row.className = 'inventory-item';
    appendItemIcon(row, item.kind);
    row.append(`${pretty(item.kind)} · ${item.location}`);
    target.append(row);
  }
  if ((resident.worn || []).length) {
    const worn = document.createElement('div'); worn.className = 'inventory-worn';
    worn.textContent = `Wearing: ${resident.worn.map(pretty).join(', ')}`;
    target.append(worn);
  }
}

function actionLabel(option) {
  const bits = [pretty(option.action)];
  for (const key of ['kind', 'recipe', 'trade', 'target']) {
    if (option[key]) bits.push(pretty(option[key].replace?.(/^target:/, '') || option[key]));
  }
  return bits.join(' · ');
}

function renderSidebar() {
  const actor = player();
  const inspected = selectedResident();
  const context = state.player_context || {};
  const clock = state.world.clock || {};
  $('status').textContent = `Turn ${clock.clock ?? 0} · day ${clock.day ?? 0}, ${clock.hour ?? 0}:00 · ${clock.season || ''}\n` +
    `${state.world.residents.filter((r) => r.alive).length} alive · ${state.world.animals.length} animals`;
  $('resident').textContent = inspected ? `${inspected.name} · ${pretty(inspected.role)} · ${inspected.coin} coins · energy ${Math.round(inspected.energy)}` : 'No resident';
  renderInventory(inspected);
  const inspector = $('inspect-resident');
  const previousInspection = inspector.value;
  inspector.replaceChildren();
  for (const resident of state.world.residents.filter((r) => r.alive)) {
    const option = document.createElement('option');
    option.value = resident.id; option.textContent = `Inspect ${resident.name}`;
    inspector.append(option);
  }
  inspector.value = selectedResidentId || previousInspection;
  inspector.onchange = () => { selectedResidentId = inspector.value; renderSidebar(); };
  const actions = $('actions');
  actions.replaceChildren();
  for (const option of (context.affordances || [])) {
    const row = document.createElement('div'); row.className = 'action';
    const button = document.createElement('button');
    button.innerHTML = `<span>${actionLabel(option)}</span><span class="score">${Math.round(option.score || 0)}</span>`;
    button.disabled = busy;
    button.onclick = () => submitTurn({major_action: {action: option.action, params: {
      kind: option.kind, recipe: option.recipe, trade: option.trade,
      target: option.target, destination: option.destination
    }}});
    row.append(button); actions.append(row);
  }
  if (!actions.children.length) actions.textContent = 'No legal major actions right now.';

  const recipient = $('recipient');
  const previous = recipient.value;
  recipient.replaceChildren();
  for (const resident of state.world.residents.filter((r) => r.alive && r.id !== state.player)) {
    const option = document.createElement('option'); option.value = resident.id; option.textContent = resident.name;
    recipient.append(option);
  }
  if ([...recipient.options].some((o) => o.value === previous)) recipient.value = previous;

  const speechEvents = (state.world.speech_events || []).slice(-10).reverse();
  const log = $('log'); log.replaceChildren();
  for (const event of speechEvents) {
    const line = document.createElement('div');
    line.textContent = `${event.speaker} → ${event.target || 'nearby'}: ${event.content || ''}`;
    log.append(line);
  }
  if (!log.children.length) log.textContent = 'No conversations yet.';
}

function renderWorld() {
  if (scene) scene.drawState(state);
}

function renderAll() { renderSidebar(); renderWorld(); }

class BigvilleScene extends Phaser.Scene {
  constructor() { super('bigville'); this.objects = []; this.hasCentered = false; this.dragging = false; }

  preload() {
    this.load.json('asset_manifest', 'assets/manifest.json');
    this.load.json('style_manifest', 'assets/style_manifest.json');
    // These are style-matched frames extracted from the original village art;
    // the map still chooses and assembles them from its own grid.
    this.load.spritesheet('tileset', 'assets/style_tiles.png', {frameWidth: TILE, frameHeight: TILE});
    this.load.spritesheet('props', 'assets/style_props.png', {frameWidth: TILE, frameHeight: TILE});
    this.load.spritesheet('large_props', 'assets/style_large_props.png', {frameWidth: 32, frameHeight: 32});
    this.load.spritesheet('buildings', 'assets/buildings.png', {frameWidth: 48, frameHeight: 48});
    this.load.spritesheet('style_buildings', 'assets/style_buildings.png', {frameWidth: 96, frameHeight: 96});
    this.load.spritesheet('style_cutaways', 'assets/style_cutaways.png', {frameWidth: 96, frameHeight: 96});
    this.load.spritesheet('building_interiors', 'assets/building_interiors.png', {frameWidth: 48, frameHeight: 48});
    this.load.spritesheet('building_parts', 'assets/building_parts.png', {frameWidth: TILE, frameHeight: TILE});
    this.load.spritesheet('building_badges', 'assets/building_badges.png', {frameWidth: TILE, frameHeight: TILE});
    this.load.spritesheet('items', 'assets/items.png', {frameWidth: TILE, frameHeight: TILE});
    this.load.spritesheet('characters', 'assets/style_characters.png', {frameWidth: 32, frameHeight: 32});
    this.load.spritesheet('actions', 'assets/actions.png', {frameWidth: 16, frameHeight: 16});
  }

  create() {
    scene = this;
    this.assetManifest = this.cache.json.get('asset_manifest') || {};
    this.styleManifest = this.cache.json.get('style_manifest') || {};
    this.cameras.main.setZoom(DEFAULT_ZOOM);
    $('zoom-reset').textContent = `${Math.round(DEFAULT_ZOOM * 100)}%`;
    this.cameras.main.setBackgroundColor('#172126');
    this.input.keyboard.on('keydown', (event) => {
      const amount = 80;
      const key = event.key.toLowerCase();
      if (key === 'w' || key === 'arrowup') this.cameras.main.scrollY -= amount;
      if (key === 's' || key === 'arrowdown') this.cameras.main.scrollY += amount;
      if (key === 'a' || key === 'arrowleft') this.cameras.main.scrollX -= amount;
      if (key === 'd' || key === 'arrowright') this.cameras.main.scrollX += amount;
    });
    this.input.on('wheel', (_pointer, _gameObjects, _deltaX, deltaY) => {
      this.adjustZoom(deltaY > 0 ? -0.1 : 0.1);
    });
    this.input.on('pointerdown', (pointer) => {
      this.dragging = true;
      this.lastPointer = {x: pointer.x, y: pointer.y};
    });
    this.input.on('pointerup', () => { this.dragging = false; });
    this.input.on('pointermove', (pointer) => {
      if (!this.dragging || !this.lastPointer) return;
      const zoom = this.cameras.main.zoom || 1;
      this.cameras.main.scrollX -= (pointer.x - this.lastPointer.x) / zoom;
      this.cameras.main.scrollY -= (pointer.y - this.lastPointer.y) / zoom;
      this.lastPointer = {x: pointer.x, y: pointer.y};
    });
    this.drawState(state);
  }

  drawState(snapshot) {
    if (!snapshot || !this.add) return;
    for (const object of this.objects) object.destroy();
    this.objects = [];
    const map = snapshot.world.map;
    const width = map.width * TILE * DISPLAY_SCALE;
    const height = map.height * TILE * DISPLAY_SCALE;
    this.drawCanonicalMap(map);
    this.drawTerrainProps(map);
    const allResidents = snapshot.world.residents || [];
    this.playerId = snapshot.player;
    const playerResident = allResidents.find((resident) => resident.id === snapshot.player);
    const occupiedResidents = this.drawBuildings(map.buildings || [], allResidents);
    const outsideResidents = allResidents.filter((resident) => {
      if (occupiedResidents.has(resident.id)) return false;
      if (resident.id === snapshot.player || !playerResident) return true;
      return Math.abs((resident.x || 0) - (playerResident.x || 0)) <= 5 &&
        Math.abs((resident.y || 0) - (playerResident.y || 0)) <= 5;
    });
    const nearby = outsideResidents
      .filter((resident) => resident.id !== snapshot.player)
      .sort((a, b) => this.distanceTo(a, playerResident) - this.distanceTo(b, playerResident))
      .slice(0, 5);
    const visibleResidents = [
      ...(playerResident && !occupiedResidents.has(playerResident.id) ? [playerResident] : []),
      ...nearby,
    ];
    for (const resident of visibleResidents) {
      const pos = resident.position || [0, 0];
      const previous = this.previousResidents?.[resident.id];
      const previousPosition = previous?.position || pos;
      const direction = this.residentDirection(previousPosition, pos);
      const frame = this.residentFrame(resident, 0, direction);
      const moving = Number(previousPosition[0]) !== Number(pos[0]) ||
        Number(previousPosition[1]) !== Number(pos[1]);
      const sprite = this.add.sprite(this.cellX(previousPosition[0]), this.cellY(previousPosition[1]), 'characters', frame)
        .setScale(1).setDepth(this.depthAt(pos[0], pos[1], 30));
      sprite.setInteractive({useHandCursor: true});
      sprite.on('pointerdown', () => { selectedResidentId = resident.id; renderSidebar(); });
      if (resident.id === snapshot.player) sprite.setScale(DISPLAY_SCALE * 1.45).setTint(0xffe1a8);
      this.objects.push(sprite);
      this.drawResidentItems(resident, pos);
      if (moving) this.animateWalking(sprite, resident, direction, pos);
      if (resident.id === snapshot.player && !this.hasCentered) {
        this.cameras.main.centerOn(this.cellX(pos[0]), this.cellY(pos[1]));
        this.hasCentered = true;
      }
    }
    this.cameras.main.setBounds(0, 0, width, height);
    this.previousResidents = Object.fromEntries(allResidents.map((resident) => [
      resident.id, {position: resident.position || [resident.x || 0, resident.y || 0]},
    ]));
  }

  cellX(x) { return Number(x) * TILE * DISPLAY_SCALE + (TILE * DISPLAY_SCALE) / 2; }
  cellY(y) { return Number(y) * TILE * DISPLAY_SCALE + (TILE * DISPLAY_SCALE) / 2; }
  depthAt(x, y, layer = 0) { return Number(y) * 1000 + Number(x) + layer; }

  adjustZoom(delta) {
    const camera = this.cameras.main;
    camera.setZoom(Math.max(0.75, Math.min(3, Number((camera.zoom + delta).toFixed(2)))));
    $('zoom-reset').textContent = `${Math.round(camera.zoom * 100)}%`;
  }

  resetView() {
    this.cameras.main.setZoom(DEFAULT_ZOOM);
    $('zoom-reset').textContent = `${Math.round(DEFAULT_ZOOM * 100)}%`;
    this.hasCentered = false;
    this.drawState(state);
  }

  residentDirection(from, to) {
    const dx = Number(to[0]) - Number(from[0]);
    const dy = Number(to[1]) - Number(from[1]);
    if (Math.abs(dx) >= Math.abs(dy) && dx !== 0) return dx < 0 ? 2 : 3;
    if (dy !== 0) return dy < 0 ? 1 : 0;
    return 0;
  }

  animateWalking(sprite, resident, direction, position) {
    const start = sprite.getData('walkTween') || 0;
    const base = this.residentFrame(resident, 0, direction) -
      (this.residentFrame(resident, 0, direction) % 3);
    const frames = [base, base + 1, base, base + 2];
    const targetX = this.cellX(position[0]);
    const targetY = this.cellY(position[1]);
    const distance = Math.max(1, Math.abs(targetX - sprite.x) + Math.abs(targetY - sprite.y));
    const duration = Math.max(220, Math.min(620, 180 + distance * 2));
    const tween = this.tweens.add({
      targets: sprite, x: targetX, y: targetY, duration, ease: 'Linear',
      onUpdate: (t) => {
        const phase = Math.min(frames.length - 1,
          Math.floor(t.progress * frames.length));
        sprite.setFrame(frames[phase]);
      },
      onComplete: () => sprite.setFrame(base),
    });
    sprite.setData('walkTween', start + 1);
    return tween;
  }

  terrainFrame(tile, x, y, grid) {
    const named = {0: 'grass', 1: 'path', 2: 'wall', 3: 'floor', 4: 'square',
      5: 'tree', 6: 'water', 7: 'grass'};
    const transitions = this.assetManifest?.terrain?.transition_masks || {};
    const same = (nx, ny, value) => grid[ny]?.[nx] === value;
    const mask = (value) => (same(x, y - 1, value) ? 1 : 0) |
      (same(x + 1, y, value) ? 2 : 0) |
      (same(x, y + 1, value) ? 4 : 0) |
      (same(x - 1, y, value) ? 8 : 0);
    if (tile === 1) {
      const pathMask = mask(1);
      const variants = this.styleManifest?.path_variants?.[String(pathMask)];
      if (variants?.length) {
        const variant = Math.abs((Number(x) * 92837111 + Number(y) * 689287499) % variants.length);
        return variants[variant];
      }
      const frame = transitions.path?.[String(pathMask)];
      if (frame !== undefined) return frame;
    } else if (tile === 6) {
      const frame = transitions.water?.[String(mask(6))];
      if (frame !== undefined) return frame;
    }
    const tileNames = this.assetManifest?.tileset?.tiles || {};
    return tileNames[named[tile]] ?? TILE_FRAMES[tile] ?? TILE_FRAMES[0];
  }

  drawCanonicalMap(map) {
    const grid = map.grid || [];
    for (let y = 0; y < grid.length; y++) {
      for (let x = 0; x < (grid[y] || []).length; x++) {
        const tile = grid[y][x];
        const frame = this.terrainFrame(tile, x, y, grid);
        const sprite = this.add.sprite(this.cellX(x), this.cellY(y), 'tileset', frame)
          .setScale(DISPLAY_SCALE).setDepth(this.depthAt(x, y, 0));
        this.objects.push(sprite);
      }
    }
  }

  drawTerrainProps(map) {
    const grid = map.grid || [];
    const props = this.styleManifest?.props?.sprites || this.assetManifest?.terrain?.props || {};
    const largeProps = this.styleManifest?.large_props?.sprites || this.assetManifest?.terrain?.large_props || {};
    const buildings = map.buildings || [];
    const occupied = new Set();
    for (const building of buildings) {
      const [bx, by] = building.position || [building.x || 0, building.y || 0];
      const width = Math.max(1, Number(building.w || 3));
      const height = Math.max(1, Number(building.h || 3));
      for (let y = by; y < by + height; y++) {
        for (let x = bx; x < bx + width; x++) occupied.add(`${x},${y}`);
      }
    }
    // A stable hash makes the village feel lived-in while keeping screenshots,
    // replays, and alternate clients deterministic. Props are overlays, never
    // geography: the exported grid remains the sole source of collision data.
    const hash = (x, y) => Math.abs((x * 92837111 + y * 689287499 +
      (map.seed || 0) * 31) % 1000003);
    const addProp = (name, x, y, depth = 1.1) => {
      const frame = props[name];
      if (frame === undefined) return;
      const sprite = this.add.sprite(this.cellX(x), this.cellY(y) - 6 * DISPLAY_SCALE,
        'props', frame).setScale(DISPLAY_SCALE).setDepth(this.depthAt(x, y, depth));
      this.objects.push(sprite);
    };
    const addLargeProp = (name, x, y, depth = 1.5) => {
      const frame = largeProps[name];
      if (frame === undefined) return;
      const sprite = this.add.sprite(this.cellX(x), this.cellY(y) - 16 * DISPLAY_SCALE,
        'large_props', frame).setScale(DISPLAY_SCALE)
        .setDepth(this.depthAt(x, y, depth));
      this.objects.push(sprite);
    };
    for (let y = 0; y < grid.length; y++) {
      for (let x = 0; x < (grid[y] || []).length; x++) {
        const tile = grid[y][x];
        if (occupied.has(`${x},${y}`)) continue;
        const roll = hash(x, y) % 1000;
        if (tile === 0) {
          const nearPath = [
            grid[y - 1]?.[x], grid[y]?.[x + 1], grid[y + 1]?.[x], grid[y]?.[x - 1]
          ].some(value => value === 1 || value === 4);
          if (nearPath && roll < 95) addProp('flower_clump', x, y);
          else if (nearPath && roll < 145) addProp('grass_tuft', x, y);
          else if (roll < 45) addLargeProp('tree', x, y);
          else if (roll < 115) addLargeProp('bush', x, y);
          else if (roll < 76) addProp('flower_clump', x, y);
          else if (roll < 90) addProp('grass_tuft', x, y);
          else if (roll < 97) addProp('stone', x, y);
          else if (roll < 99) addProp('mushroom', x, y);
          else if (roll === 227) addProp('log', x, y);
          else if (roll === 311) addProp('stump', x, y);
        } else if (tile === 6 && roll % 5 === 0) {
          const shoreline = [
            grid[y - 1]?.[x], grid[y]?.[x + 1], grid[y + 1]?.[x], grid[y]?.[x - 1]
          ].some(value => value !== 6);
          if (shoreline) addProp('reed', x, y);
        } else if (tile === 1 && roll === 19) {
          // An occasional roadside barrel/bench breaks up the long lattice
          // without making the walkable route ambiguous.
          addProp(roll % 2 ? 'barrel' : 'bench', x, y, 1.15);
        }
      }
    }
  }

  drawBuildings(buildings, residents) {
    const manifestFrames = this.assetManifest?.buildings?.sprites || {};
    const spots = new Map();
    const priority = {
      townhall: 20, bakery: 19, kitchen: 18, granary: 17, inn: 16,
      school: 15, records_office: 14, watchhouse: 13, dairy: 12,
      forge: 11, mill: 10, house: 9,
    };
    for (const building of buildings) {
      const pos = building.position || [building.x || 0, building.y || 0];
      const key = `${pos[0]},${pos[1]}`;
      const current = spots.get(key);
      if (!current || (priority[building.type] || 0) > (priority[current.type] || 0)) {
        spots.set(key, {...building, position: pos});
      }
    }
    const inside = new Set();
    for (const building of spots.values()) {
      const [x, y] = building.position;
      const width = Math.max(1, Number(building.w || 3));
      const height = Math.max(1, Number(building.h || 3));
      const occupants = residents.filter((resident) => {
        if (inside.has(resident.id)) return false;
        const rx = Number(resident.x ?? resident.position?.[0] ?? -999);
        const ry = Number(resident.y ?? resident.position?.[1] ?? -999);
        return rx >= x && rx < x + width && ry >= y && ry < y + height;
      });
      for (const resident of occupants) inside.add(resident.id);
      // An empty building shows its authored facade; occupied buildings open
      // into the existing roof-off interior representation.
      this.drawBuilding(building, occupants.length === 0);
      occupants.forEach((resident, index) => this.drawInteriorResident(building, resident, index));
    }
    return inside;
  }

  drawBuilding(building, roofOn) {
    const [x, y] = building.position || [building.x || 0, building.y || 0];
    const width = Math.max(1, Number(building.w || 3));
    const height = Math.max(1, Number(building.h || 3));
    const px = x * TILE * DISPLAY_SCALE;
    const py = y * TILE * DISPLAY_SCALE;
    const cellWidth = TILE * DISPLAY_SCALE;
    const manifest = this.assetManifest?.buildings || {};
    const frame = (manifest.sprites || {})[building.type]
      ?? BUILDING_FRAMES[building.type] ?? BUILDING_FRAMES.house;

    // Preserve the authored 3x3 institution art while allowing arbitrary
    // footprints to fall back to the composable part vocabulary.
    if (width === 3 && height === 3) {
      const styleFrame = this.styleManifest?.buildings?.sprites?.[building.type];
      if (roofOn && styleFrame !== undefined) {
        const sprite = this.add.sprite(px + width * cellWidth / 2,
          py + height * cellWidth / 2, 'style_buildings', styleFrame)
          .setDepth(this.depthAt(x + width / 2, y + height, 20));
        this.objects.push(sprite);
        return;
      }
      const cutawayFrame = this.styleManifest?.cutaways?.sprites?.[building.type];
      if (!roofOn && cutawayFrame !== undefined) {
        const sprite = this.add.sprite(px + width * cellWidth / 2,
          py + height * cellWidth / 2, 'style_cutaways', cutawayFrame)
          .setDepth(this.depthAt(x + width / 2, y + height, 20));
        this.objects.push(sprite);
        return;
      }
      const sprite = this.add.sprite(px + width * cellWidth / 2,
        py + height * cellWidth / 2 - 8 * DISPLAY_SCALE,
        roofOn ? 'buildings' : 'building_interiors', frame)
        .setScale(DISPLAY_SCALE).setDepth(this.depthAt(x + width / 2, y + height, 20));
      this.objects.push(sprite);
      return;
    }

    const parts = manifest.parts || {};
    const addPart = (name, cellX, cellY, depth = 2, tint = null) => {
      if (parts[name] === undefined) return;
      const sprite = this.add.sprite(px + cellX * cellWidth + cellWidth / 2,
        py + cellY * cellWidth + cellWidth / 2 - 4 * DISPLAY_SCALE,
        'building_parts', parts[name]).setScale(DISPLAY_SCALE)
        .setDepth(this.depthAt(x + cellX, y + cellY, depth));
      if (tint !== null) sprite.setTint(tint);
      this.objects.push(sprite);
    };
    const roofTint = {
      bakery: 0xd26b4e, granary: 0xd3a33d, forge: 0x766d68,
      school: 0x6ca35f, records_office: 0x6388a7, watchhouse: 0x6388a7,
    }[building.type] || 0xb1543e;
    for (let cy = 0; cy < height; cy++) {
      for (let cx = 0; cx < width; cx++) {
        if (roofOn) {
          addPart((cx === 0 || cy === 0 || cx === width - 1 || cy === height - 1)
            ? 'roof_edge' : 'roof', cx, cy, 2, roofTint);
        } else {
          addPart('floor', cx, cy, 1.5);
          if (cx === 0 || cy === 0 || cx === width - 1 || cy === height - 1) {
            addPart('wall', cx, cy, 2);
          }
        }
      }
    }
    if (!roofOn) {
      addPart('door', Math.floor(width / 2), height - 1, 2.2);
      if (width > 2) {
        addPart('window', 0, Math.min(1, height - 1), 2.2);
        addPart('window', width - 1, Math.min(1, height - 1), 2.2);
      }
      const fixture = /forge|smith/.test(building.type) ? 'workbench'
        : /granary|storage|cellar/.test(building.type) ? 'crate'
        : /inn|house|school/.test(building.type) ? 'bed' : 'counter';
      addPart(fixture, Math.min(1, width - 1), Math.min(1, height - 1), 2.1);
    } else {
      const badges = manifest.badges || {};
      if (badges[building.type] !== undefined) {
        const badge = this.add.sprite(px + Math.floor(width / 2) * cellWidth + cellWidth / 2,
          py + height * cellWidth - 8 * DISPLAY_SCALE, 'building_badges', badges[building.type])
          .setScale(DISPLAY_SCALE).setDepth(this.depthAt(x + width / 2, y + height, 22));
        this.objects.push(badge);
      }
    }
  }

  drawInteriorResident(building, resident, index) {
    const [x, y] = building.position || [building.x || 0, building.y || 0];
    const width = Math.max(1, Number(building.w || 3));
    const height = Math.max(1, Number(building.h || 3));
    const cellX = Math.min(width - 1, 1 + (index % Math.max(1, width - 1)));
    const cellY = Math.min(height - 1, 1 + Math.floor(index / Math.max(1, width - 1)));
    const sprite = this.add.sprite(this.cellX(x + cellX), this.cellY(y + cellY) - 8 * DISPLAY_SCALE,
      'characters', this.residentFrame(resident))
      .setScale(1.15).setDepth(this.depthAt(x + cellX, y + cellY, 30));
    sprite.setInteractive({useHandCursor: true});
    sprite.on('pointerdown', () => { selectedResidentId = resident.id; renderSidebar(); });
    if (resident.id === this.playerId) sprite.setTint(0xffe1a8);
    this.objects.push(sprite);
    this.drawResidentItems(resident, [x + cellX, y + cellY]);
  }

  residentFrame(resident, frame = 0, direction = 0) {
    const role = String(resident.role || '').toLowerCase();
    return (ROLE_VARIANTS[role] ?? 0) * 12 + direction * 3 + frame;
  }

  drawResidentItems(resident, pos) {
    const hand = (resident.held_items || []).find((item) => item.location === 'hand')
      || (resident.held_items || [])[0];
    const worn = resident.worn || [];
    const drawItem = (item, x, y, scale = 0.85) => {
      const frame = itemIcon(item.kind);
      if (!frame) return;
      const sprite = this.add.sprite(x, y, 'items', frame.frame).setScale(scale * DISPLAY_SCALE)
        .setDepth(this.depthAt(pos[0], pos[1], 35));
      this.objects.push(sprite);
    };
    if (hand) drawItem(hand, this.cellX(pos[0]) + 7 * DISPLAY_SCALE,
      this.cellY(pos[1]) - 9 * DISPLAY_SCALE);
    // Keep clothing readable without replacing the role/age body variant.
    worn.slice(0, 2).forEach((kind, index) => {
      const hat = /hat|bonnet|hood|cap/.test(kind);
      drawItem({kind}, this.cellX(pos[0]) + (hat ? 0 : -5 + index * 10) * DISPLAY_SCALE,
               this.cellY(pos[1]) - (hat ? 9 : -1) * DISPLAY_SCALE, 0.55);
    });
  }

  distanceTo(a, b) {
    if (!a || !b) return 0;
    return Math.abs((a.x || 0) - (b.x || 0)) + Math.abs((a.y || 0) - (b.y || 0));
  }

}

const config = {
  type: Phaser.AUTO, parent: 'game', width: VIEWPORT_WIDTH * TILE, height: VIEWPORT_HEIGHT * TILE,
  pixelArt: true, backgroundColor: '#172126', scene: [BigvilleScene],
  scale: {mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_BOTH}
};
new Phaser.Game(config);

$('speak').onclick = () => {
  const content = $('speech').value.trim();
  if (!content || !$('recipient').value) return;
  submitTurn({utterances: [{target: $('recipient').value, content}]});
  $('speech').value = '';
};
$('reset').onclick = async () => {
  const response = await fetch('/api/reset', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'});
  state = await response.json();
  if (scene) scene.resetView();
  renderSidebar();
};
$('zoom-in').onclick = () => scene?.adjustZoom(0.25);
$('zoom-out').onclick = () => scene?.adjustZoom(-0.25);
$('zoom-reset').onclick = () => scene?.resetView();

getState().then((loaded) => { state = loaded; renderAll(); }).catch((error) => { $('status').textContent = error.message; });
