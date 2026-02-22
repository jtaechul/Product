// Initialize Lucide Icons
lucide.createIcons();

// Elements
const ocrBtn = document.getElementById('ocr-extract-btn');
const grammarBtn = document.getElementById('grammar-check-btn');
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
let extractedText = "";
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
    
    // Update UI
    pageInput.value = num;
}

// Page Navigation Events
prevBtn.onclick = () => {
    if (currentPageNum <= 1) return;
    currentPageNum--;
    renderPage(currentPageNum);
};

nextBtn.onclick = () => {
    if (currentPageNum >= pdfDoc.numPages) return;
    currentPageNum++;
    renderPage(currentPageNum);
};

pageInput.onchange = (e) => {
    const num = parseInt(e.target.value);
    if (num > 0 && num <= pdfDoc.numPages) {
        currentPageNum = num;
        renderPage(currentPageNum);
    }
};

// 2. Hybrid Extract function (Text + OCR)
async function runExtract() {
    if (!pdfDoc || !canvas) {
        alert("먼저 PDF 파일을 불러와 주세요.");
        return;
    }

    resultBox.innerHTML = '<p style="color: #666; text-align: center;">텍스트 분석 중...</p>';
    
    try {
        const page = await pdfDoc.getPage(currentPageNum);
        const textContent = await page.getTextContent();
        
        // Check if there is native text layer
        if (textContent.items.length > 0) {
            extractedText = textContent.items.map(item => item.str).join(' ');
            resultBox.innerHTML = `<div style="color: blue; font-size: 11px; margin-bottom: 5px;">[텍스트 레이어 직접 추출 완료]</div>
                                   <div style="white-space: pre-wrap;">${extractedText}</div>`;
        } else {
            // No text layer, run OCR
            await runOCR();
        }
    } catch (error) {
        console.error(error);
        resultBox.innerHTML = '<p style="color: red;">텍스트 추출 중 오류가 발생했습니다.</p>';
    }
}

async function runOCR() {
    resultBox.innerHTML = '<p style="color: #666; text-align: center;">이미지 분석(OCR) 중... (한국어 데이터 로드)</p>';
    
    try {
        const worker = await Tesseract.createWorker({
            logger: m => {
                if (m.status === 'recognizing text') {
                    const progress = Math.round(m.progress * 100);
                    resultBox.innerHTML = `<p style="text-align: center;">OCR 인식 중: ${progress}%</p>`;
                }
            }
        });

        await worker.loadLanguage('kor+eng');
        await worker.initialize('kor+eng');

        const { data: { text } } = await worker.recognize(canvas);
        extractedText = text;

        if (extractedText.trim() === "") {
            resultBox.innerHTML = '<p style="color: orange; text-align: center;">텍스트를 찾을 수 없습니다.</p>';
        } else {
            resultBox.innerHTML = `<div style="color: orange; font-size: 11px; margin-bottom: 5px;">[이미지 OCR 추출 완료]</div>
                                   <div style="white-space: pre-wrap;">${extractedText}</div>`;
        }
        await worker.terminate();
    } catch (error) {
        console.error(error);
        resultBox.innerHTML = '<p style="color: red;">OCR 처리 중 오류가 발생했습니다.</p>';
    }
}

// 3. Grammar Check function
function runGrammarCheck() {
    if (!extractedText) {
        alert("먼저 텍스트를 추출해 주세요.");
        return;
    }

    resultBox.innerHTML = '<p style="color: #666; text-align: center;">문맥 분석 중...</p>';

    setTimeout(() => {
        const commonErrors = [
            { pattern: /반갑습니가/g, replacement: "반갑습니다", reason: "오타 교정" },
            { pattern: /있슴니다/g, replacement: "있습니다", reason: "종결 어미 오류" },
            { pattern: /않돼요/g, replacement: "안 돼요", reason: "부정어 표기 오류" },
            { pattern: /되요/g, replacement: "돼요", reason: "어미 활용 오류" },
            { pattern: /애양환경공단/g, replacement: "해양환경공단", reason: "OCR 인식 오류 수정" }
        ];

        let highlightedText = extractedText;
        let foundAny = false;

        commonErrors.forEach(item => {
            if (item.pattern.test(highlightedText)) {
                foundAny = true;
                highlightedText = highlightedText.replace(
                    item.pattern, 
                    `<span style="background-color: #ffcccc; border-bottom: 2px solid red; cursor: help;" title="${item.reason}">$1</span> → <b style="color: green;">${item.replacement}</b>`
                );
            }
        });

        if (!foundAny) {
            resultBox.innerHTML = `<div style="white-space: pre-wrap;">${extractedText}</div><hr><p style="color: green; text-align: center;">분석 결과: 문제가 발견되지 않았습니다.</p>`;
        } else {
            resultBox.innerHTML = `<div style="white-space: pre-wrap; line-height: 1.8;">${highlightedText}</div>
                                   <div style="margin-top: 15px; font-size: 11px; color: #666; border-top: 1px dashed #ccc; padding-top: 10px;">
                                   * 빨간색 표시: 발견된 오류 제안</div>`;
        }
    }, 800);
}

// Event Listeners
ocrBtn.addEventListener('click', runExtract);
grammarBtn.addEventListener('click', runGrammarCheck);
