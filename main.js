// Initialize Lucide Icons
lucide.createIcons();

// Elements
const ocrBtn = document.getElementById('ocr-extract-btn');
const grammarBtn = document.getElementById('grammar-check-btn');
const exportBtn = document.getElementById('export-text-btn');
const searchBtn = document.getElementById('search-nav-btn');
const resultBox = document.getElementById('result-box');
const viewer = document.getElementById('pdf-viewer');
const openFileBtn = document.getElementById('open-file-btn');
const fileInput = document.getElementById('file-input');
const prevBtn = document.getElementById('prev-page-btn');
const nextBtn = document.getElementById('next-page-btn');
const pageInput = document.getElementById('current-page-num');
const totalPagesSpan = document.getElementById('total-pages');

// pdf.js setup
const pdfjsLib = window['pdfjs-dist/build/pdf'];
pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.worker.min.js';

let pdfDoc = null;
let currentPageNum = 1;
let extractedText = ""; // 전체 문서 텍스트
let pageResults = []; // 페이지별 데이터 { pageNum, text, corrections }
let canvas = null;

// 1. File Upload & PDF Rendering
openFileBtn.onclick = () => fileInput.click();

fileInput.onchange = async (e) => {
    const file = e.target.files[0];
    if (file && file.type === 'application/pdf') {
        const fileReader = new FileReader();
        fileReader.onload = async function() {
            const typedarray = new Uint8Array(this.result);
            try {
                pdfDoc = await pdfjsLib.getDocument(typedarray).promise;
                totalPagesSpan.textContent = pdfDoc.numPages;
                currentPageNum = 1;
                renderPage(currentPageNum);
                extractedText = "";
                pageResults = [];
                resultBox.innerHTML = '<p class="hint">파일이 로드되었습니다. "오타 및 문맥 교정"을 눌러 분석을 시작하세요.</p>';
            } catch (err) {
                console.error("PDF 로드 오류:", err);
                alert("PDF 파일을 불러오는 데 실패했습니다.");
            }
        };
        fileReader.readAsArrayBuffer(file);
    }
};

async function renderPage(num) {
    if (!pdfDoc) return;
    const page = await pdfDoc.getPage(num);
    const viewport = page.getViewport({ scale: 1.5 });
    
    if (!canvas) {
        canvas = document.createElement('canvas');
        viewer.innerHTML = '';
        viewer.appendChild(canvas);
    }
    
    const context = canvas.getContext('2d');
    canvas.height = viewport.height;
    canvas.width = viewport.width;

    const renderContext = { canvasContext: context, viewport: viewport };
    await page.render(renderContext).promise;
    
    pageInput.value = num;
}

// Page Navigation
prevBtn.onclick = () => {
    if (!pdfDoc || currentPageNum <= 1) return;
    currentPageNum--;
    renderPage(currentPageNum);
};

nextBtn.onclick = () => {
    if (!pdfDoc || currentPageNum >= pdfDoc.numPages) return;
    currentPageNum++;
    renderPage(currentPageNum);
};

// 2. Core Processing Logic (Extract + Grammar Check for All Pages)
async function runFullAnalysis() {
    if (!pdfDoc) {
        alert("먼저 PDF 파일을 불러와 주세요.");
        return;
    }

    resultBox.innerHTML = '<p style="color: #666; text-align: center;">전체 문서 분석 시작 (총 ' + pdfDoc.numPages + '페이지)...</p>';
    extractedText = "";
    pageResults = [];

    const commonErrors = [
        { pattern: /반갑습니가/g, replacement: "반갑습니다", reason: "오타 교정" },
        { pattern: /있슴니다/g, replacement: "있습니다", reason: "종결 어미 오류" },
        { pattern: /않돼요/g, replacement: "안 돼요", reason: "부정어 표기 오류" },
        { pattern: /되요/g, replacement: "돼요", reason: "어미 활용 오류" },
        { pattern: /애양환경공단/g, replacement: "해양환경공단", reason: "OCR 인식 오류 수정" }
    ];

    try {
        const worker = await Tesseract.createWorker({
            logger: m => {
                if (m.status === 'recognizing text') {
                    const progress = Math.round(m.progress * 100);
                    const pageInfo = `[${currentPageNum}/${pdfDoc.numPages} 페이지]`;
                    resultBox.innerHTML = `<p style="text-align: center;">${pageInfo} OCR 인식 중: ${progress}%</p>`;
                }
            }
        });
        await worker.loadLanguage('kor+eng');
        await worker.initialize('kor+eng');

        for (let i = 1; i <= pdfDoc.numPages; i++) {
            currentPageNum = i;
            await renderPage(i);
            
            resultBox.innerHTML = `<p style="text-align: center;">${i} / ${pdfDoc.numPages} 페이지 분석 중...</p>`;

            const page = await pdfDoc.getPage(i);
            const textContent = await page.getTextContent();
            let pageText = "";

            if (textContent.items.length > 0) {
                pageText = textContent.items.map(item => item.str).join(' ');
            } else {
                const { data: { text } } = await worker.recognize(canvas);
                pageText = text;
            }

            // Grammar Check for this page
            let corrections = [];
            let processedText = pageText;
            commonErrors.forEach(item => {
                const regex = new RegExp(item.pattern.source, 'g');
                if (regex.test(pageText)) {
                    corrections.push({
                        original: item.pattern.source,
                        replacement: item.replacement,
                        reason: item.reason
                    });
                    processedText = processedText.replace(regex, `<span style="background-color: #ffff00; font-weight: bold;">${item.replacement}</span>`);
                }
            });

            pageResults.push({
                pageNum: i,
                originalText: pageText,
                processedText: processedText,
                corrections: corrections
            });

            extractedText += `\n[Page ${i}]\n${pageText}\n`;
        }

        await worker.terminate();
        displayResults();

    } catch (error) {
        console.error(error);
        resultBox.innerHTML = '<p style="color: red;">분석 중 오류가 발생했습니다.</p>';
    }
}

