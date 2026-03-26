"""
스톡 사진 자동화 시스템
- input_folder 에 JPG 파일이 들어오면 자동 감지 (watchdog)
- GPT-4o-mini 로 영문 제목 + 키워드 30개 생성
- piexif 로 EXIF ImageDescription(제목) / XPKeywords(키워드) 저장
- processed_folder 로 이동
"""

import os
import time
import shutil
import json
import logging
import base64
from pathlib import Path

from dotenv import load_dotenv
import openai
import piexif
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ── 환경변수 ───────────────────────────────────────────────
load_dotenv()

OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL     = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
INPUT_FOLDER     = Path(os.getenv("INPUT_FOLDER", "input_folder"))
PROCESSED_FOLDER = Path(os.getenv("PROCESSED_FOLDER", "processed_folder"))
LOG_FOLDER       = Path(os.getenv("LOG_FOLDER", "logs"))
MAX_KEYWORDS     = int(os.getenv("MAX_KEYWORDS", 30))

# ── 로깅 ──────────────────────────────────────────────────
LOG_FOLDER.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FOLDER / "automation.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ── OpenAI 클라이언트 ──────────────────────────────────────
client = openai.OpenAI(api_key=OPENAI_API_KEY)


# ══════════════════════════════════════════════════════════
#  1. GPT-4o-mini 분석
# ══════════════════════════════════════════════════════════

def analyze_image(image_path: Path) -> dict:
    """GPT-4o-mini Vision 으로 영문 제목 + 키워드 30개를 생성합니다."""

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    suffix = image_path.suffix.lower()
    mime   = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"

    prompt = f"""You are a professional stock photo metadata specialist.
Analyze the image and return ONLY a valid JSON object — no extra text.

{{
  "title": "A concise, descriptive English title for stock sites (max 200 chars)",
  "keywords": ["word1", "word2", ...]   // exactly {MAX_KEYWORDS} single-word or short-phrase keywords
}}

Rules:
- Keywords must be highly searchable on Adobe Stock / Shutterstock
- No special characters in keywords
- Return ONLY valid JSON"""

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }
        ],
        max_tokens=600,
        response_format={"type": "json_object"},
    )

    return json.loads(response.choices[0].message.content)


# ══════════════════════════════════════════════════════════
#  2. EXIF 메타데이터 삽입
# ══════════════════════════════════════════════════════════

def embed_metadata(image_path: Path, title: str, keywords: list[str]) -> None:
    """piexif 로 ImageDescription(제목)과 XPKeywords(키워드)를 삽입합니다."""

    # 기존 EXIF 로드 (없으면 빈 딕셔너리)
    try:
        exif_dict = piexif.load(str(image_path))
    except Exception:
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}

    keyword_str = "; ".join(keywords)   # Adobe Stock 표준 구분자

    # ImageDescription — ASCII/UTF-8 (표준 필드)
    exif_dict["0th"][piexif.ImageIFD.ImageDescription] = title.encode("utf-8")

    # XPKeywords — UTF-16LE (Windows/Adobe 호환)
    exif_dict["0th"][piexif.ImageIFD.XPKeywords] = keyword_str.encode("utf-16le")

    # XPTitle — UTF-16LE
    exif_dict["0th"][piexif.ImageIFD.XPTitle] = title.encode("utf-16le")

    try:
        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, str(image_path))
        log.info(f"  EXIF 저장 완료 — Title: {title[:60]}...")
        log.info(f"  Keywords({len(keywords)}): {', '.join(keywords[:5])} ...")
    except Exception as e:
        log.warning(f"  EXIF 삽입 실패: {e}")


# ══════════════════════════════════════════════════════════
#  3. 이미지 처리 파이프라인
# ══════════════════════════════════════════════════════════

def process_image(image_path: Path) -> None:
    """분석 → 메타데이터 삽입 → 이동의 전체 파이프라인."""

    log.info(f"▶ 처리 시작: {image_path.name}")

    # 파일이 완전히 쓰여질 때까지 잠시 대기
    time.sleep(1)

    try:
        # 1) GPT-4o-mini 분석
        result   = analyze_image(image_path)
        title    = result.get("title", "Untitled")
        keywords = result.get("keywords", [])[:MAX_KEYWORDS]

        # 2) EXIF 삽입
        embed_metadata(image_path, title, keywords)

        # 3) processed_folder 로 이동
        PROCESSED_FOLDER.mkdir(exist_ok=True)
        dest = PROCESSED_FOLDER / image_path.name
        # 동일 파일명 충돌 방지
        if dest.exists():
            dest = PROCESSED_FOLDER / f"{image_path.stem}_{int(time.time())}{image_path.suffix}"
        shutil.move(str(image_path), str(dest))

        # 4) JSON 결과 저장
        json_path = PROCESSED_FOLDER / (dest.stem + "_metadata.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"title": title, "keywords": keywords}, f,
                      ensure_ascii=False, indent=2)

        log.info(f"✅ 완료: {dest.name}  |  JSON: {json_path.name}\n")

    except Exception as e:
        log.error(f"❌ 처리 실패 ({image_path.name}): {e}\n")


# ══════════════════════════════════════════════════════════
#  4. Watchdog — 폴더 자동 감지
# ══════════════════════════════════════════════════════════

class PhotoHandler(FileSystemEventHandler):
    """input_folder 에 새 JPG 파일이 생기면 즉시 처리합니다."""

    SUPPORTED = {".jpg", ".jpeg", ".png", ".tiff", ".tif"}

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() in self.SUPPORTED:
            log.info(f"📂 새 파일 감지: {path.name}")
            process_image(path)


# ══════════════════════════════════════════════════════════
#  5. 실행 진입점
# ══════════════════════════════════════════════════════════

def run_batch():
    """input_folder 에 이미 있는 파일을 먼저 일괄 처리합니다."""
    ext    = {".jpg", ".jpeg", ".png", ".tiff", ".tif"}
    images = [f for f in INPUT_FOLDER.iterdir() if f.suffix.lower() in ext]
    if images:
        log.info(f"기존 파일 {len(images)}장 일괄 처리 시작...")
        for img in images:
            process_image(img)


def main():
    if not OPENAI_API_KEY or "your-" in OPENAI_API_KEY:
        print("ERROR: .env 파일에 OPENAI_API_KEY 를 입력해주세요!")
        return

    INPUT_FOLDER.mkdir(exist_ok=True)
    PROCESSED_FOLDER.mkdir(exist_ok=True)

    # 기존 파일 먼저 처리
    run_batch()

    # 이후 새 파일 실시간 감지
    handler  = PhotoHandler()
    observer = Observer()
    observer.schedule(handler, str(INPUT_FOLDER), recursive=False)
    observer.start()

    log.info(f"👀 감시 중: {INPUT_FOLDER.resolve()}  (종료: Ctrl+C)\n")

    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        observer.stop()
        log.info("프로그램 종료.")

    observer.join()


if __name__ == "__main__":
    main()
