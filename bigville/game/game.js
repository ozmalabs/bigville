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
    const grid = map.grid || [];
    for (let y = 0; y < grid.length; y++) {
      for (let x = 0; x < (grid[y] || []).length; x++) {
        const frame = TILE_FRAMES[grid[y][x]] ?? 0;
        this.objects.push(this.add.image(x * TILE + TILE / 2, y * TILE + TILE / 2, 'tileset', frame).setOrigin(.5));
      }
    }
    for (const building of (map.buildings || [])) {
      const pos = building.position || [building.x || 0, building.y || 0];
      const kind = String(building.type || '').toLowerCase();
      const frame = {house: 0, townhall: 1, market: 4, granary: 10, root_cellar: 11,
        records_office: 16, watchhouse: 17, kitchen: 18, dairy: 19, bakery: 31,
        mill: 33, printshop: 34}[kind] ?? 0;
      this.objects.push(this.add.image(pos[0] * TILE + 24, pos[1] * TILE + 24, 'buildings', frame).setOrigin(.5));
    }
    for (const animal of (snapshot.world.animals || [])) {
      const pos = animal.position || [0, 0];
      const marker = this.add.rectangle(pos[0] * TILE + 8, pos[1] * TILE + 8, 8, 8, 0xd8c37d);
      this.objects.push(marker);
    }
    for (const resident of (snapshot.world.residents || [])) {
      const pos = resident.position || [0, 0];
      const role = String(resident.role || '').toLowerCase();
      const variant = ROLE_VARIANTS[role] ?? 0;
      const frame = variant * 12; // first (down/idle) frame for the role variant
      const sprite = this.add.sprite(pos[0] * TILE + 8, pos[1] * TILE + 8, 'characters', frame);
      if (resident.id === snapshot.player) sprite.setScale(1.3).setTint(0xffe1a8);
      this.objects.push(sprite);
      if (resident.id === snapshot.player) {
        this.cameras.main.centerOn(pos[0] * TILE, pos[1] * TILE);
      }
    }
    this.cameras.main.setBounds(0, 0, map.width * TILE, map.height * TILE);
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
