import re

# Files that are tests (same pattern the search code uses)
TEST_PATH = re.compile(
    r"(^|/)(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$",
    re.IGNORECASE,
)


def is_test_path(path: str) -> bool:
    return bool(TEST_PATH.search(path))


def _prefer_same_file(options, caller_path):
    """options = [(chunk_id, path), ...]. Pick the one in the caller's file, else the only one."""
    same_file = [chunk_id for chunk_id, path in options if path == caller_path]
    if len(same_file) == 1:
        return same_file[0]
    if len(options) == 1:
        return options[0][0]
    return None


def _method_in_hierarchy(class_name, method, by_qualified, bases_of, caller_path, seen=None):
    """Look for `method` on a class, then on its parent classes."""
    seen = seen if seen is not None else set()
    if class_name in seen:
        return None
    seen.add(class_name)

    options = by_qualified.get(f"{class_name}.{method}")
    if options:
        return _prefer_same_file(options, caller_path)
    for base in bases_of.get(class_name, []):
        hit = _method_in_hierarchy(base, method, by_qualified, bases_of, caller_path, seen)
        if hit is not None:
            return hit
    return None


def build_edges(entries, chunk_ids):
    """Turn each symbol's calls into (src_chunk, dst_name, dst_chunk) edges.

    entries   = [(file_path, Symbol), ...]
    chunk_ids = the database id of each entry, in the same order.
    dst_chunk is None when the call cannot be pinned to one function.
    """
    by_name = {}       # symbol name -> [(chunk_id, path)]
    by_qualified = {}  # qualified name -> [(chunk_id, path)]
    bases_of = {}      # class qualified name -> [parent class names]
    for (path, symbol), chunk_id in zip(entries, chunk_ids):
        by_name.setdefault(symbol.name, []).append((chunk_id, path))
        by_qualified.setdefault(symbol.qualified_name, []).append((chunk_id, path))
        if symbol.kind == "class":
            bases_of[symbol.qualified_name] = symbol.bases

    edges = []
    for (path, symbol), chunk_id in zip(entries, chunk_ids):
        class_name = symbol.qualified_name.rpartition(".")[0]
        caller_is_test = is_test_path(path)

        for call_name in symbol.calls:
            if call_name in symbol.super_calls and class_name:
                # super().name(): search the parent classes only
                target = None
                for base in bases_of.get(class_name, []):
                    target = _method_in_hierarchy(base, call_name, by_qualified, bases_of, path)
                    if target is not None:
                        break
                if target is None:
                    continue  # the parent is outside this repo (e.g. Exception)

            elif call_name in symbol.self_calls and class_name:
                # self.name(): this class first, then its parents
                target = _method_in_hierarchy(class_name, call_name, by_qualified, bases_of, path)
                if target is None:
                    continue  # an attribute, or defined outside this repo: do not guess

            else:
                # Any other call: link only if exactly one function in the repo has this name
                candidates = by_name.get(call_name, [])
                if not caller_is_test:
                    candidates = [c for c in candidates if not is_test_path(c[1])]
                if not candidates:
                    continue  # builtin or third-party call
                target = candidates[0][0] if len(candidates) == 1 else None

            edges.append((chunk_id, call_name, target))
    return edges