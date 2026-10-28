from app.parsing import parse_python

SAMPLE = '''
import os
from pathlib import Path

def top(x):
    """Top-level helper."""
    return helper(x)

@decorator
class AuthService:
    """Handles login."""

    def login(self, user):
        """Log a user in."""
        return self.verify(user)

    def verify(self, user):
        return check_password(user)

if True:
    def conditional():
        pass
'''


def test_extracts_symbols_and_scopes():
    parsed = parse_python(SAMPLE, "auth.py")
    by_name = {s.qualified_name: s for s in parsed.symbols}
    assert set(by_name) == {
        "top", "AuthService", "AuthService.login", "AuthService.verify", "conditional",
    }
    assert by_name["AuthService"].kind == "class"
    assert by_name["AuthService.login"].kind == "method"
    assert by_name["top"].kind == "function"


def test_docstrings_signatures_and_calls():
    parsed = parse_python(SAMPLE, "auth.py")
    by_name = {s.qualified_name: s for s in parsed.symbols}
    assert by_name["top"].docstring == "Top-level helper."
    assert by_name["AuthService.login"].signature.startswith("def login(self, user)")
    assert by_name["top"].calls == ["helper"]
    assert by_name["AuthService.login"].calls == ["verify"]
    assert by_name["AuthService.verify"].calls == ["check_password"]


def test_decorator_included_and_lines_start_at_one():
    parsed = parse_python(SAMPLE, "auth.py")
    cls = next(s for s in parsed.symbols if s.name == "AuthService")
    assert cls.code.startswith("@decorator")
    assert cls.start_line == 9


def test_imports_collected():
    parsed = parse_python(SAMPLE, "auth.py")
    assert [i.text for i in parsed.imports] == ["import os", "from pathlib import Path"]

CLASS_SAMPLE = '''
class Base:
    def run(self):
        pass

class Child(Base):
    def run(self):
        super().run()
        self.helper()

    def helper(self):
        pass
'''


def test_call_kinds_and_bases():
    parsed = parse_python(CLASS_SAMPLE, "x.py")
    by_name = {s.qualified_name: s for s in parsed.symbols}
    assert by_name["Child"].bases == ["Base"]
    run = by_name["Child.run"]
    assert run.super_calls == ["run"]
    assert run.self_calls == ["helper"]
    assert set(run.calls) == {"run", "helper"}