import tree_sitter_python as tspython
from tree_sitter import Language, Parser

# Load the Python grammar and build a parser from it
PY_LANGUAGE = Language(tspython.language())
parser = Parser(PY_LANGUAGE)

SAMPLE = b'''
import os

class AuthService:
    """Handles login."""

    def login(self, user):
        return self.verify(user)

def helper(x):
    return x + 1
'''


def show(node, depth=0):
    """Print a node and everything inside it, indented by depth."""
    if not node.is_named:
        return

    extra = ""
    if node.type == "identifier":
        extra = "  -> " + node.text.decode()

    first_line = node.start_point[0] + 1
    last_line = node.end_point[0] + 1
    print("  " * depth + f"{node.type} (lines {first_line}-{last_line}){extra}")

    for child in node.children:
        show(child, depth + 1)


tree = parser.parse(SAMPLE)
show(tree.root_node)