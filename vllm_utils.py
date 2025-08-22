import requests
import re

# ✅ vLLM API 서버 정보
VLLM_API_URL = "http://localhost:8000/v1/completions"
MODEL_ID = "/home/filadmin/ai-project/vllm/production-models/gemma-3-27b-it"

# ✅ 1️⃣ vLLM API 호출 함수
def call_vllm(prompt, max_tokens=256, stop=None):
    try:
        response = requests.post(
            VLLM_API_URL,
            headers={"Content-Type": "application/json"},
            json={
                "model": MODEL_ID,
                "prompt": prompt.strip(),
                "max_tokens": max_tokens,
                "temperature": 0.4,
                **({"stop": stop} if stop else {})
            },
            timeout=30
        )

        response.raise_for_status()
        result = response.json()
        print("🔍 vLLM 응답 전체:", result)

        choices = result.get("choices", [])
        if choices and "text" in choices[0]:
            return choices[0].get("text", "").strip()

        return "[⚠️ LLM 응답에 텍스트 없음]"

    except requests.RequestException as e:
        print(f"[❌ vLLM 호출 실패]: {e}")
        return "[❌ LLM 서버 연결 실패]"


# ✅ 2️⃣ 검색 키워드 생성 함수
def call_vllm_generate_search_condition(user_question):
    prompt = f"""
다음은 문서 검색용 키워드를 생성하는 작업이야.
❗️절대 설명하지 말고, 쉼표로 구분된 키워드 목록만 생성해.

규칙:
- 질문에 명시된 연도가 있을 때만 포함해. 없으면 연도는 절대 넣지 마.
- 연도는 항상 4자리 숫자 (예: '23년도' → '2023')
- 월,일이 들어가면 앞에 숫자만 추출해줘
- HTML 태그, 특수문자, 개행문자(\\n), 따옴표 등은 절대 포함하지 마
- 출력은 예: 키워드1, 키워드2, 키워드3 형식이어야 함

질문: {user_question}

키워드:"""
    return call_vllm(prompt, max_tokens=32, stop=["\n"])


# ✅ 3️⃣ 키워드 후처리 함수
def clean_llm_keywords(raw_text: str) -> list:
    first_line = raw_text.strip().split("\n")[0]  # 첫 줄만 사용
    cleaned = re.sub(r"(?i)질문\s*:.*", "", first_line)  # "질문:" 제거
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = re.sub(r"[\\\n\r\t]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return [kw.strip() for kw in cleaned.split(",") if kw.strip()]


# ✅ 4️⃣ 뉴스 기사 요약 함수
def call_vllm_summarize_article(article_text, user_question=None):
    cleaned_text = clean_article_text(article_text)
    prompt = f"""다음은 뉴스 기사입니다. 본문의 핵심 내용을 3~5문장으로 요약하세요.

조건:
- 문장 반복 금지
- "요약" 이라는 단어를 사용 금지
- 문법과 어휘를 유연하게

[본문]
{cleaned_text}
"""
    raw_summary = call_vllm(prompt, max_tokens=512)  # ❌ stop 제거
    return clean_sentences_preserve_meaning(raw_summary)




# ✅ 5️⃣ 문장 정제 함수
def clean_sentences_preserve_meaning(text: str) -> str:
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'[\r\n\t]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ✅ 6️⃣ 기사 본문 정제 함수
def clean_article_text(text: str) -> str:
    text = text.replace('\n', ' ').replace('\r', ' ')
    text = text.replace('“', '"').replace('”', '"')
    text = text.replace("‘", "'").replace("’", "'")
    text = re.sub(r"\([^)]{0,30}\)", "", text)
    text = re.sub(r"[•★☆▶▲▼→※]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
