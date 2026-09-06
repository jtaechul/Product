// 저장소에 글을 쓰는 창구 — 관리자 화면에서 만든 문항이 여기로 나간다.
//
// 왜 DB가 아니라 저장소인가: 문항의 원본은 content/questions/*.json 이고 DB는 그 사본이다
// (배포 때 import.mjs 가 다시 밀어 넣는다). 관리자가 만든 문항만 DB에 두면 원본이 두 곳이 되고,
// 음원·사진을 만드는 배치가 그 문항을 영영 모른다 — 듣기 문항이면 소리가 끝내 안 붙는다.
// 저장소에 커밋하면 배포·음원·사진 배치가 지금 그대로 이어서 돌아간다.
//
// 커밋은 Git Data API 로 한다(파일 하나씩 올리는 Contents API 가 아니라).
// 새 문항은 원고와 ULID 매핑(.idmap.json)이 **한 커밋에 같이** 들어가야 하기 때문이다 —
// 따로 올리면 그 사이에 음원 배치가 돌아 러너가 제 마음대로 ULID 를 지어 버린다
// (2026-08-11 에 실제로 겪은 사고라 generate-tts.yml 이 그걸 검사해 실패시킨다).

const API = 'https://api.github.com';

export class GithubRepo {
  constructor(env) {
    this.token = env.GITHUB_TOKEN || '';
    // 저장소·브랜치는 설정으로 뺀다. 브랜치를 잘못 지정하면 배포가 안 걸릴 뿐이라 안전하다.
    this.repo = env.GITHUB_REPO || 'jtaechul/Product';
    this.branch = env.GITHUB_BRANCH || 'claude/junior-toeic-master-planning-322l2t';
    this.dir = env.GITHUB_DIR || 'junior-toeic-master';
  }

  get configured() { return Boolean(this.token); }

  async call(path, init = {}) {
    const r = await fetch(`${API}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${this.token}`,
        Accept: 'application/vnd.github+json',
        'Content-Type': 'application/json',
        // 깃허브는 User-Agent 없는 요청을 403으로 막는다
        'User-Agent': 'jumplish-admin',
        ...(init.headers || {}),
      },
    });
    if (!r.ok) {
      const body = await r.text().catch(() => '');
      // 토큰·경로 같은 내부 사정을 그대로 흘리지 않고, 사람이 할 수 있는 말로 바꾼다
      const why = r.status === 401 || r.status === 403
        ? '저장소에 글을 쓸 권한이 없습니다 (GITHUB_TOKEN 확인 필요)'
        : r.status === 404 ? '저장소나 브랜치를 찾지 못했습니다'
        : r.status === 409 ? '저장소가 방금 바뀌었습니다 — 잠시 후 다시 시도해주세요'
        : `저장소 요청 실패 (${r.status})`;
      const e = new Error(why);
      e.status = r.status;
      e.detail = body.slice(0, 300);
      throw e;
    }
    return r.status === 204 ? null : r.json();
  }

  // 파일 하나 읽기 — 없으면 null (새 파일을 만드는 경우)
  async readFile(relPath) {
    const p = `${this.dir}/${relPath}`;
    try {
      const j = await this.call(
        `/repos/${this.repo}/contents/${encodeURI(p)}?ref=${encodeURIComponent(this.branch)}`);
      // base64 는 줄바꿈이 섞여 오므로 걷어내고 디코드. 한글이 있으므로 UTF-8 로 되돌린다.
      const bytes = Uint8Array.from(atob(String(j.content).replace(/\n/g, '')), (ch) => ch.charCodeAt(0));
      return { text: new TextDecoder().decode(bytes), sha: j.sha };
    } catch (e) {
      if (e.status === 404) return null;
      throw e;
    }
  }

  // 파일 여러 개를 한 커밋으로. files: [{ path: 'content/questions/R1.json', text }]
  // 반환: { sha, url } — 화면에서 "이 커밋이 배포 중" 링크로 쓴다.
  async commitFiles(files, message) {
    const ref = await this.call(
      `/repos/${this.repo}/git/ref/heads/${encodeURIComponent(this.branch)}`);
    const baseSha = ref.object.sha;
    const baseCommit = await this.call(`/repos/${this.repo}/git/commits/${baseSha}`);

    // 내용을 blob 으로 올리고 그 목록으로 새 트리를 만든다.
    // 한글이 많아 base64 로 올린다 (utf-8 로 그냥 보내도 되지만 개행 처리가 엔진마다 다르다).
    const tree = [];
    for (const f of files) {
      const blob = await this.call(`/repos/${this.repo}/git/blobs`, {
        method: 'POST',
        body: JSON.stringify({ content: b64(f.text), encoding: 'base64' }),
      });
      tree.push({ path: `${this.dir}/${f.path}`, mode: '100644', type: 'blob', sha: blob.sha });
    }
    const newTree = await this.call(`/repos/${this.repo}/git/trees`, {
      method: 'POST',
      body: JSON.stringify({ base_tree: baseCommit.tree.sha, tree }),
    });
    const commit = await this.call(`/repos/${this.repo}/git/commits`, {
      method: 'POST',
      body: JSON.stringify({ message, tree: newTree.sha, parents: [baseSha] }),
    });
    // fast-forward 만 허용한다 — 그 사이 누가 먼저 올렸으면 실패해야 덮어쓰지 않는다
    await this.call(`/repos/${this.repo}/git/refs/heads/${encodeURIComponent(this.branch)}`, {
      method: 'PATCH',
      body: JSON.stringify({ sha: commit.sha, force: false }),
    });
    return { sha: commit.sha, url: `https://github.com/${this.repo}/commit/${commit.sha}` };
  }

  // ⚠ 워크플로를 API 로 직접 부르는 메서드는 두지 않는다.
  // GitHub 은 워크플로 파일이 **기본 브랜치**에 있어야 그 이름을 인식하는데, 이 저장소의
  // 점프리시 배치들은 전부 작업 브랜치에서만 산다. 그래서 dispatch 는 404 로 떨어진다
  // (2026-09-02 '부족한 문제 채우기' 버튼이 아무 일도 안 하던 원인).
  // 대신 requests/ 에 주문서를 커밋해 push 트리거로 돌린다 — 저장소의 다른 배치 10개와 같은 방식.
}

// UTF-8 문자열 → base64 (btoa 는 바이트만 받으므로 먼저 인코딩해야 한글이 깨지지 않는다)
function b64(text) {
  const bytes = new TextEncoder().encode(text);
  let s = '';
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s);
}
