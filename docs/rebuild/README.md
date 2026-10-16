# 최종판 소스 재빌드

공개 Git 소스와 별도 원본 ISO·외부 폰트·공용 변환 도구·기존 공개 릴리즈로 `release-current` 최종판을 복원합니다. 과거 게임 폴더, 개인 백업, 추출 자산은 필요하지 않습니다.

## 필요한 별도 입력

- 지원 원본 ISO: 687,964,160바이트. SHA-256 `6f62cbe6fcab9a35146245a85025725782ad060a2b1f47a400e1477f9b445360`.
- `Font/LeeSeoYeon.ttf`: LeeSeoyun Regular. 해시는 `INPUTS.json` 참조.
- `Tools/GimConv` 전체 폴더. exe와 DLL·설정을 함께 보존하세요. 공개 저장소에는 변환 도구나 폰트 바이너리를 포함하지 않습니다.
- xdelta3 실행 파일. 공용 `Tools/xdelta3-3.2.0-windows-x86_64/xdelta3.exe`를 사용할 수 있습니다.
- Python 3.11 이상과 `requirements-rebuild.txt` 의존성.
- 고정된 기존 공개 릴리즈 ZIP. `--release-zip`을 생략하면 GitHub에서 자동 다운로드하며 해시를 검사합니다. 기존 `release-current` 첨부 파일은 변경하거나 삭제하지 마세요.

게임 폴더를 삭제해도 공용 Font와 Tools는 삭제 대상이 아닙니다. 지원 원본은 나중에 별도로 다시 제공해야 합니다.

## 재현 명령

```powershell
python -m pip install -r requirements-rebuild.txt
python -X utf8 -B translation_workspace/rebuild_final.py --source-iso "D:/ROM/Valhalla Knights (Korea).iso" --font "D:/Font/LeeSeoYeon.ttf" --gimconv-dir "D:/Tools/GimConv" --xdelta "D:/Tools/xdelta3.exe" --output-dir "build/restored_final"
```

새 출력 폴더에만 작업하며 기존 출력 폴더를 거부합니다. 원본과 체크아웃의 번역 원장은 변경하지 않습니다. 최종 ISO는 `<output-dir>/Valhalla_Knights_Korean_Rebuilt.iso`입니다.

## 복원한 빌드 조건

기존 통합 CSV는 개별 테이블 번역을 병합하기 전 상태였습니다. 최종판은 정확히 `tbldata_tbldata_extracted_*.csv` 17개를 병합하며, 원문·키와 번역의 끝 공백·줄바꿈을 보존해야 합니다. 재귀적으로 임의 CSV나 과거 백업을 섞지 않습니다. TSQV는 공개된 통합 `tsqv_translation.csv`를 사용하며 분할 CSV를 다시 병합하지 않습니다.

최종 배포본의 문자 변환 규칙은 `VK_FINAL_RELEASE_PROFILE=1`로 명시합니다. `ー ” “ ＋ ／ 【 】`는 그대로 보존합니다. 기존 개발 빌드의 기본 문자 변환과 번역 데이터는 유지합니다. 소스 재빌드가 만든 폰트·문자 코드·대사·실행 파일의 전체 바이트가 배포본과 일치하는 것으로 이 조건을 검증했습니다.

원본에서 폰트 GIM과 station0/station2를 추출하고, 원본의 16단계 알파를 인덱스와 팔레트로 복원합니다. 폰트·그래픽·텍스트·이름 입력 코드·모든 수정 리소스를 다시 생성합니다. 원본에서 재사용한 파일까지 총 3,125개를 배포본과 바이트 대조합니다.

ISO의 파일 배치·메타데이터·패딩은 원본+공개 패치로 복원한 고정 레이아웃을 사용합니다. 대조를 통과한 모든 파일을 해당 위치에 기록하고 최종 ISO 해시를 검사합니다. ISO 패킹 전체를 독립적으로 재생성한 검증과는 구분합니다. 원본 ISO, 완성 ISO, 추출된 GIM/PNG/ELF는 공개 소스에 추가하지 않습니다.

## 이후 번역 작업

이 명령은 고정 최종판 복원용이라 번역을 바꿔 결과가 달라지면 실패합니다. 변경 작업은 출력 폴더의 `project/translation_workspace`에서 별도 후보로 진행하고, 기존 `build_full_translation.py`와 `build_iso.py`를 사용하세요. 새 ISO 조립에는 별도 mkisofs 도구와 새로운 검증이 필요합니다. 기존 릴리즈는 이번 복원 작업에서 교체하지 않았습니다.

새 에뮬레이터 실행·장면 시각 검수·전체 플레이 검증은 수행하지 않았습니다.