function displayResults() {
    let allCorrectionsHTML = "";
    let fullTextHTML = "";
    let totalCorrections = 0;

    pageResults.forEach(res => {
        if (res.corrections.length > 0) {
            res.corrections.forEach(c => {
                totalCorrections++;
                allCorrectionsHTML += `<li style="margin-bottom: 6px;">
                    <span style="color: #666; font-weight: bold;">[${res.pageNum}쪽]</span> 
                    <span style="color: red;">${c.original}</span> → <b style="color: green;">${c.replacement}</b> (${res.reason || '오타/문맥'})
                </li>`;
            });
        }
        fullTextHTML += `
            <div style="margin-bottom: 20px; border-bottom: 1px dashed #ddd; padding-bottom: 10px;">
                <p style="font-weight: bold; color: var(--acrobat-red); margin: 0;">Page ${res.pageNum}</p>
                <div style="white-space: pre-wrap; line-height: 1.6; font-size: 11px;">${res.processedText}</div>
            </div>`;
    });

    if (totalCorrections === 0) {
        resultBox.innerHTML = `
            <div style="padding: 10px; border-bottom: 2px solid #eee; margin-bottom: 10px;">
                <p style="color: green; font-weight: bold; margin: 0;">✔ 전체 분석 결과: 문제가 발견되지 않았습니다.</p>
            </div>
            <div style="padding: 10px;">${fullTextHTML}</div>`;
    } else {
        resultBox.innerHTML = `
            <div style="padding: 10px; border-bottom: 2px solid #eee; margin-bottom: 15px; background-color: #fff9f9;">
                <p style="font-weight: bold; margin-top: 0; color: #d32f2f;">[전체 문서 교정 권장 사항 - 총 ${totalCorrections}건]</p>
                <ul style="margin: 0; padding-left: 15px; font-size: 11px; list-style: none;">
                    ${allCorrectionsHTML}
                </ul>
            </div>
            <div style="padding: 10px;">
                <p style="font-weight: bold; margin-top: 0; color: #666;">[페이지별 추출 텍스트 (교정 반영)]</p>
                ${fullTextHTML}
            </div>`;
    }
}

// 3. Export & Search (Updated for all pages)
function runExportText() {
    if (!extractedText) {
        alert("내보낼 데이터가 없습니다. 먼저 분석을 완료해 주세요.");
        return;
    }
    const blob = new Blob([extractedText], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `full_document_text_${new Date().getTime()}.txt`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

function runSearch() {
    if (pageResults.length === 0) {
        alert("검색할 데이터가 없습니다. 먼저 분석을 완료해 주세요.");
        return;
    }

    const keyword = prompt("전체 문서에서 검색할 단어를 입력하세요:");
    if (!keyword) return;

    let foundCount = 0;
    let searchHTML = `<div style="color: #333; font-size: 11px; margin-bottom: 10px; background: #f0f0f0; padding: 5px;">
                        '${keyword}' 전체 문서 검색 결과
                      </div>`;

    const regex = new RegExp(keyword, 'gi');

    pageResults.forEach(res => {
        const matches = res.originalText.match(regex);
        if (matches) {
            foundCount += matches.length;
            const highlighted = res.originalText.replace(regex, `<span style="background-color: #ff9; font-weight: bold;">$&</span>`);
            searchHTML += `
                <div style="margin-bottom: 15px; border-left: 3px solid orange; padding-left: 10px;">
                    <p style="font-weight: bold; font-size: 11px; margin: 0;">Page ${res.pageNum} (${matches.length}건)</p>
                    <div style="white-space: pre-wrap; font-size: 11px;">${highlighted}</div>
                </div>`;
        }
    });

    if (foundCount > 0) {
        resultBox.innerHTML = `<p style="font-weight: bold; color: blue; font-size: 12px;">총 ${foundCount}건 발견</p>` + searchHTML;
    } else {
        alert(`'${keyword}'을(를) 찾을 수 없습니다.`);
    }
}

// Event Listeners
ocrBtn.addEventListener('click', runFullAnalysis); // 추출 버튼도 전체 분석으로 연결
grammarBtn.addEventListener('click', runFullAnalysis);
exportBtn.addEventListener('click', runExportText);
searchBtn.addEventListener('click', runSearch);
