import ast

with open("msds_engine_v6.py", "r", encoding="utf-8") as f:
    tree = ast.parse(f.read())

for node in tree.body:
    if isinstance(node, ast.ClassDef) and node.name == "MSDSOfflineTester":
        print(f"Class: {node.name}, Start: {node.lineno}, End: {node.end_lineno}")
        for subnode in node.body:
            if isinstance(subnode, ast.FunctionDef):
                print(f"  Method: {subnode.name}, Start: {subnode.lineno}, End: {subnode.end_lineno}")





