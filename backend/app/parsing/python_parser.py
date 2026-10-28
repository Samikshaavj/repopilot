import ast

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from .models import ImportRef, ParsedFile, Symbol

_LANGUAGE = Language(tspython.language())
_parser = Parser(_LANGUAGE)


def _text(node: Node, src: bytes) -> str:
    """The exact source text a node covers."""
    return src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _docstring(body: Node | None, src: bytes) -> str | None:
    """A docstring is a string that is the first statement in the body."""
    if body is None or body.named_child_count == 0:
        return None
    first = body.named_children[0]
    if first.type != "expression_statement" or first.named_child_count == 0:
        return None
    expr = first.named_children[0]
    if expr.type != "string":
        return None
    raw = _text(expr, src)
    try:
        value = ast.literal_eval(raw)
        return value.strip() if isinstance(value, str) else None
    except (ValueError, SyntaxError):
        return raw.strip("\"'").strip()


def _calls_in(node: Node, src: bytes) -> list[str]:
    """Names of functions called anywhere inside `node` (no duplicates)."""
    names: list[str] = []
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type == "call":
            fn = current.child_by_field_name("function")
            if fn is not None:
                if fn.type == "identifier":                # helper(x)
                    names.append(_text(fn, src))
                elif fn.type == "attribute":               # self.verify(x)
                    attr = fn.child_by_field_name("attribute")
                    if attr is not None:
                        names.append(_text(attr, src))
        stack.extend(current.children)
    return list(dict.fromkeys(names))


def _walk(node, src, file_path, scope, in_class, symbols, imports):
    for child in node.children:
        outer = child          # the node whose lines we report
        target = child
        if child.type == "decorated_definition":
            # "@decorator + def/class": the real definition is inside
            target = child.child_by_field_name("definition") or child

        if target.type in ("function_definition", "class_definition"):
            name_node = target.child_by_field_name("name")
            body = target.child_by_field_name("body")
            if name_node is None or body is None:
                continue

            name = _text(name_node, src)
            is_class = target.type == "class_definition"
            if is_class:
                kind = "class"
            elif in_class:
                kind = "method"
            else:
                kind = "function"

            signature = src[target.start_byte:body.start_byte].decode(
                "utf-8", errors="replace"
            ).strip()

            symbols.append(Symbol(
                kind=kind,
                name=name,
                qualified_name=".".join(scope + [name]),
                file_path=file_path,
                start_line=outer.start_point[0] + 1,
                end_line=outer.end_point[0] + 1,
                signature=signature,
                docstring=_docstring(body, src),
                code=_text(outer, src),
                calls=[] if is_class else _calls_in(body, src),
            ))

            # Look inside for methods and nested functions
            _walk(body, src, file_path, scope + [name], is_class, symbols, imports)

        elif child.type in ("import_statement", "import_from_statement"):
            imports.append(ImportRef(file_path, child.start_point[0] + 1, _text(child, src)))

        else:
            # Keep searching inside things like `if` and `try` blocks
            _walk(child, src, file_path, scope, in_class, symbols, imports)


def parse_python(source, file_path: str) -> ParsedFile:
    """Parse Python source (str or bytes) into symbols and imports."""
    src = source.encode("utf-8") if isinstance(source, str) else source
    tree = _parser.parse(src)
    symbols: list[Symbol] = []
    imports: list[ImportRef] = []
    _walk(tree.root_node, src, file_path, [], False, symbols, imports)
    return ParsedFile(file_path=file_path, language="python", symbols=symbols, imports=imports)