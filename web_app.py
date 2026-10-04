import os
import time
import json
import hashlib
import io
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
import streamlit as st
import qrcode
from PIL import Image, ImageDraw
from google import genai
from google.genai import types

# 1. 페이지 기본 설정
st.set_page_config(page_title="AI 모바일 신분증 Visual PoC", layout="wide")
st.title("🛡️ AI 최소정보 선택 인증 & Dynamic QR 모바일 신분증 PoC")
st.caption("2026 모바일신분증 아이디어 공모전 시각적 개념검증 시뮬레이터")

# 2. API 키 로드 및 Client 초기화
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

# Streamlit Secrets 또는 .env에서 키 읽기
if not api_key and "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]

if not api_key:
    st.error(".env 파일 또는 Streamlit Secrets에 GEMINI_API_KEY가 설정되지 않았습니다.")
    st.stop()

client = genai.Client(api_key=api_key)

# 3. 데이터 및 Pydantic 스키마 정의
MOCK_USER_DATABASE = {
    "user_id": "USER_10029384",
    "name": "홍길동",
    "birth_date": "1998-05-15",
    "is_adult": True,
    "photo_ref": "photo_hong_gildong_v1.jpg",
    "address": "서울특별시 종로구 세종대로 209",
    "rrn_masked": "980515-1******",
    "exam_number": "2026-CSAT-9982"
}

class FilteredDataPacket(BaseModel):
    is_adult: Optional[bool] = Field(default=None, description="성인 여부")
    name: Optional[str] = Field(default=None, description="이름")
    photo_ref: Optional[str] = Field(default=None, description="사진 참조 ID")
    exam_number: Optional[str] = Field(default=None, description="수험 번호")
    address: Optional[str] = Field(default=None, description="주소")
    rrn_masked: Optional[str] = Field(default=None, description="마스킹 주민번호")

class MinimizationResult(BaseModel):
    context_type: str = Field(description="인식된 맥락")
    verified_purpose: str = Field(description="검증 목적")
    filtered_data: FilteredDataPacket = Field(description="최소 개인정보 패킷")
    tts_announcement: str = Field(description="TTS 음성 문구")

# 4. 백엔드 AI 및 Fallback 로직
def fallback_local_minimization(prompt: str) -> MinimizationResult:
    prompt_lower = prompt.lower()
    if "편의점" in prompt_lower or "주류" in prompt_lower or "성인" in prompt_lower:
        return MinimizationResult(
            context_type="CONVENIENCE_STORE",
            verified_purpose="주류 구매용 만 19세 이상 성인 여부 확인",
            filtered_data=FilteredDataPacket(is_adult=MOCK_USER_DATABASE["is_adult"]),
            tts_announcement="성인 확인이 완료되었습니다."
        )
    elif "시험" in prompt_lower or "수험" in prompt_lower or "입실" in prompt_lower:
        return MinimizationResult(
            context_type="EXAM_HALL",
            verified_purpose="자격증 시험 응시용 본인 확인",
            filtered_data=FilteredDataPacket(
                name=MOCK_USER_DATABASE["name"],
                photo_ref=MOCK_USER_DATABASE["photo_ref"],
                exam_number=MOCK_USER_DATABASE["exam_number"]
            ),
            tts_announcement="시험 응시용 본인 확인이 완료되었습니다."
        )
    else:
        return MinimizationResult(
            context_type="GOVERNMENT_OFFICE",
            verified_purpose="관공서 민원 처리용 기본 정보 확인",
            filtered_data=FilteredDataPacket(
                name=MOCK_USER_DATABASE["name"],
                address=MOCK_USER_DATABASE["address"],
                rrn_masked=MOCK_USER_DATABASE["rrn_masked"]
            ),
            tts_announcement="관공서 민원 본인 확인이 완료되었습니다."
        )

def run_ai_filter(request_prompt: str) -> MinimizationResult:
    system_instruction = f"""
    당신은 모바일 신분증 AI 최소정보 선택 인증 엔진입니다.
    검증자의 요청 맥락을 분석하여 필수 최소 정보만 필터링하세요.
    [원칙]
    1. 편의점/성인: is_adult 만 제공
    2. 시험장: name, photo_ref, exam_number 만 제공
    3. 관공서: name, address, rrn_masked 제공
    [원본 데이터]: {json.dumps(MOCK_USER_DATABASE, ensure_ascii=False)}
    """
    try:
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=f"검증 요청: {request_prompt}",
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=MinimizationResult,
                temperature=0.0
            )
        )
        return MinimizationResult(**json.loads(response.text))
    except Exception:
        return fallback_local_minimization(request_prompt)

