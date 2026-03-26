@echo off
echo ============================================
echo  스톡 사진 자동화 프로젝트 - 초기 세팅
echo ============================================

echo.
echo [Step 1] 가상환경(venv) 생성 중...
python -m venv venv
echo  완료!

echo.
echo [Step 2] 가상환경 활성화 중...
call venv\Scripts\activate.bat
echo  완료!

echo.
echo [Step 3] 패키지 설치 중... (잠깐 기다려주세요)
pip install -r requirements.txt
echo  완료!

echo.
echo [Step 4] .env 파일 생성 중...
if not exist .env (
    copy .env.example .env
    echo  .env 파일이 생성됐습니다.
    echo  *** 반드시 .env 파일을 열어서 API 키를 입력해주세요! ***
) else (
    echo  .env 파일이 이미 존재합니다. 건너뜁니다.
)

echo.
echo [Step 5] 폴더 구조 확인 중...
if not exist input_folder mkdir input_folder
if not exist processed_folder mkdir processed_folder
if not exist logs mkdir logs
echo  완료!

echo.
echo ============================================
echo  세팅 완료! 다음 단계:
echo  1. .env 파일 열기: notepad .env
echo  2. OPENAI_API_KEY 값 입력
echo  3. 실행: python main.py
echo ============================================
pause
