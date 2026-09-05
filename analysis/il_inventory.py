"""Parse the monodis IL dump of Assembly-CSharp.dll into a type inventory.

Input:  scratch/full_il.txt  (monodis output, 13.3 MB, not in git)
Output (when run as a script): docs/sfs_reference/inventory.json

Emits one record per `.class` declaration: name, namespace, kind, extends,
nested flag, parent type, generic arity, line number in the dump, and counts
of `.method` / `.field` declarations. Compiler-generated types are kept here
and filtered downstream by name.

`parse_il()` is also importable directly (e.g. by sfsprobe_mcp/server.py's
deep_search, MCP overhaul Checkpoint 5) to get the same per-type records
against a different IL dump path, optionally with `capture_members=True` to
also collect each type's real method/field names (not just counts) --
without triggering this file's own docs/sfs_reference/inventory.json
write, which only happens under `if __name__ == "__main__"` below. That
guard matters: docs/sfs_reference/ is a work-in-progress migration tree
with its own INDEX.md/manifest.json built from inventory.json (see
docs/sfs_reference/INVENTORY.md's own status section) -- importing this
module must never have the side effect of regenerating it.

Regenerate the input with:
  monodis --output=scratch/full_il.txt <Managed>/Assembly-CSharp.dll
Pinned build: md5 cbad19d24f73252e5a7acd6b88cfa9c1 (SFS 1.6.00.16).
"""

import re, json, sys, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_IL_PATH = os.path.join(ROOT, "scratch", "full_il.txt")
DEFAULT_INVENTORY_OUT = os.path.join(ROOT, "docs", "sfs_reference", "inventory.json")

ns_re = re.compile(r'^\.namespace\s+(.+?)\s*$')
class_re = re.compile(r'^(\s*)\.class\s+(.*)$')
end_re = re.compile(r'^\s*\}\s*//\s*end of class\s+(.+?)\s*$')
meth_re = re.compile(r'^(\s*)\.method\s+(.*)$')
field_re = re.compile(r'^(\s*)\.field\s+(.*)$')

_CLASS_KWSET = {
    'public', 'private', 'nested', 'auto', 'ansi', 'sealed', 'abstract', 'beforefieldinit',
    'serializable', 'interface', 'explicit', 'sequential', 'import', 'specialname',
    'rtspecialname', 'family', 'assembly', 'famandassem', 'famorassem', 'unicode', 'autochar',
    'windowsruntime', 'forwardref', 'literal',
}


def _parse_member_name(lines, i, max_lookahead=6):
    """Given `lines` and the index `i` of a `.method`/`.field` declaration's
    first line, recovers the real member name. A `.field` decl is one line
    (name is the last token); a `.method` decl splits its attributes from
    the return-type/name/param-list onto a continuation line beginning
    `default ...` (docs/sfs_source_reference.md §A2 gotcha #1), so this
    concatenates forward until a `(` shows up, then takes the last token
    before it. Not a full IL parser -- good enough for identifier search,
    not for reconstructing exact signatures."""
    decl = lines[i]
    j = i
    while '(' not in decl and j + 1 < len(lines) and j < i + max_lookahead:
        j += 1
        decl += ' ' + lines[j]
    idx = decl.find('(')
    head = decl[:idx] if idx != -1 else decl
    toks = head.split()
    if not toks:
        return None
    raw = toks[-1]
    if raw.startswith("'"):
        end = raw.rfind("'")
        name = raw[1:end] if end > 0 else raw.strip("'")
    else:
        name = raw
    return name.split('`')[0] or None


