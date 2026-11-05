"""Compare the founding-town digests of HEAD and of the working tree, section by section (Phase 016a).

    python3 docs/phases/phase016a/compare_digests.py HEAD.json.gz AFTER.json.gz

Prints each top-level section as identical or differing, then every differing leaf with both values.
Whole-file byte identity is checked separately with cmp on the uncompressed outputs.
"""
import gzip
import hashlib
import json
import sys


def load(path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def leaves(a, b, path=""):
    if type(a) is not type(b):
        yield path, a, b
    elif isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                yield f"{path}/{key}", a.get(key, "<missing>"), b.get(key, "<missing>")
            else:
                yield from leaves(a[key], b[key], f"{path}/{key}")
    elif isinstance(a, list):
        if len(a) != len(b):
            yield f"{path} (length)", len(a), len(b)
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                yield from leaves(x, y, f"{path}[{i}]")
    elif a != b:
        yield path, a, b


def main(head_path, after_path):
    head, after = load(head_path), load(after_path)
    for key in head:
        status = "identical" if head[key] == after.get(key) else "DIFFERS"
        print(f"{key}: {status}")
    for key in head:
        for path, x, y in leaves(head[key], after.get(key), key):
            print(f"  {path}: HEAD={x!r} AFTER={y!r}")
    for label, path in (("HEAD", head_path), ("AFTER", after_path)):
        print(f"{label} canonical sha256 {hashlib.sha256(json.dumps(load(path), sort_keys=True).encode()).hexdigest()}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
