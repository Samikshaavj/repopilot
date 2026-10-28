from app.callgraph import build_edges
from app.parsing.models import Symbol


def make(name, qualified, kind="method", calls=(), self_calls=(), super_calls=(), bases=()):
    return Symbol(
        kind=kind, name=name, qualified_name=qualified, file_path="",
        start_line=1, end_line=2, signature="", docstring=None, code="",
        calls=list(calls), self_calls=list(self_calls),
        super_calls=list(super_calls), bases=list(bases),
    )


def test_module_call_is_not_linked_to_same_named_method():
    # _CompactJSON.loads calls json.loads(), the standard library, not itself
    entries = [
        ("src/_json.py", make("loads", "_CompactJSON.loads", calls=["loads"])),
        ("src/serializer.py", make("loads", "Serializer.loads")),
    ]
    assert build_edges(entries, [1, 2]) == [(1, "loads", None)]


def test_self_call_to_an_attribute_does_not_link_to_a_test_helper():
    # self.signer(...) is an attribute holding a class, not a method
    entries = [
        ("src/serializer.py", make("make_signer", "Serializer.make_signer",
                                   calls=["signer"], self_calls=["signer"])),
        ("tests/test_signer.py", make("signer", "TestSigner.signer")),
    ]
    assert build_edges(entries, [1, 2]) == []


def test_self_and_super_calls_resolve_through_inheritance():
    entries = [
        ("a.py", make("Child", "Child", kind="class", bases=["Base"])),
        ("a.py", make("Base", "Base", kind="class")),
        ("a.py", make("run", "Child.run", calls=["run", "helper"],
                      self_calls=["helper"], super_calls=["run"])),
        ("a.py", make("helper", "Child.helper")),
        ("a.py", make("run", "Base.run")),
    ]
    edges = build_edges(entries, [1, 2, 3, 4, 5])
    assert (3, "helper", 4) in edges   # self.helper() -> Child.helper
    assert (3, "run", 5) in edges      # super().run() -> Base.run