import csv
import os

class ExposureLookup:
    """
    제공된 '화학물질 노출기준_고시자료.csv' 파일을 로드하여 CAS 번호로 데이터를 조회하는 모듈.
    """
    def __init__(self, csv_path="화학물질 노출기준_고시자료.csv"):
        self.csv_path = csv_path
        self.data = {}
        self._load_data()

    def _load_data(self):
        if not os.path.exists(self.csv_path):
            print(f"  [*] [Warning] CSV 파일을 찾을 수 없습니다: {self.csv_path}")
            return

        # 한국어 윈도우 환경이므로 cp949 인코딩 시도 후 실패 시 utf-8-sig 시도
        encodings = ['cp949', 'utf-8-sig', 'utf-8']
        
        success = False
        for enc in encodings:
            try:
                with open(self.csv_path, mode='r', encoding=enc) as f:
                    # 헤더: 일련번호,CAS No,유해물질의 명칭_국문,유해물질의 명칭_영문,화학식,노출기준_TWA_ppm,노출기준_TWA_㎎/㎥,노출기준_STEL_ppm,노출기준_STEL_㎎/㎥
                    reader = csv.DictReader(f)
                    for row in reader:
                        # 'CAS No' 컬럼 또는 'Cas No. 추출값' 사용
                        cas = row.get("CAS No", "").strip()
                        if not cas:
                            cas = row.get("Cas No. 추출값", "").strip()
                        
                        if cas:
                            self.data[cas] = {
                                "twa_ppm": row.get("노출기준_TWA_ppm", "-"),
                                "twa_mg": row.get("노출기준_TWA_㎎/㎥", "-"),
                                "stel_ppm": row.get("노출기준_STEL_ppm", "-"),
                                "stel_mg": row.get("노출기준_STEL_㎎/㎥", "-"),
                                "c_ppm": "-", # 제공된 CSV에 C 기준은 별도 컬럼이 안 보임
                                "c_mg": "-"
                            }
                print(f"  [OK] 노출기준 CSV 로드 완료 ({enc}): {len(self.data)}건")
                success = True
                break
            except (UnicodeDecodeError, KeyError):
                continue
            except Exception as e:
                print(f"  [ERR] CSV 로드 중 예외 발생 ({enc}): {e}")
                break
        
        if not success:
            print("  [ERR] 모든 인코딩 시도 실패. CSV 데이터를 로드하지 못했습니다.")

    def lookup(self, cas_no):
        """CAS 번호로 노출기준 조회. 데이터가 없으면 None 반환."""
        if not cas_no: return None
        return self.data.get(cas_no)

if __name__ == "__main__":
    lookup = ExposureLookup()
    # 테스트: 에탄올(64-17-5) 등 샘플 조회
    test_cas = "64-18-6" # 개미산 (CSV 예제 2번)
    print(f"조회 결과 ({test_cas}): {lookup.lookup(test_cas)}")
