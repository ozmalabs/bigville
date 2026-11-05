"""data_view.py -- the entity modules bound to any data pack.

The four entity modules (world_affordances, shared_frames, population, bigville_entities) bind
their tables from the "bigville" pack when they are imported, and their functions read those
module globals. To use another pack, this module runs the same source again in fresh namespaces,
with `_PACK_NAME` seeded to that pack's directory. Every table and every function in a view then
reads that pack, and the default modules stay as they are.

    entities()                 -> domains.bigville_entities (the default pack, the real module)
    entities("test_hamlet")    -> a module-like view over packs/test_hamlet/

Inside a view, `from domains.world_affordances import ...` (and the other entity modules) resolve
to the view's own namespaces, so the four modules of one view see one another and nothing else.
Views are cached per pack directory. Each view is a separate namespace, so tables of one pack
never appear in another pack's view.
"""
from __future__ import annotations

import builtins
import importlib
import os
import types

from domains.pack import load_pack

DEFAULT_PACK = "bigville"
# Import order matters: a module may import names from the modules before it.
MODULES = ("world_affordances", "shared_frames", "population", "bigville_entities")

_VIEWS = {}   # pack directory -> {"domains.<module>": module-like object}


def entities(pack=None):
    """The combined entity view (what `from domains import bigville_entities` gives) for `pack`.

    `pack` is a pack name, a pack directory, or None for the default pack."""
    default = load_pack(DEFAULT_PACK)
    loaded = default if pack is None else load_pack(pack)
    if loaded.path == default.path:
        return importlib.import_module("domains.bigville_entities")
    return _build(loaded)["domains.bigville_entities"]


def world_entities(world):
    """The entity view a world reads (`world.E`, set from its data pack), or the default view."""
    view = getattr(world, "E", None)
    return view if view is not None else entities()


def _namespace_builtins(modules):
    """Builtins for a view's code: `domains.<module>` imports resolve to the view's own modules."""
    table = dict(vars(builtins))
    real_import = builtins.__import__

    def view_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level == 0 and name in modules:
            return modules[name]
        return real_import(name, globals, locals, fromlist, level)

    table["__import__"] = view_import
    return table


def _build(loaded):
    if loaded.path in _VIEWS:
        return _VIEWS[loaded.path]
    real_dir = os.path.dirname(os.path.abspath(importlib.import_module("domains.world_affordances").__file__))
    modules = {}
    for short in MODULES:
        fq = f"domains.{short}"
        mod = types.ModuleType(f"{fq}[{loaded.name}]")
        mod.__file__ = os.path.join(real_dir, f"{short}.py")
        mod.__package__ = "domains"
        mod.__dict__["_PACK_NAME"] = loaded.path
        mod.__dict__["__builtins__"] = _namespace_builtins(modules)
        modules[fq] = mod
    _VIEWS[loaded.path] = modules
    try:
        for short in MODULES:
            fq = f"domains.{short}"
            with open(modules[fq].__file__, encoding="utf-8") as fh:
                code = compile(fh.read(), modules[fq].__file__, "exec")
            exec(code, modules[fq].__dict__)
    except Exception:
        _VIEWS.pop(loaded.path, None)
        raise
    return modules
