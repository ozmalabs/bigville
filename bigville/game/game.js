/* Bigville's browser client. Phaser renders the world; Python remains the authority. */
const TILE = 16;
const MAP_WIDTH = 52;
const MAP_HEIGHT = 40;
const TILE_FRAMES = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7};
const ROLE_VARIANTS = {
  farmer: 3, smith: 4, cook: 5, clerk: 6, constable: 7, councillor: 8,
  merchant: 9, teacher: 10, doctor: 11, shepherd: 12, builder: 13,
  fisher: 14, craftsperson: 15
};

let state = null;
let scene = null;
let busy = false;

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

function actionLabel(option) {
  const bits = [pretty(option.action)];
  for (const key of ['kind', 'recipe', 'trade', 'target']) {
    if (option[key]) bits.push(pretty(option[key].replace?.(/^target:/, '') || option[key]));
  }
  return bits.join(' · ');
}

function renderSidebar() {
  const actor = player();
  const context = state.player_context || {};
  const clock = state.world.clock || {};
  $('status').textContent = `Turn ${clock.clock ?? 0} · day ${clock.day ?? 0}, ${clock.hour ?? 0}:00 · ${clock.season || ''}\n` +
    `${state.world.residents.filter((r) => r.alive).length} alive · ${state.world.animals.length} animals`;
  $('resident').textContent = actor ? `${actor.name} · ${pretty(actor.role)} · ${actor.coin} coins · energy ${Math.round(actor.energy)}` : 'No player';
  const actions = $('actions');
  actions.replaceChildren();
  for (const option of (context.affordances || [])) {
    const row = document.createElement('div'); row.className = 'action';
    const button = document.createElement('button');
    button.innerHTML = `<span>${actionLabel(option)}</span><span class="score">${Math.round(option.score || 0)}</span>`;
    button.disabled = busy;
    button.onclick = () => submitTurn({major_action: {action: option.action, params: {
      kind: option.kind, recipe: option.recipe, trade: option.trade, target: option.target
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
    this.load.image('village_scene', 'assets/village_scene.png');
    this.load.image('open_room', 'assets/open_room.png');
    this.load.spritesheet('tileset', 'assets/tileset.png', {frameWidth: TILE, frameHeight: TILE});
    this.load.spritesheet('buildings', 'assets/buildings.png', {frameWidth: 48, frameHeight: 48});
    this.load.spritesheet('characters', 'assets/character_variants.png', {frameWidth: 16, frameHeight: 16});
    this.load.spritesheet('actions', 'assets/actions.png', {frameWidth: 16, frameHeight: 16});
  }

  create() {
    scene = this;
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
    const width = map.width * TILE;
    const height = map.height * TILE;
    const backdrop = this.add.image(width / 2, height / 2, 'village_scene')
      .setDisplaySize(width, height).setDepth(0);
    this.objects.push(backdrop);
    this.drawCanonicalMap(map);
    const allResidents = snapshot.world.residents || [];
    this.playerId = snapshot.player;
    const playerResident = allResidents.find((resident) => resident.id === snapshot.player);
    const occupiedResidents = this.drawOccupiedInteriors(map.buildings || [], allResidents);
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
      const frame = this.residentFrame(resident);
      const sprite = this.add.sprite(pos[0] * TILE + 8, pos[1] * TILE + 8, 'characters', frame).setDepth(3);
      if (resident.id === snapshot.player) sprite.setScale(1.45).setTint(0xffe1a8);
      this.objects.push(sprite);
      if (resident.id === snapshot.player && !this.hasCentered) {
        this.cameras.main.centerOn(pos[0] * TILE, pos[1] * TILE);
        this.hasCentered = true;
      }
    }
    this.cameras.main.setBounds(0, 0, width, height);
  }

  adjustZoom(delta) {
    const camera = this.cameras.main;
    camera.setZoom(Math.max(0.75, Math.min(3, Number((camera.zoom + delta).toFixed(2)))));
    $('zoom-reset').textContent = `${Math.round(camera.zoom * 100)}%`;
  }

  resetView() {
    this.cameras.main.setZoom(1);
    $('zoom-reset').textContent = '100%';
    this.hasCentered = false;
    this.drawState(state);
  }

  drawCanonicalMap(map) {
    const grid = map.grid || [];
    const routes = this.add.graphics().setDepth(1);
    const tileColours = {
      path: 0xd4ad6d,
      square: 0xc7b887,
      floor: 0xa47b59,
      wall: 0x625b63,
      water: 0x4e9da5,
      tree: 0x4f804c,
    };
    for (let y = 0; y < grid.length; y++) {
      for (let x = 0; x < (grid[y] || []).length; x++) {
        const tile = grid[y][x];
        const px = x * TILE;
        const py = y * TILE;
        // These overlays are deliberately translucent: the generated village
        // art supplies warmth and texture, while this layer makes the
        // simulation's real navigation lattice visible and authoritative.
        if (tile === 1) {
          // A small stitched marker keeps the real road lattice visible
          // without turning the cosy artwork into a debugging grid.
          routes.fillStyle(tileColours.path, 0.55).fillRect(px + 5, py + 5, 6, 6);
        } else if (tile === 4) {
          routes.fillStyle(tileColours.square, 0.28).fillRect(px, py, TILE, TILE);
        } else if (tile === 2 || tile === 6) {
          routes.fillStyle(tile === 6 ? tileColours.water : tileColours.wall, 0.42)
            .fillRect(px, py, TILE, TILE);
        } else if (tile === 5) {
          routes.fillStyle(tileColours.tree, 0.16).fillRect(px, py, TILE, TILE);
        }
      }
    }
    this.objects.push(routes);
  }

  drawOccupiedInteriors(buildings, residents) {
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
      const occupants = residents.filter((resident) => {
        if (inside.has(resident.id)) return false;
        const rx = Number(resident.x ?? resident.position?.[0] ?? -999);
        const ry = Number(resident.y ?? resident.position?.[1] ?? -999);
        return rx >= x && rx < x + (building.w || 3) &&
          ry >= y && ry < y + (building.h || 3);
      });
      if (!occupants.length) continue;
      for (const resident of occupants) inside.add(resident.id);
      const px = x * TILE;
      const py = y * TILE;
      // The roofless room asset replaces the opaque roof sprite. Occupants
      // are added below at their actual world coordinates.
      const room = this.add.image(px + 24, py + 24, 'open_room')
        .setDisplaySize(48, 48).setDepth(2);
      this.objects.push(room);
      occupants.forEach((resident, index) => {
        const localX = px + 15 + (index % 2) * 18;
        const localY = py + 21 + Math.floor(index / 2) * 12;
        const sprite = this.add.sprite(localX, localY, 'characters', this.residentFrame(resident))
          .setScale(1.15).setDepth(3);
        if (resident.id === this.playerId) sprite.setTint(0xffe1a8);
        this.objects.push(sprite);
      });
    }
    return inside;
  }

  residentFrame(resident) {
    const role = String(resident.role || '').toLowerCase();
    return (ROLE_VARIANTS[role] ?? 0) * 12;
  }

  distanceTo(a, b) {
    if (!a || !b) return 0;
    return Math.abs((a.x || 0) - (b.x || 0)) + Math.abs((a.y || 0) - (b.y || 0));
  }

}

const config = {
  type: Phaser.AUTO, parent: 'game', width: MAP_WIDTH * TILE, height: MAP_HEIGHT * TILE,
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
