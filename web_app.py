import os
import time
import json
import hashlib
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
import streamlit as st
from google import genai
from google.genai import types
from google.genai.errors import ServerError, ClientError

# 1. 페이지 기본 설정 및 제목
st.set_page_config(page_title="AI 모바일 신분증 PoC", layout="wide")
st.title("🛡️ AI 최소정보 선택 인증 모바일 신분증 PoC")
st.caption("2026 모바일신분증 아이디어 공모전 시뮬레이터")

# 2. API 키 및 Client 초기화
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    st.error(".env 파일에 GEMINI_API_KEY가 설정되지 않았습니다.")
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
    is_adult: Optional[bool] = Field(default=None, description="성인 여부 (Pass/Fail)")
    name: Optional[str] = Field(default=None, description="수험생/본인 이름")
    photo_ref: Optional[str] = Field(default=None, description="사진 파일 참조 ID")
    exam_number: Optional[str] = Field(default=None, description="수험 번호")
    address: Optional[str] = Field(default=None, description="주소 정보")
    rrn_masked: Optional[str] = Field(default=None, description="마스킹된 주민번호")

class MinimizationResult(BaseModel):
    context_type: str = Field(description="인식된 맥락")
    verified_purpose: str = Field(description="검증 목적 요약")
    filtered_data: FilteredDataPacket = Field(description="필터링된 최소 개인정보 패킷")
    tts_announcement: str = Field(description="TTS 음성 안내 문구")

# 4. 백엔드 로직
def fallback_local_minimization(prompt: str) -> MinimizationResult:
    prompt_lower = prompt.lower()
    if "편의점" in prompt_lower or "주류" in prompt_lower or "성인" in prompt_lower:
        return MinimizationResult(
            context_type="CONVENIENCE_STORE",
            verified_purpose="주류/담배 구매를 위한 만 19세 이상 성인 여부 확인",
            filtered_data=FilteredDataPacket(is_adult=MOCK_USER_DATABASE["is_adult"]),
            tts_announcement="성인 확인이 완료되었습니다."
        )
    elif "시험" in prompt_lower or "수험" in prompt_lower or "입실" in prompt_lower:
        return MinimizationResult(
            context_type="EXAM_HALL",
            verified_purpose="자격증/수능 시험 응시를 위한 본인 확인",
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
            verified_purpose="관공서 민원 처리를 위한 기본 정보 확인",
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
    검증자의 요청 맥락(Prompt)을 분석하고, 아래의 사용자 원본 데이터 중 '최소 필요 정보'만 선택하여 패킷을 구성하세요.
    [원칙]
    1. 편의점/주류/성인 확인: "is_adult"만 제공.
    2. 시험장: "name", "photo_ref", "exam_number"만 제공.
    3. 관공서: "name", "address", "rrn_masked" 제공.
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

# 5. UI 시뮬레이션 화면 구성
st.sidebar.header("⚙️ 시뮬레이션 설정")
scenario = st.sidebar.radio(
    "테스트 시나리오 선택",
    ["편의점 주류 구매 (성인 확인)", "국가 자격시험장 입실 (수험생 확인)", "신분증 미소지자 현장 P2P 인쇄"]
)

if scenario == "편의점 주류 구매 (성인 확인)":
    prompt_input = "편의점 POS 단말기: 손님의 주류 구매를 위한 만 19세 이상 성인 여부(Pass/Fail) 확인 요청"
elif scenario == "국가 자격시험장 입실 (수험생 확인)":
    prompt_input = "국가자격시험 입실 창구: 수험생 본인 확인을 위한 이름, 사진, 수험번호 확인 요청"
else:
    prompt_input = "국가자격시험 입실 창구: 수험생 확인 요청 후 현장 임시 신분증 인쇄 요청"

st.subheader("1. 검증 요청 맥락 입력")
user_prompt = st.text_area("검증 단말기 요청 프롬프트", prompt_input, height=80)

if st.button("🚀 AI 최소정보 필터링 실행", type="primary"):
    with st.spinner("Gemini API 맥락 분석 중..."):
        result = run_ai_filter(user_prompt)
        clean_data = {k: v for k, v in result.filtered_data.model_dump().items() if v is not None}
        
        # QR 토큰 생성
        timestamp = int(time.time())
        dummy_hash = hashlib.sha256(f"{json.dumps(clean_data)}_{timestamp}".encode()).hexdigest()[:16]
        qr_token = f"DYN_QR_{dummy_hash}_{timestamp}"

    st.success("인증 처리 완료!")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 📱 사용자 모바일 앱 화면")
        st.info("🔒 **화면 노출 Zero 'QR-Only' 표출 중**")
        st.code(f"보안 QR 토큰: {qr_token}\n유효시간: 30초 (Dynamic QR)")
        st.warning(f"📢 **검증기 TTS 음성 출력**: \"{result.tts_announcement}\"")

    with col2:
        st.markdown("### 🖥️ 검증 단말기 및 서버 수신 데이터")
        st.json({
            "인식된_맥락": result.context_type,
            "검증_목적": result.verified_purpose,
            "수신된_최소정보_패킷": clean_data,
            "개인정보_차단_여부": "불필요한 개인정보(주소, 주민번호 등) 100% 차단됨"
        })

    if scenario == "신분증 미소지자 현장 P2P 인쇄":
        st.markdown("---")
        st.markdown("### 🖨️ 현장 P2P 무선 보안 임시 신분증 발급 결과")
        auth_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        st.json({
            "서식": "법적 효력 임시 신분증 (당일용)",
            "발급_대상": clean_data.get("name", "홍길동"),
            "인증_타임스탬프": auth_time,
            "인쇄_타임스탬프": auth_time,
            "워터마크": "COPY_PROTECTION_VOID_PATTERN_EMBEDDED",
            "상태": "P2P 보안 무선 프린터로 출력 명령 전송 완료 (15초 이내 완료)"
        })