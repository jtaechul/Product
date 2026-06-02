"""
make_soyun.py — 소윤 Chibi 캐릭터 생성 스크립트 (Blender 4.0 bpy)

실행:
  blender --background --python night-hunter/blender/make_soyun.py

출력:
  night-hunter/assets/models/soyun.glb

구성:
  1) 절차적 메시 파츠 (sphere/cube/cylinder) → Join → Soyun_Mesh
  2) 12본 아마추어 배치 + 계층 → Soyun_Armature
  3) 자동 가중치 스키닝 (ARMATURE_AUTO)
  4) 3개 애니메이션 Action (Idle 60f / Walk 30f / Run 20f) → NLA 등록
  5) GLB 내보내기
"""

import bpy
import math
import os

# ─── 경로 ────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.normpath(
    os.path.join(SCRIPT_DIR, "..", "assets", "models", "soyun.glb"))
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

# ─── 씬 초기화 ───────────────────────────────────────────────────
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
bpy.context.scene.render.fps = 30

# ─── 머티리얼 헬퍼 ──────────────────────────────────────────────
def mat(name, hex_int):
    r = ((hex_int >> 16) & 0xFF) / 255.0
    g = ((hex_int >>  8) & 0xFF) / 255.0
    b = ((hex_int >>  0) & 0xFF) / 255.0
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
    bsdf.inputs["Roughness"].default_value  = 0.6
    return m

M = {
    'skin' : mat("skin",    0xffdbac),
    'white': mat("white",   0xffffff),
    'eye'  : mat("eye",     0x1a0a00),
    'unif' : mat("uniform", 0x1e3060),
    'hair' : mat("hair",    0x5a3a1f),
    'hat'  : mat("hat",     0x0d1b2a),
    'gold' : mat("gold",    0xFFD700),
    'black': mat("black",   0x111111),
}

# ─── 메시 파츠 헬퍼 ─────────────────────────────────────────────
_parts = []

def _reg(obj, mk):
    obj.data.materials.clear()
    obj.data.materials.append(M[mk])
    _parts.append(obj)
    return obj

def sphere(name, r, loc, mk, segs=16, rings=12):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segs, ring_count=rings, radius=r, location=loc)
    o = bpy.context.active_object
    o.name = name
    return _reg(o, mk)

def cube(name, sx, sy, sz, loc, mk):
    """sx/sy/sz: half-extent (±sx in X, ±sy in Y, ±sz in Z)"""
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(scale=True)
    return _reg(o, mk)

