// 위치 관련 유틸 — Geolocation + 거리 계산(Haversine)

// 두 좌표 사이 거리(미터)
export function distanceM(lat1, lng1, lat2, lng2) {
  const R = 6371000; // 지구 반지름(m)
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
}

// 현재 위치 1회 조회 (Promise). 실패 시 code/message 반환.
export function getCurrentPosition(options = {}) {
  const opts = {
    enableHighAccuracy: true,
    timeout: 10000,
    maximumAge: 0,
    ...options,
  };
  return new Promise((resolve, reject) => {
    if (!('geolocation' in navigator)) {
      reject({ code: 'UNSUPPORTED', message: '이 브라우저는 위치 기능을 지원하지 않습니다.' });
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
        accuracy: pos.coords.accuracy,
      }),
      (err) => {
        const map = {
          1: { code: 'DENIED', message: '위치 권한이 거부되었습니다. 브라우저 설정에서 위치 접근을 허용해 주세요.' },
          2: { code: 'UNAVAILABLE', message: '현재 위치를 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.' },
          3: { code: 'TIMEOUT', message: '위치 확인 시간이 초과되었습니다. 다시 시도해 주세요.' },
        };
        reject(map[err.code] || { code: 'ERROR', message: '위치 확인 중 오류가 발생했습니다.' });
      },
      opts
    );
  });
}

// 스탬프 지점 반경 안에 있는지 검사. { inside, distance } 반환
export function checkWithin(spot, pos) {
  const d = distanceM(pos.lat, pos.lng, spot.lat, spot.lng);
  return { inside: d <= spot.radiusM, distance: Math.round(d) };
}
