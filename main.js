const pdfUpload = document.getElementById('pdf-upload');
const checkButton = document.getElementById('check-button');
const pdfViewerContainer = document.getElementById('pdf-viewer-container');

pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://mozilla.github.io/pdf.js/build/pdf.worker.js';

checkButton.addEventListener('click', () => {
    const file = pdfUpload.files[0];
    if (!file) {
        alert('PDF 파일을 선택해주세요.');
        return;
    }

    const fileReader = new FileReader();
    fileReader.onload = function() {
        const typedarray = new Uint8Array(this.result);
        pdfjsLib.getDocument(typedarray).promise.then(pdf => {
            pdfViewerContainer.innerHTML = ''; // 이전 뷰어 내용 삭제
            for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
                pdf.getPage(pageNum).then(page => {
                    const canvas = document.createElement('canvas');
                    pdfViewerContainer.appendChild(canvas);

                    const viewport = page.getViewport({ scale: 1.5 });
                    const context = canvas.getContext('2d');
                    canvas.height = viewport.height;
                    canvas.width = viewport.width;

                    const renderContext = {
                        canvasContext: context,
                        viewport: viewport
                    };
                    page.render(renderContext);

                    page.getTextContent().then(textContent => {
                        // 여기에 텍스트 검사 로직을 추가합니다.
                        console.log(textContent.items.map(item => item.str).join(' '));
                    });
                });
            }
        });
    };
    fileReader.readAsArrayBuffer(file);
});