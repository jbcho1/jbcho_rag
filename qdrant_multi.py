import time
from typing import List
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# ✅ Qdrant 설정
qdrant_client = QdrantClient(host="localhost", port=6333)
collection_name = "article_2025_image_test"

# ✅ 한국어 임베딩 모델
model = SentenceTransformer("nlpai-lab/KURE-v1")

# ✅ 필터링 필드 목록
KEYWORD_FILTER_FIELDS = [
    "title_original", "organization", "reporter",
    "year", "month", "date_day", "date_weekday", "topic", "content"
]

# ✅ 벡터 기반 의미 검색 (전체 대상)
def semantic_vector_search(question: str, top_k: int = 10):
    print(f"\n🧠 [의미 기반 벡터 검색] 질문: {question}")
    start = time.time()

    try:
        query_vector = model.encode(question)
        results = qdrant_client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=top_k,
            with_payload=True,
            score_threshold=0.5
        )
    except Exception as e:
        print(f"❌ 벡터 검색 오류: {e}")
        return []

    documents = []
    for hit in results:
        payload = hit.payload
        documents.append({
            "id": hit.id,
            "제목": payload.get("title_original", ""),
            "언론사": payload.get("organization", ""),
            "기자": payload.get("reporter", ""),
            "날짜": f"{payload.get('year', '----')}-{payload.get('month', '--')}-{payload.get('date_day', '--')} ({payload.get('date_weekday', '-')})",
            "주제": payload.get("topic", ""),
            "요약": payload.get("summary", ""),
            "URL": payload.get("url", ""),
            "Image_url":hit.payload.get("main_image_url", ""),
            "본문": payload.get("content", ""),
            "score": round(hit.score, 5) if hasattr(hit, "score") else 0.0
        })

    print(f"✅ 검색 완료 (소요 시간: {time.time() - start:.2f}초) → 결과 {len(documents)}건")
    return documents


def search_qdrant_metadata_smart(keywords: List[str], top_k_per_keyword: int = 50):
    print(f"\n📋 [스마트 키워드 기반 검색] 키워드 목록: {keywords}")

    year_val = next((int(k) for k in keywords if k.isdigit() and len(k) == 4 and 1900 <= int(k) <= 2100), None)
    month_val = next((int(k) for k in keywords if k.isdigit() and 1 <= int(k) <= 12), None)
    day_val = next((int(k) for k in keywords if k.isdigit() and 1 <= int(k) <= 31), None)

    date_conditions = []
    if year_val: date_conditions.append(FieldCondition(key="year", match=MatchValue(value=year_val)))
    if month_val: date_conditions.append(FieldCondition(key="month", match=MatchValue(value=month_val)))
    if day_val: date_conditions.append(FieldCondition(key="date_day", match=MatchValue(value=day_val)))

    keyword_conditions = []
    for keyword in keywords:
        if keyword.isdigit() and (keyword == str(year_val) or keyword == str(month_val) or keyword == str(day_val)):
            continue  # 날짜로 이미 처리된 값은 제외
        keyword_conditions.extend(
            FieldCondition(key=field, match=MatchValue(value=keyword))
            for field in KEYWORD_FILTER_FIELDS
        )

    try:
        if date_conditions:
            if keyword_conditions:
                query_filter = Filter(must=[
                    Filter(must=date_conditions),
                    Filter(should=keyword_conditions)
                ])
            else:
                query_filter = Filter(must=date_conditions)
        else:
            query_filter = Filter(should=keyword_conditions)

        result = qdrant_client.query_points(
            collection_name=collection_name,
            query_filter=query_filter,
            limit=top_k_per_keyword,
            with_payload=True
        )
    except Exception as e:
        print(f"❌ 검색 오류: {e}")
        return []

    documents = []
    for point in result.points:
        payload = point.payload
        documents.append({
            "id": point.id,
            "제목": payload.get("title_original", ""),
            "언론사": payload.get("organization", ""),
            "기자": payload.get("reporter", ""),
            "날짜": f"{payload.get('year', '----')}-{payload.get('month', '--')}-{payload.get('date_day', '--')} ({payload.get('date_weekday', '-')})",
            "주제": payload.get("topic", ""),
            "요약": payload.get("summary", ""),
            "URL": payload.get("url", ""),
            "본문": payload.get("content", "")
        })

    print(f"✅ 총 검색 결과 수: {len(documents)}")
    return documents

# ✅ 키워드 기반 필터링
def search_qdrant_metadata_by_keywords(keywords: List[str], top_k_per_keyword: int = 50):
    print(f"\n📋 [키워드 기반 메타데이터 검색] 키워드 목록: {keywords}")
    matched_ids = set()
    documents_map = {}

    for keyword in keywords:
        print(f"🔍 '{keyword}' 검색 중...")

        try:
            conditions = [
                FieldCondition(key=field, match=MatchValue(value=keyword))
                for field in KEYWORD_FILTER_FIELDS
            ]
            query_filter = Filter(should=conditions)

            result = qdrant_client.query_points(
                collection_name=collection_name,
                query_filter=query_filter,
                limit=top_k_per_keyword,
                with_payload=True
            )
        except Exception as e:
            print(f"❌ 키워드 '{keyword}' 검색 오류: {e}")
            continue

        for point in result.points:
            pid = point.id
            if pid not in matched_ids:
                matched_ids.add(pid)
                payload = getattr(point, 'payload', None)
                if payload:
                    documents_map[pid] = {
                        "id": pid,
                        "제목": payload.get("title_original", ""),
                        "언론사": payload.get("organization", ""),
                        "기자": payload.get("reporter", ""),
                        "날짜": f"{payload.get('year', '----')}-{payload.get('month', '--')}-{payload.get('date_day', '--')} ({payload.get('date_weekday', '-')})",
                        "주제": payload.get("topic", ""),
                        "요약": payload.get("summary", ""),
                        "URL": payload.get("url", ""),
                        "본문": payload.get("content", "")
                    }

    print(f"✅ 총 키워드 검색 결과 수: {len(documents_map)}")
    return list(documents_map.values())

# ✅ 키워드 기반 필터 + 의미 기반 재정렬
def keyword_then_semantic_rerank(question: str, keywords: List[str], top_k: int = 5):
    print(f"\n🔎 [종합 검색 시작] 질문: '{question}' | 키워드 필터: {keywords}")

    metadata_results = search_qdrant_metadata_smart(keywords, top_k_per_keyword=50)

    if not metadata_results:
        print("⚠️ 키워드 결과 없음 → 전체 의미 기반 검색으로 fallback")
        return semantic_vector_search(question, top_k=top_k)

    print("💡 키워드 결과 존재 → 의미 기반 재정렬 수행 중...")
    query_vector = model.encode(question)
    contents = [doc["본문"] for doc in metadata_results]
    doc_vectors = model.encode(contents, batch_size=32)

    similarities = cosine_similarity([query_vector], doc_vectors)[0]

    reranked = []
    for i, doc in enumerate(metadata_results):
        score = float(similarities[i])
        if score < 0.35:
            continue
        doc["score"] = round(score, 5)
        reranked.append(doc)

    sorted_results = sorted(reranked, key=lambda x: x["score"], reverse=True)
    print(f"✅ 종합 검색 완료: {len(sorted_results)}건 중 상위 {top_k}개 반환")
    return sorted_results[:top_k]
