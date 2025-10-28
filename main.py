from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from qdrant_utils import keyword_then_semantic_rerank
from vllm_utils import (
    call_vllm_generate_search_condition,
    clean_llm_keywords,
    call_vllm_summarize_article
)
import json

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def serve_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/search/documents")
async def document_search(request: Request):
    data = await request.json()
    user_question = data.get("question")

    if not user_question:
        return {"error": "❌ 질문이 없습니다."}

    print(f"\n📥 사용자 질문: {user_question}")

    raw_keywords = call_vllm_generate_search_condition(user_question)
    print(f"🔍 LLM 생성 키워드 (원본): {raw_keywords}")

    keywords = clean_llm_keywords(raw_keywords)
    print(f"✅ 정제된 키워드 리스트: {keywords}")

    document_list = keyword_then_semantic_rerank(user_question, keywords, top_k=30)

    print(f"\n📄 검색 결과 개수: {len(document_list)}")

    formatted_documents = []
    for idx, doc in enumerate(document_list, 1):
        title = doc.get("제목", "")
        date = doc.get("날짜", "")
        score = doc.get("score", 0.0)
        content = doc.get("본문", "")

        # ✅ 디버깅: 각 문서 본문 길이 출력
        print(f"📄 [{idx}] 제목: {title}")
        print(f"    날짜: {date}, 점수: {score:.4f}")
        print(f"    본문 길이: {len(content)}자")
        print(f"    본문 앞 100자: {content[:100]}")

        formatted_documents.append({
            "title": title,
            "reporter": doc.get("기자", ""),
            "date": date,
            "topic": doc.get("주제", ""),
            "url": doc.get("URL", ""),
            "image_url": doc.get("Image_url", ""),
            "accuracy": f"{round(score * 100, 2)}%",
            "content": content
        })

    # ✅ 전체 응답 내용 출력
    print("\n📦 최종 응답 데이터:")
    print(json.dumps({
        "result_count": len(formatted_documents),
        "documents": formatted_documents
    }, indent=2, ensure_ascii=False))

    return {
        "result_count": len(formatted_documents),
        "documents": formatted_documents
    }


@app.post("/summarize")
async def summarize_article(request: Request):
    data = await request.json()
    content = data.get("content", "")
    question = data.get("question", None)

    print(f"\n🧠 요약 요청 수신")
    print(f"📄 본문 길이: {len(content)}자")
    print(f"📄 본문 앞 100자: {content[:100]}")

    if not content:
        return {"error": "❌ 기사 본문이 없습니다."}

    summary = call_vllm_summarize_article(content, question)
    return {"summary": summary}
