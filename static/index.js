// ✅ 날짜 포맷 함수 (YYYY-MM-DD → YYYY년 M월 D일)
function formatDateKorean(dateStr) {
    if (!dateStr) return "";
    const parts = dateStr.split("-");
    if (parts.length !== 3) return dateStr;

    const year = parts[0];
    const month = String(parseInt(parts[1], 10));
    const day = String(parseInt(parts[2], 10));

    return `${year}년 ${month}월 ${day}일`;
}

function toSortableDateNum(dateStr) {
    if (!dateStr) return 0;

//    console.log("[원본 dateStr]", dateStr);

    // 숫자만 추출
    let digits = dateStr.replace(/\D/g, "");
  //  console.log("[숫자만 추출]", digits);

    // 6자리(YYYYM D)나 7자리(YYYYMM D or YYYY MDD) 보정
    if (digits.length === 6) {
        // 예: 202553 → 20250503
        const year = digits.slice(0, 4);
        const month = digits.slice(4, 5).padStart(2, "0");
        const day = digits.slice(5).padStart(2, "0");
        digits = year + month + day;
    //    console.log("[6자리 보정됨]", digits);
    } else if (digits.length === 7) {
        const year = digits.slice(0, 4);
        const month = digits.slice(4, 5).padStart(2, "0");
        const day = digits.slice(5).padStart(2, "0");
        digits = year + month + day;
  //      console.log("[7자리 보정됨]", digits);
    }

    const result = digits.length >= 8 ? parseInt(digits.slice(0, 8), 10) : 0;
//    console.log("[최종 리턴]", result);

    return result;
}



// ✅ 검색 함수
async function search() {
    const question = document.getElementById('questionInput').value;
    const resultDiv = document.getElementById('result');
    resultDiv.innerHTML = '⏳ 검색 중...';

    try {
        const response = await fetch("/search/documents", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question })
        });

        const data = await response.json();

        if (data.error) {
            resultDiv.innerHTML = `<p style="color:red;">❌ ${data.error}</p>`;
            return;
        }
       // data.documents.sort((a, b) => toSortableDateNum(b.date) - toSortableDateNum(a.date)); //날짜순 정렬
        data.documents.sort((a, b) => b.accuracy - a.accuracy); // 정확도 순 정렬

        let html = `<p>🔎 총 ${data.result_count}건 검색됨</p>`;
        for (const [index, doc] of data.documents.entries()) {
            const safeId = `summary_${index}`;
            const imageSrc = (doc.image_url && doc.image_url.trim() !== "") 
                ? doc.image_url 
                : "https://s1.tokenpost.kr/assets/images/tokenpost_new/common_new/logo.svg";

            html += `
                <div class="result-card">
                    <div class="result-content">
                        <div class="result-title">${doc.title || "제목 없음"}</div>
                        <div class="result-meta">📝 기자: ${doc.reporter || "없음"} | ${formatDateKorean(doc.date)}</div>
                        <div class="result-accuracy">🧠 정확도: ${doc.accuracy}</div>
                        <div class="result-buttons">
                            <button 
                                data-content="${encodeURIComponent(doc.content || '')}" 
                                data-target="${safeId}" 
                                onclick="summarizeFromButton(this)">요약하기</button>
                            <a href="${doc.url}" target="_blank">
                                <button>보러가기</button>
                            </a>
                        </div>
                        <div id="${safeId}"></div>
                    </div>
                    <img src="${imageSrc}" alt="기사 이미지" class="result-thumb">
                </div>
            `;
        }
        resultDiv.innerHTML = html;
    } catch (err) {
        resultDiv.innerHTML = `<p style="color:red;">❌ 오류 발생: ${err.message}</p>`;
    }
}

// ✅ 버튼에서 호출되는 함수
function summarizeFromButton(button) {
    button.disabled = true;                  // 👉 버튼 비활성화
    button.innerText = "요약하기";          // 👉 텍스트 변경 (선택사항)
    button.style.opacity = "0.6";            // 👉 시각적으로 회색 느낌
    button.style.cursor = "not-allowed";     // 👉 커서도 막힌 느낌

    const contentEncoded = button.dataset.content;
    const targetId = button.dataset.target;
    summarize(contentEncoded, targetId);
}

// ✅ 요약 함수
async function summarize(contentEncoded, targetId) {
    const content = decodeURIComponent(contentEncoded);

    if (!content || content.length < 10) {
        alert("⚠️ 요약할 본문이 없습니다.");
        return;
    }

    const targetDiv = document.getElementById(targetId);
    targetDiv.className = "summary-box";   // ✅ 박스 스타일 적용
    targetDiv.innerText = "🧠 요약 중...";

    try {
        const response = await fetch("/summarize", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content })
        });

        const data = await response.json();

        if (data.summary) {
            targetDiv.innerHTML = "📄 ";
            let i = 0;
            const text = data.summary;

            function typeWriter() {
                if (i < text.length) {
                    const char = text.charAt(i);
                    targetDiv.innerHTML += (char === " " ? "&nbsp;" : char);
                    i++;
                    setTimeout(typeWriter, 20);
                }
            }
            typeWriter();
        } else {
            targetDiv.innerText = "❌ 요약 실패";
        }
    } catch (err) {
        targetDiv.innerText = `❌ 요약 중 오류: ${err.message}`;
    }
}

// ✅ HTML의 onclick이 동작하도록 전역 등록
window.search = search;
window.summarizeFromButton = summarizeFromButton;
