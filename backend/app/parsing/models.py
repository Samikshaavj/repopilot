from dataclasses import dataclass, field


@dataclass
class Symbol:
    kind: str            # "function", "method" or "class"
    name: str            # "login"
    qualified_name: str  # "AuthService.login"
    file_path: str       # path inside the repo
    start_line: int      # first line (1 = first line of the file)
    end_line: int
    signature: str       # "def login(self, user):"
    docstring: str | None
    code: str            # the full source of the symbol
    calls: list[str] = field(default_factory=list)  # names it calls


@dataclass
class ImportRef:
    file_path: str
    line: int
    text: str            # the import statement as written


@dataclass
class ParsedFile:
    file_path: str
    language: str
    symbols: list[Symbol]
    imports: list[ImportRef]