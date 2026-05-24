    def _create_settings_page(self):
        """[Page 2] 데이터 맵핑 및 보조 관리 도구를 모은 환경 설정 페이지"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # 1. 컬럼 맵핑 설정 영역
        map_group = QGroupBox("데이터 열 매핑 설정 (엑셀 컬럼 지정)")
        map_layout = QVBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(400)
        self.mapping_panel = ModernMappingPanel()
        scroll.setWidget(self.mapping_panel)
        map_layout.addWidget(scroll)
        map_group.setLayout(map_layout)
        layout.addWidget(map_group)

        # 2. 파일 및 번호 관리 영역 (부가 기능)
        lower_layout = QHBoxLayout()
        
        file_mgmt_group = QGroupBox("파일 관리 및 번호 부여 (보조 도구)")
        file_mgmt_layout = QGridLayout()
        file_mgmt_layout.setContentsMargins(15, 15, 15, 15)
        
        file_mgmt_layout.addWidget(QLabel("시작 번호:"), 0, 0)
        self.edit_start_num = QLineEdit("1")
        self.edit_start_num.setFixedWidth(50)
        file_mgmt_layout.addWidget(self.edit_start_num, 0, 1)
        
        self.btn_batch_rename = QPushButton("파일명 일괄 변경")
        self.btn_batch_rename.setStyleSheet("background-color: #6c757d; min-height: 35px;")
        self.btn_batch_rename.clicked.connect(self.batch_rename_files)
        file_mgmt_layout.addWidget(self.btn_batch_rename, 1, 0, 1, 2)
        
        self.btn_excel_no = QPushButton("엑셀 A열 번호 부여")
        self.btn_excel_no.setStyleSheet("background-color: #e6a23c; min-height: 35px;")
        self.btn_excel_no.clicked.connect(self.assign_excel_numbers)
        file_mgmt_layout.addWidget(self.btn_excel_no, 2, 0, 1, 2)
        
        file_mgmt_group.setLayout(file_mgmt_layout)
        lower_layout.addWidget(file_mgmt_group)
        
        # 캐시 관리 등 추가 설정 버튼들 배치 가능
        info_group = QGroupBox("시스템 정보 및 캐시")
        info_layout = QVBoxLayout()
        info_layout.addWidget(QLabel("MSDS Intelligence v2.0 - Enterprise Edition"))
        info_layout.addWidget(QLabel(f"작동 모드: 지능형 바인딩 활성화"))
        btn_clear_cache = QPushButton("정밀 캐시(Hash) 초기화")
        btn_clear_cache.setStyleSheet("background-color: #f56c6c; color: white;")
        info_layout.addWidget(btn_clear_cache)
        info_group.setLayout(info_layout)
        lower_layout.addWidget(info_group)
        
        layout.addLayout(lower_layout)
        layout.addStretch()
        
        return page