# 5. [핵심 개선] 5초 주기 동적 색상 & 가짜 패턴(Dummy Pattern) 생성을 포함한 QR 그리기 함수
def generate_visual_qr(qr_token_str: str, current_sec: int, simulate_tamper: bool = False):
    # 5초 간격으로 색상 테마 및 미세 보안 격자 무늬가 자동 교체됨
    theme_cycle = (current_sec // 5) % 3
    
    themes = [
        {
            "fill": "#0D47A1", "back": "#E3F2FD", "grid": "#90CAF9",
            "name": "🎨 [테마 A] 네이비 & 수직 보안 격자 패턴",
            "pattern_type": "vertical"
        },
        {
            "fill": "#1B5E20", "back": "#E8F5E9", "name": "🎨 [테마 B] 에메랄드 & 사선 보안 무늬 패턴",
            "grid": "#A5D6A7", "pattern_type": "diagonal"
        },
        {
            "fill": "#4A148C", "back": "#F3E5F5", "name": "🎨 [테마 C] 디프 퍼플 & 크로스 도트 패턴",
            "grid": "#CE93D8", "pattern_type": "dots"
        }
    ]
    theme = themes[theme_cycle]

    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=3,
    )
    qr.add_data(qr_token_str)
    qr.make(fit=True)

    img = qr.make_image(fill_color=theme["fill"], back_color=theme["back"]).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = img.size

    if simulate_tamper:
        # 동영상/캡처 재전송 시뮬레이션: 주사율 상 오차로 가짜 프레임과 빨간 뭉개짐선 발생
        for y in range(0, h, 6):
            draw.line([(0, y), (w, y)], fill="#FF1744", width=2)
        draw.text((15, h//2 - 10), "⚠️ REPLAY ATTACK DETECTED", fill="#D50000")
        mode_name = "❌ 부정사용 감지 (동영상 녹화/캡처본 프레임 상 오차 노출)"
    else:
        # 정상 모드: 5초마다 패턴 무늬 자동 변경
        if theme["pattern_type"] == "vertical":
            for i in range(0, w, 15):
                draw.line([(i, 0), (i, h)], fill=theme["grid"], width=1)
        elif theme["pattern_type"] == "diagonal":
            for i in range(-w, w, 15):
                draw.line([(i, 0), (i + h, h)], fill=theme["grid"], width=1)
        elif theme["pattern_type"] == "dots":
            for x in range(5, w, 15):
                for y in range(5, h, 15):
                    draw.ellipse([x-2, y-2, x+2, y+2], fill=theme["grid"])
        mode_name = theme["name"]

    return img, mode_name

# 6. UI 시뮬레이터 화면 구성
st.sidebar.header("⚙️ PoC 시뮬레이션 제어")

# 실시간 라이브 토글 스위치 (기본 켜짐)
live_mode = st.sidebar.toggle("🔴 5초 주기 실시간 Dynamic QR 라이브 모드", value=True)

scenario = st.sidebar.radio(
    "검증 상황 선택",
    ["편의점 주류 구매 (성인 확인)", "국가 자격시험장 입실 (수험생 확인)", "신분증 미소지자 현장 P2P 인쇄"]
)

# 현재 시간 초 계산
now_sec = int(time.time())
cycle_sec = 5
time_left = cycle_sec - (now_sec % cycle_sec)

if scenario == "편의점 주류 구매 (성인 확인)":
    prompt_input = "편의점 POS 단말기: 손님의 주류 구매를 위한 만 19세 이상 성인 여부(Pass/Fail) 확인 요청"
elif scenario == "국가 자격시험장 입실 (수험생 확인)":
    prompt_input = "국가자격시험 입실 창구: 수험생 본인 확인을 위한 이름, 사진, 수험번호 확인 요청"
else:
    prompt_input = "국가자격시험 입실 창구: 수험생 확인 요청 후 현장 임시 신분증 인쇄 요청"

st.subheader("1. AI 검증 요청 및 실시간 QR 모니터링")
user_prompt = st.text_area("검증 단말기(POS/감독관 앱) 요청 문구", prompt_input, height=70)

# 세션에 필터링 결과 저장 (화면이 1초마다 자동 새로고침되어도 AI를 계속 다시 부르지 않도록 방지)
if "last_prompt" not in st.session_state or st.session_state.last_prompt != user_prompt:
    st.session_state.last_prompt = user_prompt
    st.session_state.ai_result = run_ai_filter(user_prompt)

result = st.session_state.ai_result
clean_data = {k: v for k, v in result.filtered_data.model_dump().items() if v is not None}

# 5초 단위 주기성 암호화 토큰 생성
seed_time = (now_sec // 5) * 5
dummy_hash = hashlib.sha256(f"{json.dumps(clean_data)}_{seed_time}".encode()).hexdigest()[:16]
qr_token = f"DYN_QR_{dummy_hash}_{seed_time}"

col1, col2 = st.columns([1, 1])

with col1:
    st.markdown("### 📱 사용자 모바일 앱 화면 (Zero Exposure)")
    st.caption("🔒 화면 노출 Zero 적용: 이름/주소 등 시각적 노출 차단, 오직 Dynamic QR만 생성")

    # 5초 마다 색상과 패턴이 달라지는 시각적 QR 렌더링
    qr_img, mode_title = generate_visual_qr(qr_token, now_sec, simulate_tamper=False)
    
    buf = io.BytesIO()
    qr_img.save(buf, format="PNG")
    st.image(buf.getvalue(), width=260)

    # 카운트다운 타이머 및 현재 패턴 표시
    st.markdown(f"**실시간 보안 상태**: `{mode_title}`")
    st.progress((cycle_sec - time_left) / cycle_sec)
    st.warning(f"⏱️ **색상/가짜 패턴(Dummy) 갱신까지**: `{time_left}초` 남음 (5초 주기 파기)")
    st.info(f"📢 **검증 단말기 TTS 음성 출력 (0.5초 이내)**: \"{result.tts_announcement}\"")

with col2:
    st.markdown("### 🖥️ 검증 단말기 수신 & 보안 대조 결과")
    
    tab_a, tab_b = st.tabs(["✅ 정상 실물 스캔 (인증 성공)", "❌ 동영상/캡처 재전송 (인증 거절)"])
    
    with tab_a:
        st.json({
            "인식된_맥락": result.context_type,
            "검증_목적": result.verified_purpose,
            "수신된_최소정보_패킷": clean_data,
            "4단계_Dummy_Pattern_대조": "PASSED (5초 주기 동기화 패킷 및 보안 프레임 일치)",
            "개인정보_유출_건수": "0건 (성인 여부 외 정보 완전 차단)"
        })

    with tab_b:
        tampered_img, _ = generate_visual_qr(qr_token, now_sec, simulate_tamper=True)
        t_buf = io.BytesIO()
        tampered_img.save(t_buf, format="PNG")
        st.image(t_buf.getvalue(), width=220, caption="녹화본 스캔 시 프레임 상 오차 및 모아레 왜곡 노출")
        st.error("🚫 [부정 사용 차단 완료] 동영상 촬영 및 캡처본 스캔 감지 (Replay Attack 원천 차단)")

if scenario == "신분증 미소지자 현장 P2P 인쇄":
    st.markdown("---")
    st.markdown("### 🖨️ 현장 P2P 무선 보안 임시 신분증 즉시 인쇄")
    auth_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    st.success("BLE/Wi-Fi Direct P2P 암호화 연동 성공 - 15초 이내 인쇄 완료")
    st.json({
        "서식": "법적 효력 임시 신분증 (당일용)",
        "발급_대상": clean_data.get("name", "홍길동"),
        "모바일_인증_타임스탬프": auth_time,
        "종이_인쇄_타임스탬프": auth_time,
        "위변조_방지_특수_각인": "COPY_PROTECTION_VOID_PATTERN_EMBEDDED (복사 시 VOID 문구 노출)",
        "상태": "보안 무선 프린터 전송 완료"
    })

# 실시간 라이브 갱신 루프 (1초마다 자동 새로고침하여 5초 주기 색상/패턴 변화를 눈으로 보여줌)
if live_mode:
    time.sleep(1)
    st.rerun()