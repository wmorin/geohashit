MAX_JSON_DEPTH = 64


def validate_json_depth(value):
    """Bound container nesting independently of the interpreter's recursion limit."""
    pending = [(value, 0)]
    while pending:
        node, depth = pending.pop()
        if not isinstance(node, (dict, list, tuple)):
            continue
        depth += 1
        if depth > MAX_JSON_DEPTH:
            raise ValueError('JSON nesting exceeds the maximum depth of %s' % MAX_JSON_DEPTH)
        children = node.values() if isinstance(node, dict) else node
        pending.extend((child, depth) for child in children)