def parse_il(il_path=DEFAULT_IL_PATH, capture_members=False):
    """Parses a monodis IL dump into one record per `.class` declaration:
    name, namespace, kind, extends, nested flag, parent fq name, generic
    arity, line number, and `.method`/`.field` counts. Compiler-generated
    types are included (filter with `is_compiler_generated` below).

    `capture_members=True` additionally populates each record's
    `method_names`/`field_names` with the real identifiers found (not just
    counts) -- the member-level index deep_search needs to match a query
    like "gimbal" against `EngineModule.gimbal`/`RecalculateGimbal`, since
    a query term frequently isn't the type name itself. Off by default so
    a plain call behaves exactly as this module always has.
    """
    types = []
    stack = []
    cur_ns = ""
    lines = open(il_path, encoding='utf-8', errors='replace').read().split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        m = ns_re.match(line)
        if m:
            cur_ns = m.group(1).strip()
            i += 1; continue
        m = class_re.match(line)
        if m:
            indent, rest = m.group(1), m.group(2)
            # class decl may span lines until 'extends' or '{'
            decl = rest
            j = i
            while '{' not in lines[j] and j + 1 < len(lines) and not lines[j + 1].strip().startswith('.'):
                j += 1
                decl += ' ' + lines[j].strip()
                if lines[j].strip().startswith('{'): break
            # parse flags/name from `rest` (first line) - name is last token before extends/implements
            head = rest.strip()
            toks = head.split()
            idx = 0
            while idx < len(toks) and (toks[idx] in _CLASS_KWSET or toks[idx].startswith('bestfit') or toks[idx].startswith('charmaperror')):
                idx += 1
            raw = toks[idx] if idx < len(toks) else toks[-1]
            if raw.startswith("'"):
                end = raw.index("'", 1)
                name = raw[1:end]
                name = name.split('`')[0]
            else:
                name = raw.split('<')[0].split('`')[0]
            generic_arity = 0
            mg = re.search(r"`(\d+)", raw)
            if mg: generic_arity = int(mg.group(1))
            nested = 'nested' in toks
            kind = 'interface' if 'interface' in toks else 'class'
            if 'abstract' in toks and 'sealed' in toks and kind == 'class':
                kind = 'static class'
            elif 'abstract' in toks and kind == 'class':
                kind = 'abstract class'
            extends = ''
            # look ahead for extends
            k = i
            while k < min(i + 4, len(lines)):
                s = lines[k].strip()
                if s.startswith('extends'):
                    extends = s[len('extends'):].strip()
                    break
                if s == '{': break
                k += 1
            if 'System.ValueType' in extends: kind = 'struct'
            if 'System.Enum' in extends: kind = 'enum'
            if 'MulticastDelegate' in extends: kind = 'delegate'
            entry = {'name': name, 'ns': cur_ns, 'kind': kind, 'extends': extends,
                     'nested': nested, 'generic_arity': generic_arity, 'parent': stack[-1]['fq'] if stack else None,
                     'line': i + 1, 'methods': 0, 'fields': 0, 'indent': len(indent)}
            if capture_members:
                entry['method_names'] = []
                entry['field_names'] = []
            entry['fq'] = (entry['parent'] + '/' + name) if entry['parent'] else ((cur_ns + '.' + name) if cur_ns else name)
            stack.append(entry)
            types.append(entry)
            i += 1; continue
        m = end_re.match(line)
        if m:
            if stack: stack.pop()
            i += 1; continue
        if stack:
            m = meth_re.match(line)
            if m:
                stack[-1]['methods'] += 1
                if capture_members:
                    name = _parse_member_name(lines, i)
                    if name:
                        stack[-1]['method_names'].append(name)
            else:
                m = field_re.match(line)
                if m:
                    stack[-1]['fields'] += 1
                    if capture_members:
                        name = _parse_member_name(lines, i)
                        if name:
                            stack[-1]['field_names'].append(name)
        i += 1
    return types


def is_compiler_generated(t):
    n = t["name"]
    return (n.startswith("<") or "__DisplayClass" in n or n == ""
            or n.startswith("__StaticArrayInitType")
            or n == "PrivateImplementationDetails")


if __name__ == "__main__":
    types = parse_il(DEFAULT_IL_PATH, capture_members=False)
    real = [t for t in types if not is_compiler_generated(t)]

    # Annotate against the pre-split single-file reference, so INVENTORY.md can
    # report how much of the inventory that file already covers. Two bars:
    # a named heading (real per-type content) vs. any mention (upper bound).
    old_doc_path = os.path.join(ROOT, "docs", "sfs_source_reference.md")
    if os.path.exists(old_doc_path):
        doc = open(old_doc_path, encoding="utf-8").read()
        heads = " | ".join(l for l in doc.split("\n") if re.match(r"^#{2,4} ", l))
    else:
        doc = heads = ""
    for t in real:
        t.pop("indent", None)
        pat = r"(?<![A-Za-z0-9_])" + re.escape(t["name"]) + r"(?![A-Za-z0-9_])"
        t["in_old_doc_heading"] = bool(re.search(pat, heads))
        t["mentioned_in_old_doc"] = bool(re.search(pat, doc))

    json.dump(real, open(DEFAULT_INVENTORY_OUT, "w"), indent=1)
    print("class declarations:", len(types), "| real types:", len(real))
    from collections import Counter
    c = Counter(t['ns'] for t in real)
    print("namespaces:", len(c))
