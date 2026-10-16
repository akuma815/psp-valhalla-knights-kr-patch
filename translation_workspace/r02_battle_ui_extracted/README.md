# R02 전투 UI 이미지 추출

## 추출 원본

- `Original/PSP_GAME/USRDIR/Resource/gsprite/gsprite.res`
  - `btmens00`, `btmens10`, `btmens11`, `btmens20`, `btmens21`
  - `btmens30`, `btmens40`, `btmens41`, `btmens42`, `btmensxx`
- `Original/PSP_GAME/USRDIR/Resource/global/global.res`
  - `station0`
  - `station2`

`btmens*` 레코드의 텍스처 참조를 해석하여 위 두 GIM을 선택했습니다.

## 파일 설명

- `textures/station0.gim`, `textures/station2.gim`: RES에서 추출한 무변경 원본 GIM
- `textures/station0.png`, `textures/station2.png`: 투명 배경 편집용 원본 PNG
- `textures/station0_dark.png`, `textures/station2_dark.png`: 흰 글자 확인용 어두운 배경 미리보기
- `textures/station2_battle_text_crop.png`: `station2`의 전투 글자 영역 `(0,176)~(256,256)` 원본 크롭
- `textures/station2_battle_text_crop_x4.png`: 위 영역을 최근접 보간으로 4배 확대한 식별용 이미지
- `sprite_definitions/btmens*.bin`: 원본 전투 메뉴 스프라이트 정의
- `manifest.csv`: 원본 컨테이너 오프셋, 크기, 참조 텍스처 목록
- `station_text_translation.csv`: 일본어 25개 영역의 원문, 좌표, 번역 입력 열
- `station_text_coordinates.md`: 사람이 읽기 쉬운 좌표·원문 목록
- `textures/station0_text_map.png`, `textures/station2_text_map.png`: ID별 좌표 표시 이미지

## 확인 결과

전투 화면에 남은 일본어 커맨드는 `station2.png` 하단에 이미지로 포함되어 있습니다. `station0`에는 `行動不能` 한 항목이 있습니다. 현재 총 25개 일본어 영역을 좌표화했으며, `station_text_translation.csv`의 `Translated` 열에 번역을 입력하면 됩니다.

## 한글 렌더링 및 적용 상태

- 번역 입력: 25/25 완료
- 좌표 적합성: 25/25 PASS (`render_validation.csv`)
- 최종 GIM: `textures/station0_korean.gim`, `textures/station2_korean.gim`
- 역변환 픽셀 비교: 차이 0
- 적용 전 백업: `translation_workspace/backups/r02_station_before_patch/global.res`
- 적용 매니페스트: `apply_manifest.csv`
- 전체 빌드 연속 2회 `global.res` 해시 일치
- 현재 단계: PPSSPP 런타임 확인 대기
