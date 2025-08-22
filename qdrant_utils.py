import time, gc, torch
from typing import List, Tuple, Dict, Set
from concurrent.futures import ThreadPoolExecutor
from qdrant_client import QdrantClient
from qdrant_client.models import MatchValue, Filter, FieldCondition
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# ✅ Qdrant 설정
qdrant_client = QdrantClient(host="localhost", port=6333)
collection_name = "article_2025_image_test"

# ✅ 한국어 임베딩 모델
model = SentenceTransformer("nlpai-lab/KURE-v1")

# ✅ VRAM 청소 포함 임베딩 함수 (query 전용)
def encode_and_clear(texts, **kwargs):
    vectors = model.encode(texts, **kwargs)
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        gc.collect()
    return vectors

# ✅ 일반 키워드 검색 필드
KEYWORD_FILTER_FIELDS = [
    "title_original", "organization", "reporter",
    "topic", "content"
]

# ✅ 단일 키워드 검색
def keyword_search_single(keyword: str, top_k: int = 50) -> Tuple[Set, Dict, str]:
    keyword_type = "none"
    query_filter = None

    if keyword.isdigit():
        val_str = keyword
        val = int(keyword)

        if len(keyword) == 4 and 1900 <= val <= 2100:
            keyword_type = "year"
            query_filter = Filter(must=[FieldCondition(key="year", match=MatchValue(value=val_str))])
        elif 1 <= val <= 12:
            keyword_type = "month"
            query_filter = Filter(must=[FieldCondition(key="month", match=MatchValue(value=val_str))])
        else:
            return set(), {}, keyword_type
    else:
        query_filter = Filter(
            should=[FieldCondition(key=field, match=MatchValue(value=keyword))
                    for field in KEYWORD_FILTER_FIELDS]
        )

    result = qdrant_client.query_points(
        collection_name=collection_name,
        query_filter=query_filter,
        limit=top_k,
        with_payload=True,
        with_vectors=True   # ✅ 벡터도 같이 가져오기
    )

    ids = {p.id for p in result.points}
    payloads = {p.id: {"payload": p.payload, "vector": p.vector} for p in result.points}
    return ids, payloads, keyword_type

# ✅ 병렬 키워드 검색
def search_qdrant_metadata_parallel(keywords: List[str], top_k_per_keyword: int = 50):
    all_payloads = {}
    keyword_results = {}
    keyword_types = {}

    with ThreadPoolExecutor(max_workers=len(keywords)) as executor:
        futures = {executor.submit(keyword_search_single, kw, top_k_per_keyword): kw for kw in keywords}
        for future in futures:
            ids, payloads, kw_type = future.result()
            kw = futures[future]
            keyword_results[kw] = ids
            keyword_types[kw] = kw_type
            all_payloads.update(payloads)

    return keyword_results, all_payloads, keyword_types

# ✅ 날짜(MUST) + 의미검색 재정렬
def keyword_then_semantic_rerank(question: str, keywords: List[str], top_k: int = 5):
    keyword_results, all_payloads, keyword_types = search_qdrant_metadata_parallel(keywords, top_k_per_keyword=200)

    date_sets = [ids for kw, ids in keyword_results.items() if keyword_types[kw] in ("year", "month")]
    date_intersection = set.intersection(*date_sets) if date_sets else None

    normal_sets = [ids for kw, ids in keyword_results.items() if keyword_types[kw] == "none"]
    normal_union = set.union(*normal_sets) if normal_sets else None

    if date_intersection and normal_union:
        final_ids = date_intersection & normal_union
    elif date_intersection:
        final_ids = date_intersection
    elif normal_union:
        final_ids = normal_union
    else:
        final_ids = set()

    # ✅ Qdrant에서 바로 의미검색 (날짜 필터 있는 경우)
    if date_intersection:
        print(f"⚡ 날짜 필터 적용됨 → Qdrant에서 벡터검색 바로 실행")
        query_vector = encode_and_clear([question])[0]
        must_conditions = []
        for kw, kw_type in keyword_types.items():
            if kw_type == "year":
                must_conditions.append(FieldCondition(key="year", match=MatchValue(value=kw)))
            elif kw_type == "month":
                must_conditions.append(FieldCondition(key="month", match=MatchValue(value=kw)))
        filter_query = Filter(must=must_conditions)
        results = qdrant_client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            query_filter=filter_query,
            limit=top_k,
            with_payload=True
        )
        return [
            {
                "id": hit.id,
                "제목": hit.payload.get("title_original", ""),
                "기자": hit.payload.get("reporter", ""),
                "날짜": f"{hit.payload.get('year', '----')}-{hit.payload.get('month', '--')}-{hit.payload.get('date_day', '--')}",
                "주제": hit.payload.get("topic", ""),
                "URL": hit.payload.get("url", ""),
                "Image_url": hit.payload.get("main_image_url", ""),
                "본문": hit.payload.get("content", ""),
                "score": round(hit.score, 5)
            }
            for hit in results
        ]

    # ✅ 로컬 재랭킹 (벡터는 Qdrant에서 꺼냄)
    if not final_ids:
        print("⚠️ 필터 결과 없음 → 전체 의미 기반 검색으로 fallback")
        return semantic_vector_search(question, top_k=top_k)

    print(f"💡 필터링된 문서 {len(final_ids)}건 → 로컬 의미검색 재정렬")
    query_vector = encode_and_clear([question])[0]

    doc_vectors = [all_payloads[pid]["vector"] for pid in final_ids]
    similarities = cosine_similarity([query_vector], doc_vectors)[0]

    reranked = []
    for pid, score in zip(final_ids, similarities):
        payload = all_payloads[pid]["payload"]
        reranked.append({
            "id": pid,
            "제목": payload.get("title_original", ""),
            "기자": payload.get("reporter", ""),
            "날짜": f"{payload.get('year', '----')}-{payload.get('month', '--')}-{payload.get('date_day', '--')}",
            "주제": payload.get("topic", ""),
            "URL": payload.get("url", ""),
            "Image_url": payload.get("main_image_url", ""),
            "본문": payload.get("content", ""),
            "score": round(float(score), 5)
        })

    return sorted(reranked, key=lambda x: x["score"], reverse=True)[:top_k]

# ✅ 의미 기반 벡터 검색 (Qdrant 벡터 직접 활용)
def semantic_vector_search(question: str, top_k: int = 10):
    query_vector = encode_and_clear([question])[0]
    results = qdrant_client.search(
        collection_name=collection_name,
        query_vector=query_vector,
        limit=top_k,
        with_payload=True
    )
    return [
        {
            "id": hit.id,
            "제목": hit.payload.get("title_original", ""),
            "기자": hit.payload.get("reporter", ""),
            "날짜": f"{hit.payload.get('year', '----')}-{hit.payload.get('month', '--')}-{hit.payload.get('date_day', '--')}",
            "주제": hit.payload.get("topic", ""),
            "URL": hit.payload.get("url", ""),
            "Image_url": hit.payload.get("main_image_url", ""),
            "본문": hit.payload.get("content", ""),
            "score": round(hit.score, 5)
        }
        for hit in results
    ]
