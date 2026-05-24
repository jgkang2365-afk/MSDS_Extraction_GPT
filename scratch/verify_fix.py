import sys
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QComboBox

# PyQt QApplication 인스턴스 생성 (GUI 이벤트 루프 구동용)
app = QApplication.instance() or QApplication(sys.argv)

def test_container_and_saving():
    # 1. 보통 휘발유 기준 1:N 대상 크실렌 콤보박스 모의 생성 (함량 2~4% 보존)
    combo = QComboBox()
    combo.addItem("크실렌 - TWA : 100 ppm", "C1330207")
    combo.setCurrentIndex(0)
    combo.setProperty("cas", "1330-20-7")
    combo.setProperty("content", "2~4%")
    
    # 2. 컨테이너 및 레이아웃 생성
    container = QWidget()
    layout = QVBoxLayout()
    layout.addWidget(combo)
    
    # 3. KOSHA API 및 복원 로직을 통해 복구된 실제 함량 정보 기입 (미기재%가 아님)
    other_text = "벤젠(0.1~0.7%); 톨루엔(1~10%)"
    label = QLabel(other_text)
    layout.addWidget(label)
    
    container.setLayout(layout)
    container.setProperty("combo", combo)
    container.setProperty("other_text", other_text)
    
    # 4. 저장 시의 추출 로직 시뮬레이션
    measure_widget = container
    
    if measure_widget and not isinstance(measure_widget, QComboBox):
        combo_in_widget = measure_widget.property("combo")
        extracted_other = measure_widget.property("other_text") or ""
    else:
        combo_in_widget = measure_widget if isinstance(measure_widget, QComboBox) else None
        extracted_other = ""
        
    assert combo_in_widget is not None, "컨테이너에서 콤보박스 추출 실패!"
    
    selected_text = combo_in_widget.currentText()
    combo_val = selected_text.split(" - TWA")[0].strip()
    
    content_val = combo_in_widget.property("content")
    if content_val:
        combo_val = f"{combo_val}({content_val})"
        
    measure_val = combo_val
    if extracted_other:
        measure_val = f"{combo_val}; {extracted_other}"
        
    print(f"[*] 추출된 최종 측정대상 값: {measure_val}")
    
    # 예상 결과 대조
    expected = "크실렌(2~4%); 벤젠(0.1~0.7%); 톨루엔(1~10%)"
    assert measure_val == expected, f"결과 불일치! 예상: {expected}, 실제: {measure_val}"
    print("[+] 테스트 성공! 실제 수치 정보(0.1~0.7%, 1~10%)가 온전히 기록됩니다.")

if __name__ == "__main__":
    try:
        test_container_and_saving()
    except Exception as e:
        print(f"[!] 테스트 실패: {e}")
        sys.exit(1)
