"""
make_hayun.py — 하윤 chibi 3D 캐릭터 생성 후 GLB로 내보내기
실행: blender --background --python make_hayun.py
출력: output/hayun.glb
"""
import bpy
import os

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "output", "hayun.glb")

# 팔레트 (하윤)
SKIN   = (1.00, 0.88, 0.78, 1)
HAIR   = (0.29, 0.16, 0.06, 1)
EYE    = (0.23, 0.51, 0.83, 1)   # 파란 눈
UNIF   = (0.12, 0.19, 0.38, 1)
GOLD   = (0.83, 0.66, 0.13, 1)
BLACK  = (0.07, 0.07, 0.07, 1)
LIP    = (0.82, 0.44, 0.38, 1)
GREEN  = (0.18, 0.55, 0.24, 1)   # 헤어밴드

def mat(name, color):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = color
    return m

def sphere(name, r, loc, color, segs=12):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=segs, ring_count=segs//2)
    obj = bpy.context.active_object
    obj.name = name
    obj.data.materials.append(mat(name+"_mat", color))
    return obj

def box(name, sx, sy, sz, loc, color):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (sx/2, sz/2, sy/2)
    bpy.ops.object.transform_apply(scale=True)
    obj.data.materials.append(mat(name+"_mat", color))
    return obj

def cylinder(name, r, h, loc, color, verts=12):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, location=loc, vertices=verts)
    obj = bpy.context.active_object
    obj.name = name
    obj.data.materials.append(mat(name+"_mat", color))
    return obj

# ── 씬 초기화 ──
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# ── 머리 ──
sphere("hair_back", 0.52, (0, -0.04, 1.90), HAIR)
sphere("face",      0.50, (0,  0.00, 1.90), SKIN)
box("bangs", 0.82, 0.20, 0.18, (0, 0.34, 2.28), HAIR)

# 양갈래 머리 (땋기 느낌)
for sign in [-1, 1]:
    cylinder(f"braid_up_{sign}", 0.10, 0.40, (sign*0.46, 0, 1.62), HAIR)
    cylinder(f"braid_dn_{sign}", 0.08, 0.35, (sign*0.46, 0, 1.22), HAIR)

# 녹색 헤어밴드
cylinder("headband", 0.56, 0.05, (0, 0, 2.08), GREEN)

# 눈 (흰자 + 홍채 — 파란색)
for sign, prefix in [(-1,"L"), (1,"R")]:
    sphere(f"eye_w_{prefix}", 0.12, (sign*0.19,  0.45, 1.94), (1,1,1,1))
    sphere(f"eye_i_{prefix}", 0.09, (sign*0.19,  0.48, 1.92), EYE)
    sphere(f"eye_p_{prefix}", 0.05, (sign*0.19,  0.505,1.91), (0.04,0.10,0.23,1))
    sphere(f"eye_hl_{prefix}",0.03, (sign*0.19-0.04, 0.515, 1.97), (1,1,1,1))

# 볼 홍조
for sign in [-1, 1]:
    s = sphere(f"blush_{sign}", 0.12, (sign*0.32, 0.42, 1.79), (1,0.6,0.6,0.5))
    s.scale.z = 0.45

# 코
sphere("nose", 0.025, (0, 0.50, 1.80), (0.83, 0.63, 0.44, 1))

# 입
bpy.ops.mesh.primitive_torus_add(
    major_radius=0.065, minor_radius=0.016,
    location=(0, 0.49, 1.69)
)
mouth = bpy.context.active_object
mouth.name = "mouth"
mouth.data.materials.append(mat("mouth_mat", LIP))

# ── 경찰 모자 ──
cylinder("hat_brim",  0.60, 0.05, (0, 0, 2.12), BLACK)
sphere("hat_dome",    0.53, (0, 0, 2.32), (0.10, 0.17, 0.31, 1))
cylinder("hat_band",  0.54, 0.06, (0, 0, 2.22), GOLD)
sphere("hat_badge",   0.08, (0, 0.44, 2.42), GOLD)

# ── 몸통 ──
box("torso",  0.78, 0.68, 0.44, (0, 0, 1.05), UNIF)
box("collar", 0.24, 0.20, 0.09, (0, 0.23, 1.34), (0.9,0.9,0.9,1))
box("tie",    0.09, 0.26, 0.05, (0, 0.235,1.18), (0.06,0.09,0.22,1))
cylinder("badge_chest", 0.075, 0.04, (-0.22, 0.23, 1.22), GOLD)

for y in [1.28, 1.12, 0.96, 0.82]:
    sphere(f"btn_{y:.2f}", 0.028, (0, 0.234, y), GOLD)

for sign in [-1, 1]:
    box(f"epaulet_{sign}", 0.22, 0.07, 0.24, (sign*0.40, 0, 1.38), UNIF)
    box(f"stripe_{sign}",  0.22, 0.03, 0.24, (sign*0.40, 0, 1.40), GOLD)

box("belt",   0.80, 0.11, 0.46, (0, 0, 0.77), BLACK)
box("buckle", 0.13, 0.11, 0.05, (0, 0.245, 0.77), GOLD)
for sign in [-1, 1]:
    box(f"pouch_{sign}", 0.13, 0.14, 0.09, (sign*0.24, 0.24, 0.75), BLACK)

# 헤드셋 (하윤 전용)
cylinder("headset_band", 0.55, 0.04, (0, 0, 2.36), BLACK)
for sign in [-1, 1]:
    cylinder(f"earpiece_{sign}", 0.10, 0.06, (sign*0.56, 0, 1.90), (0.2,0.2,0.2,1))
cylinder("mic", 0.025, 0.18, (-0.42, 0.28, 1.75), (0.2,0.2,0.2,1))

# ── 팔 ──
for sign, pref in [(-1,"L"), (1,"R")]:
    cylinder(f"arm_up_{pref}", 0.112, 0.46, (sign*0.47, 0, 1.07), UNIF)
    cylinder(f"arm_lo_{pref}", 0.095, 0.20, (sign*0.47, 0, 0.74), UNIF)
    sphere(f"hand_{pref}",     0.092, (sign*0.47, 0, 0.60), SKIN)

# ── 다리 ──
for sign, pref in [(-1,"L"), (1,"R")]:
    cylinder(f"leg_up_{pref}", 0.145, 0.42, (sign*0.19, 0, 0.53), UNIF)
    cylinder(f"leg_lo_{pref}", 0.122, 0.33, (sign*0.19, 0, 0.165), UNIF)
    box(f"boot_{pref}",  0.21, 0.155, 0.34, (sign*0.19, 0.04, -0.03), BLACK)

# ── GLB 내보내기 ──
bpy.ops.object.select_all(action='SELECT')
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
bpy.ops.export_scene.gltf(
    filepath=OUTPUT_PATH,
    export_format='GLB',
    use_selection=True,
    export_apply=True,
)
print(f"[make_hayun] 내보내기 완료: {OUTPUT_PATH}")
