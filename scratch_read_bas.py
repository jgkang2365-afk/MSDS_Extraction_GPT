import os

def read_bas():
    bas_file = "Module7.bas"
    if not os.path.exists(bas_file):
        print("파일이 존재하지 않습니다.")
        return
        
    try:
        # CP949(EUC-KR)로 읽어보기
        with open(bas_file, "r", encoding="cp949") as f:
            content = f.read()
        print("[*] cp949 인코딩으로 읽기 성공!")
        lines = content.splitlines()
        # 전체 라인 중 앞의 1000라인 출력
        for idx, line in enumerate(lines[:1000]):
            print(f"{idx+1:03d}: {line}")
    except Exception as e:
        print(f"오류: {e}")

if __name__ == "__main__":
    read_bas()
