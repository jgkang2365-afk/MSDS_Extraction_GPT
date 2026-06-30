with open("smu_gui.py", "r", encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        if "venv_312" in line or "python" in line.lower() or "sys.executable" in line:
            print(f"{i}: {line.strip()}")
