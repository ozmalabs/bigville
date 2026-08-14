/* Bigville's browser client. Phaser renders the world; Python remains the authority. */
const TILE = 16;
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
  constructor() { super('bigville'); this.objects = []; }

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
    const allResidents = snapshot.world.residents || [];
    const playerResident = allResidents.find((resident) => resident.id === snapshot.player);
    const occupiedResidents = this.drawOccupiedInteriors(map.buildings || [], allResidents);
    const visibleResidents = allResidents.filter((resident) => {
      if (occupiedResidents.has(resident.id)) return false;
      if (resident.id === snapshot.player || !playerResident) return true;
      return Math.abs((resident.x || 0) - (playerResident.x || 0)) <= 5 &&
        Math.abs((resident.y || 0) - (playerResident.y || 0)) <= 5;
    });
    for (const resident of visibleResidents) {
      const pos = resident.position || [0, 0];
      const role = String(resident.role || '').toLowerCase();
      const variant = ROLE_VARIANTS[role] ?? 0;
      const frame = variant * 12; // first (down/idle) frame for the role variant
      const sprite = this.add.sprite(pos[0] * TILE + 8, pos[1] * TILE + 8, 'characters', frame).setDepth(3);
      if (resident.id === snapshot.player) sprite.setScale(1.45).setTint(0xffe1a8);
      this.objects.push(sprite);
      if (resident.id === snapshot.player) {
        this.cameras.main.centerOn(pos[0] * TILE, pos[1] * TILE);
      }
    }
    this.cameras.main.setBounds(0, 0, width, height);
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
    }
    return inside;
  }

}

const config = {
  type: Phaser.AUTO, parent: 'game', width: 960, height: 640,
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
  state = await response.json(); renderAll();
};

getState().then((loaded) => { state = loaded; renderAll(); }).catch((error) => { $('status').textContent = error.message; });