def cyl(name, r, d, loc, mk, v=8, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=v, radius=r, depth=d, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    return _reg(o, mk)

# ═══════════════════════════════════════════════════════════════
# 1. 메시 파츠 생성
# ═══════════════════════════════════════════════════════════════

# [머리]
sphere("head",      0.22,  (0,      0,      1.18), 'skin')

# [눈 흰자 L/R]
sphere("eye_wL",    0.055, (-0.09, -0.19,   1.20), 'white', segs=8, rings=6)
sphere("eye_wR",    0.055, ( 0.09, -0.19,   1.20), 'white', segs=8, rings=6)

# [눈동자 L/R]
sphere("eye_pL",    0.035, (-0.09, -0.215,  1.20), 'eye',   segs=8, rings=6)
sphere("eye_pR",    0.035, ( 0.09, -0.215,  1.20), 'eye',   segs=8, rings=6)

# [몸통] scale(0.22, 0.14, 0.18) → W=0.44, D=0.28, H=0.36
cube("torso",       0.22, 0.14, 0.18, (0, 0, 0.82), 'unif')

# [팔] 수평 배치 (Y축 90° 회전 → depth가 X 방향)
HR = math.radians(90)
cyl("arm_L",        0.055, 0.28, (-0.28, 0, 0.82), 'unif', rot=(0, HR, 0))
cyl("arm_R",        0.055, 0.28, ( 0.28, 0, 0.82), 'unif', rot=(0, HR, 0))

# [손]
sphere("hand_L",    0.055, (-0.44, 0, 0.82), 'skin', segs=8, rings=6)
sphere("hand_R",    0.055, ( 0.44, 0, 0.82), 'skin', segs=8, rings=6)

# [다리]
cyl("leg_L",        0.07, 0.28, (-0.10, 0, 0.54), 'unif')
cyl("leg_R",        0.07, 0.28, ( 0.10, 0, 0.54), 'unif')

# [발] scale(0.075, 0.12, 0.06) → W=0.15, D=0.24, H=0.12
cube("foot_L",      0.075, 0.12, 0.06, (-0.10, -0.04, 0.38), 'black')
cube("foot_R",      0.075, 0.12, 0.06, ( 0.10, -0.04, 0.38), 'black')

# [머리카락 — 소윤 긴 생머리]
cube("hair_top",    0.21, 0.10, 0.22, (0, 0.06, 1.18), 'hair')
cube("hair_long",   0.20, 0.06, 0.20, (0, 0.07, 0.95), 'hair')

# [경찰 모자 챙]
cyl("hat_brim",     0.24, 0.02, (0, 0, 1.36), 'hat', v=32)
# [경찰 모자 몸체]
cyl("hat_body",     0.17, 0.14, (0, 0, 1.44), 'hat', v=32)

# [가슴 배지]
cyl("badge",        0.04, 0.01, (-0.12, -0.14, 0.88), 'gold', v=6)

# ═══════════════════════════════════════════════════════════════
# 2. 전체 Join → Soyun_Mesh
# ═══════════════════════════════════════════════════════════════
bpy.ops.object.select_all(action='DESELECT')
for o in _parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = _parts[0]
bpy.ops.object.join()
mesh_obj = bpy.context.active_object
mesh_obj.name = "Soyun_Mesh"
print("[1/5] Soyun_Mesh 생성 완료")

# ═══════════════════════════════════════════════════════════════
# 3. 아마추어 (12본)
# ═══════════════════════════════════════════════════════════════
bpy.ops.object.armature_add(location=(0, 0, 0))
arm_obj       = bpy.context.active_object
arm_obj.name  = "Soyun_Armature"
arm_data      = arm_obj.data
arm_data.name = "Soyun_Armature"

bpy.ops.object.mode_set(mode='EDIT')
eb = arm_data.edit_bones
for b in list(eb):
    eb.remove(b)

BONES = [
    ("Root",       (0,     0, 0   ), (0,     0, 0.10)),
    ("Hips",       (0,     0, 0.60), (0,     0, 0.72)),
    ("Spine",      (0,     0, 0.72), (0,     0, 0.92)),
    ("Head",       (0,     0, 0.96), (0,     0, 1.42)),
    ("L_UpperArm", (-0.16, 0, 0.90), (-0.32, 0, 0.90)),
    ("L_ForeArm",  (-0.32, 0, 0.90), (-0.46, 0, 0.90)),
    ("R_UpperArm", ( 0.16, 0, 0.90), ( 0.32, 0, 0.90)),
    ("R_ForeArm",  ( 0.32, 0, 0.90), ( 0.46, 0, 0.90)),
    ("L_UpperLeg", (-0.10, 0, 0.68), (-0.10, 0, 0.54)),
    ("L_LowerLeg", (-0.10, 0, 0.54), (-0.10, 0, 0.38)),
    ("R_UpperLeg", ( 0.10, 0, 0.68), ( 0.10, 0, 0.54)),
    ("R_LowerLeg", ( 0.10, 0, 0.54), ( 0.10, 0, 0.38)),
]

_eb = {}
for name, head, tail in BONES:
    b = eb.new(name)
    b.head, b.tail = head, tail
    _eb[name] = b

PARENTS = [
    ("Hips",       "Root"),
    ("Spine",      "Hips"),
    ("Head",       "Spine"),
    ("L_UpperArm", "Spine"),    ("R_UpperArm", "Spine"),
    ("L_ForeArm",  "L_UpperArm"),("R_ForeArm", "R_UpperArm"),
    ("L_UpperLeg", "Hips"),     ("R_UpperLeg", "Hips"),
    ("L_LowerLeg", "L_UpperLeg"),("R_LowerLeg","R_UpperLeg"),
]
for child, parent in PARENTS:
    _eb[child].parent = _eb[parent]

bpy.ops.object.mode_set(mode='OBJECT')
print("[2/5] Soyun_Armature (12본) 생성 완료")

# ═══════════════════════════════════════════════════════════════
# 4. 스키닝 — 자동 가중치 (ARMATURE_AUTO)
# ═══════════════════════════════════════════════════════════════
bpy.ops.object.select_all(action='DESELECT')
mesh_obj.select_set(True)
arm_obj.select_set(True)
bpy.context.view_layer.objects.active = arm_obj
bpy.ops.object.parent_set(type='ARMATURE_AUTO')
print("[3/5] 자동 가중치 스키닝 완료")

# ═══════════════════════════════════════════════════════════════
# 5. 애니메이션
# ═══════════════════════════════════════════════════════════════
bpy.context.view_layer.objects.active = arm_obj
bpy.ops.object.mode_set(mode='POSE')
arm_obj.animation_data_create()

def pb(name):
    return arm_obj.pose.bones[name]

def rot_kf(bname, axis, kfs):
    """pose bone 회전 키프레임. axis: 0=X 1=Y 2=Z"""
    bone = pb(bname)
    bone.rotation_mode = 'XYZ'
    for f, v in kfs:
        re = [0.0, 0.0, 0.0]
        re[axis] = v
        bone.rotation_euler = re
        bone.keyframe_insert("rotation_euler", frame=f)

def loc_kf(bname, axis, kfs):
    """pose bone 위치 키프레임. axis: 0=X 1=Y 2=Z"""
    bone = pb(bname)
    for f, v in kfs:
        loc = [0.0, 0.0, 0.0]
        loc[axis] = v
        bone.location = loc
        bone.keyframe_insert("location", frame=f)

def sval(f, amp, period, offset=0):
    return amp * math.sin(2 * math.pi * (f + offset) / period)

# ── ① Idle (60프레임 = 2초 루프) ───────────────────────────
idle_act = bpy.data.actions.new("Idle")
arm_obj.animation_data.action = idle_act

for f in [0, 15, 30, 45, 60]:
    loc_kf("Hips",       1, [(f, sval(f, 0.005, 60))])           # Y 흔들림
    rot_kf("Spine",      0, [(f, sval(f, 0.02,  60))])           # X 호흡
    rot_kf("Head",       2, [(f, sval(f, 0.015, 80))])           # Z 미세 흔들
    rot_kf("L_UpperArm", 0, [(f, sval(f, 0.04,  60))])           # X 흔들
    rot_kf("R_UpperArm", 0, [(f, sval(f, 0.04,  60, offset=10))])

# ── ② Walk (30프레임 = 1초 루프) ───────────────────────────
walk_act = bpy.data.actions.new("Walk")
arm_obj.animation_data.action = walk_act

loc_kf("Hips",       2, [(0,0),   (8,0.03),  (15,0),    (23,0.03), (30,0)])
rot_kf("Hips",       1, [(0,0),   (15,0.05), (30,0)])
rot_kf("L_UpperLeg", 0, [(0, 0.5),(15,-0.5), (30, 0.5)])
rot_kf("R_UpperLeg", 0, [(0,-0.5),(15, 0.5), (30,-0.5)])
rot_kf("L_LowerLeg", 0, [(0,-0.2),(8,-0.4),  (15,0),    (23,-0.2),(30,-0.2)])
rot_kf("R_LowerLeg", 0, [(0, 0),  (8,-0.2),  (15,-0.4), (23, 0),  (30, 0)])
rot_kf("L_UpperArm", 0, [(0,-0.4),(15, 0.4), (30,-0.4)])
rot_kf("R_UpperArm", 0, [(0, 0.4),(15,-0.4), (30, 0.4)])

# ── ③ Run (20프레임 = 0.67초 루프) ─────────────────────────
run_act = bpy.data.actions.new("Run")
arm_obj.animation_data.action = run_act

loc_kf("Hips",       2, [(0,0),   (5,0.06),  (10,0),   (15,0.06),(20,0)])
rot_kf("Hips",       0, [(0,0.15),(20,0.15)])                     # 앞 기울기
rot_kf("Spine",      0, [(0,0.10),(20,0.10)])                     # 상체 기울기
rot_kf("L_UpperLeg", 0, [(0, 0.8),(10,-0.8), (20, 0.8)])
rot_kf("R_UpperLeg", 0, [(0,-0.8),(10, 0.8), (20,-0.8)])
rot_kf("L_LowerLeg", 0, [(0,-0.3),(5,-0.6),  (10,0),   (15,-0.3),(20,-0.3)])
rot_kf("R_LowerLeg", 0, [(0, 0),  (5,-0.3),  (10,-0.6),(15, 0),  (20, 0)])
rot_kf("L_UpperArm", 0, [(0,-0.7),(10, 0.7), (20,-0.7)])
rot_kf("R_UpperArm", 0, [(0, 0.7),(10,-0.7), (20, 0.7)])

bpy.ops.object.mode_set(mode='OBJECT')
print("[4/5] 애니메이션 3종 (Idle/Walk/Run) 키프레임 완료")

# ── NLA 등록 ────────────────────────────────────────────────
arm_obj.animation_data.action = None
nla = arm_obj.animation_data.nla_tracks

for action, dur in [(idle_act, 60), (walk_act, 30), (run_act, 20)]:
    track       = nla.new()
    track.name  = action.name
    strip       = track.strips.new(action.name, 1, action)
    strip.action_frame_start = 0
    strip.action_frame_end   = dur

# ═══════════════════════════════════════════════════════════════
# 6. GLB 내보내기
# ═══════════════════════════════════════════════════════════════
bpy.ops.export_scene.gltf(
    filepath                    = OUTPUT_PATH,
    export_format               = 'GLB',
    export_animations           = True,
    export_anim_single_armature = True,
    export_skins                = True,
    export_morph                = False,
    export_apply                = True,
)
print(f"[5/5] ✅ soyun.glb 내보내기 완료: {OUTPUT_PATH}")
