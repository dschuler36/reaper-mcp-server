"""Structural tokenizer for REAPER project (.RPP) files.

An RPP file is a tree of chunks. A chunk opens with a line beginning with '<'
and closes with a line that is exactly '>'. Everything else is a token line
belonging to the innermost open chunk::

    <TRACK {GUID}
      NAME "my track"
      <ITEM
        POSITION 1.0
      >
    >

Parsing this with a flat line scanner is what caused items to be silently
dropped: any chunk the scanner did not recognise still emitted a '>' that was
mistaken for the end of the enclosing track. Tokenizing structurally first
means unknown chunks (``<SOURCE MIDI``, ``<VOLENV2``, future REAPER additions)
are consumed correctly instead of corrupting parser state.

Base64 payload lines cannot be confused for structure: the base64 alphabet is
``A-Za-z0-9+/=``, so a payload line never begins with '<' or '>'.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Union

QUOTE_CHARS = ('"', "'", '`')


def split_tokens(line: str) -> List[str]:
    """Split an RPP line into tokens, honouring REAPER's quoting.

    REAPER quotes a string with '"', falling back to "'" and then '`' when the
    string itself contains the preferred quote character. Quotes are stripped
    from the returned tokens.
    """
    tokens: List[str] = []
    i, n = 0, len(line)
    while i < n:
        while i < n and line[i].isspace():
            i += 1
        if i >= n:
            break
        if line[i] in QUOTE_CHARS:
            quote = line[i]
            end = line.find(quote, i + 1)
            if end == -1:
                tokens.append(line[i + 1:])
                break
            tokens.append(line[i + 1:end])
            i = end + 1
        else:
            end = i
            while end < n and not line[end].isspace():
                end += 1
            tokens.append(line[i:end])
            i = end
    return tokens


@dataclass
class Chunk:
    """One ``<NAME ...> ... >`` block.

    ``body`` preserves the original interleaving of token lines and child
    chunks, which matters wherever position carries meaning -- take
    boundaries inside an ITEM, or BYPASS preceding its VST inside an FXCHAIN.
    """

    name: str
    args: List[str] = field(default_factory=list)
    body: List[Union[str, 'Chunk']] = field(default_factory=list)

    @property
    def lines(self) -> List[str]:
        return [entry for entry in self.body if isinstance(entry, str)]

    @property
    def children(self) -> List['Chunk']:
        return [entry for entry in self.body if isinstance(entry, Chunk)]

    def find(self, name: str) -> Optional['Chunk']:
        """First direct child chunk with this name."""
        for child in self.children:
            if child.name == name:
                return child
        return None

    def find_all(self, name: str) -> List['Chunk']:
        return [child for child in self.children if child.name == name]

    def tokens(self, keyword: str) -> Optional[List[str]]:
        """Tokens after ``keyword`` on its first occurrence, or None."""
        for line in self.lines:
            parts = split_tokens(line)
            if parts and parts[0] == keyword:
                return parts[1:]
        return None

    def tokens_all(self, keyword: str) -> List[List[str]]:
        """Tokens after ``keyword`` for every occurrence, in file order."""
        results = []
        for line in self.lines:
            parts = split_tokens(line)
            if parts and parts[0] == keyword:
                results.append(parts[1:])
        return results


def tokenize(lines: List[str]) -> Chunk:
    """Build a chunk tree from RPP lines. Returns a synthetic ROOT chunk."""
    root = Chunk(name='ROOT')
    stack: List[Chunk] = [root]

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith('<'):
            parts = split_tokens(line[1:])
            child = Chunk(name=parts[0] if parts else '', args=parts[1:])
            stack[-1].body.append(child)
            stack.append(child)
        elif line == '>':
            # A stray '>' at the top level would otherwise unwind the root.
            if len(stack) > 1:
                stack.pop()
        else:
            stack[-1].body.append(line)

    return root


def tokenize_file(file_path: str) -> Chunk:
    with open(file_path, 'r', encoding='utf-8', errors='replace') as handle:
        return tokenize(handle.read().splitlines())
