import os

def convert():
    bas_file = "Module7.bas"
    out_file = "scratch/Module7.txt"
    os.makedirs("scratch", exist_ok=True)
    try:
        with open(bas_file, "r", encoding="cp949", errors="replace") as f:
            content = f.read()
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(content)
        print("성공적으로 scratch/Module7.txt로 변환했습니다.")
    except Exception as e:
        print(f"오류: {e}")

if __name__ == "__main__":
    convert()
