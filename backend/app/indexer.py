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


def _pick_target(candidates, caller_path):
    """Generic rule: unique match in the same file, else unique match in the repo."""
    same_file = [chunk_id for chunk_id, path, _ in candidates if path == caller_path]
    if len(same_file) == 1:
        return same_file[0]
    if len(candidates) == 1:
        return candidates[0][0]
    return None


def _build_edges(entries, chunk_ids):
    """Turn each symbol's calls into (src_chunk, dst_name, dst_chunk) edges."""
    by_name = {}       # symbol name -> [(chunk_id, path, qualified name)]
    by_qualified = {}  # qualified name -> [(chunk_id, path)]
    bases_of = {}      # class qualified name -> [parent class names]
    for (path, symbol), chunk_id in zip(entries, chunk_ids):
        by_name.setdefault(symbol.name, []).append((chunk_id, path, symbol.qualified_name))
        by_qualified.setdefault(symbol.qualified_name, []).append((chunk_id, path))
        if symbol.kind == "class":
            bases_of[symbol.qualified_name] = symbol.bases

    edges = []
    for (path, symbol), chunk_id in zip(entries, chunk_ids):
        class_name = symbol.qualified_name.rpartition(".")[0]
        for call_name in symbol.calls:
            target = None

            if call_name in symbol.super_calls and class_name:
                # super().name(): search the parent classes only
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
                candidates = by_name.get(call_name)
                if not candidates:
                    continue  # builtin or third-party call
                target = _pick_target(candidates, path)

            edges.append((chunk_id, call_name, target))
    return edges