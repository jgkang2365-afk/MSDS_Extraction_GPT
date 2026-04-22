import json
import os

class SubstanceHelper:
    """substance_whitelist.json을 로드하여 CAS 번호 기반 규제 정보를 제공합니다."""
    
    _instance = None
    _data = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SubstanceHelper, cls).__new__(cls)
            cls._instance._load_data()
        return cls._instance

    def _load_data(self):
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'substance_whitelist.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
            except Exception as e:
                print(f"[SubstanceHelper] 데이터 로드 실패: {e}")
                self._data = {}
        else:
            print(f"[SubstanceHelper] 파일을 찾을 수 없음: {config_path}")

    def get_info(self, cas):
        """CAS 번호를 키로 하여 정보를 반환합니다. (정규화 포함)"""
        clean_cas = str(cas).strip()
        return self._data.get(clean_cas)

    def is_measurement_target(self, cas):
        info = self.get_info(cas)
        return info.get("is_measurement_target", False) if info else False

    def is_special_checkup_target(self, cas):
        info = self.get_info(cas)
        return info.get("is_special_checkup_target", False) if info else False

    def get_korean_name(self, cas):
        info = self.get_info(cas)
        return info.get("name", "") if info else ""

    def is_cas_in_whitelist(self, cas):
        """CAS 번호가 화이트리스트에 존재하는지 여부를 반환합니다."""
        return self.get_info(cas) is not None
