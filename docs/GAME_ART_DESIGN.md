# Bigville game-art and scale contract

This is the sizing contract for the standalone game client. The simulation
does not own pixels; it owns map cells, building placements, actors, items,
clothing, and physical states. The renderer assembles those things from the
asset manifest.

## World units

- One map cell is one walkable world square, approximately one metre.
- The logical terrain grid is 16x16 pixels per cell and is displayed at 2x for
  readable pixel-art silhouettes.
- A resident occupies one cell, with their feet anchored at the cell centre's
  lower edge. A held item shares that anchor and is drawn as a separate layer.
- A standard building occupies 3x3 cells and is therefore 48x48 logical
  pixels. Larger or smaller buildings use integer cell footprints and are
  assembled from the reusable building-part atlas; authored 3x3 sprites are
  an optional quality tier, not a geometry constraint.
- Furniture, animals, crops, fences, and dropped items are placed on cell
  anchors or half-cell offsets; none are baked into a map illustration.

## Camera and zoom

- The base viewport is 52x40 cells (832x640 logical pixels), but the world
  dimensions come from the scenario's exported map.
- The camera is pixel-art nearest-neighbour at all zoom levels.
- The presentation is square-cell 3/4 top-down: the terrain stays square,
  while upright facades, roof overhangs, shadows, and row depth create the
  perspective. It is not a diamond-isometric projection.
- Supported zoom is 0.75x through 3x. 1.25x is the default inspection view,
  2x is the close interaction view, and 3x is for checking inventory, clothing,
  tools, and room contents.
- Camera movement operates in world pixels, not CSS pixels. The viewport may
  show more or less of a scenario without changing simulation coordinates.

## Asset layers

Every rendered object has an explicit layer and state:

1. terrain tile (`16x16`, scenario grid), including cardinally masked
   path/shore transitions so corners and junctions are not forced to be square
2. small world prop or animal (`16x16` or an integer multiple), placed as a
   transparent overlay so flowers, verges, reeds, benches, and work details
   can vary independently of the map geometry
3. building structure with roof (assembled from `16x16` parts or a matching
   `48x48` authored frame)
4. building interior without roof (matching footprint, with reusable floor,
   wall, door, furniture, and badge parts)
5. actor body/clothes (`16x16`, role/age variant)
6. held item (`16x16` item atlas frame, anchored to the hand)
7. UI/inspection overlays

Roof-on and roof-off are paired building assets. The renderer selects roof-off
when a resident is inside or when an inspector explicitly opens a building;
the roof-on version remains the default. Interior assets are matched by
building type, not replaced by a generic village background.

## Item and clothing rules

- Every key in `domains.bigville_entities.ITEMS` must have one entry in the
  item atlas and manifest.
- A 16x16 item icon must have a readable silhouette at 1x and remain legible
  at 2x/3x. The atlas is also used for inventory UI and held-item overlays.
- Discrete tools are distinct physical instances. If an actor holds a `pick`,
  the actor renderer draws the pick instance; inventory inspection lists it
  separately from bulk stock.
- Worn garments are separate from carried stock. The actor payload exposes
  both `held_items` and `worn`, so UI and future clothing overlays can inspect
  the physical state without guessing from role.

## Data boundary

The manifest is generated from the entity data. New items, building types, or
terrain features must fail an asset-coverage check until they have a sprite
entry. Scenarios provide map grids and placements; they never require a new
background image.

`style_source_village.png` is the recovered original village rendering and is
the primary reference for palette, silhouette density, tall facades, irregular
paths, water edges, and prop placement. It is never used as a runtime
backdrop. The terrain and building source sheets are converted by
`tools/build_style_assets.py` into assembled runtime atlases:
`style_tiles.png`, `style_props.png`, `style_large_props.png`, and
`style_buildings.png`, described by `style_manifest.json`. This keeps the
original visual language while allowing every scenario to provide a different
map and building arrangement. `stardew_like_art_direction.png`,
`pixel_art_art_direction.png`, and `terrain_art_direction.png` remain useful
art-direction studies.
