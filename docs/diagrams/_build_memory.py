"""Blender headless build — Memory hierarchy as a 3D ledger.

Five tier rows recede into the scene; each row pairs a candidate slab
(orange, left) with a live slab (blue, right), joined by a glowing
promote() connector. Renders memory.png + memory.coords.json.

Run:  blender --background --factory-startup --python _build_memory.py
"""
import bpy, math, mathutils, os, json
from bpy_extras.object_utils import world_to_camera_view

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "memory.png")
COORDS = os.path.join(HERE, "memory.coords.json")

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT'
RES_X, RES_Y = 1680, 1160
scene.render.resolution_x = RES_X
scene.render.resolution_y = RES_Y
scene.render.film_transparent = True
scene.view_settings.view_transform = 'AgX'
scene.view_settings.look = 'AgX - Punchy'
try:
    scene.eevee.use_raytracing = True
    scene.eevee.taa_render_samples = 200
except Exception:
    pass

world = bpy.data.worlds.new("w"); scene.world = world
world.use_nodes = True
bgn = world.node_tree.nodes["Background"]
bgn.inputs["Color"].default_value = (0.965, 0.915, 0.815, 1)
bgn.inputs["Strength"].default_value = 0.36

def clay(name, color, emit=0.0, rough=0.55):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = 0.32
    if emit > 0:
        b.inputs["Emission Color"].default_value = (*color, 1)
        b.inputs["Emission Strength"].default_value = emit
    return m

def box(name, loc, size, color, emit=0.0, bevel=0.08):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = size
    bv = ob.modifiers.new("b", "BEVEL")
    bv.width = bevel; bv.segments = 8; bv.harden_normals = True
    ob.data.materials.append(clay(name + "_m", color, emit=emit))
    bpy.ops.object.shade_smooth()
    return ob

def panel(loc, size, color, emit=0.0):
    box("p", (loc[0], loc[1], loc[2] + size[2] / 2), (size[0] * 0.8, size[1] * 0.72, 0.05),
        tuple(min(1, c * 1.15 + 0.03) for c in color), emit=emit, bevel=0.02)

ORANGE = (0.95, 0.55, 0.34)
BLUE = (0.29, 0.55, 0.86)
GREEN = (0.40, 0.66, 0.34)

# ---------- 5 tier rows ----------
TIERS = ["working", "episodic", "semantic", "procedural", "causal"]
SY = 1.78
CW, LW, D, H = 2.9, 2.9, 1.4, 0.5
CX, LX = -2.45, 2.45
anchors = {}

def entries(cx, y, top_z, tint, n=3, sealed=False):
    """small 'entry' cards sitting on a slab top — adds informative detail."""
    for k in range(n):
        ex = cx - (n - 1) * 0.46 + k * 0.92
        box("e", (ex, y, top_z + 0.075), (0.74, 0.86, 0.14),
            tint, emit=(0.6 if sealed else 0.0), bevel=0.025)
        if sealed:
            bpy.ops.mesh.primitive_cylinder_add(radius=0.07, depth=0.05,
                location=(ex, y, top_z + 0.16))
            c = bpy.context.active_object
            c.data.materials.append(clay("seal", (0.95, 0.95, 0.98), emit=2.0))
            bpy.ops.object.shade_smooth()

for i, tier in enumerate(TIERS):
    y = -i * SY
    star = (tier == "procedural")
    box("cand_%d" % i, (CX, y, 0.34), (CW, D, H), ORANGE, emit=0.05)
    panel((CX, y, 0.34), (CW, D, H), ORANGE, emit=0.02)
    box("live_%d" % i, (LX, y, 0.34), (LW, D, H), BLUE, emit=0.05)
    panel((LX, y, 0.34), (LW, D, H), BLUE, emit=0.02)
    # detail: loose unsealed entry cards on candidate, sealed ones on live
    top = 0.34 + H / 2
    entries(CX, y, top, (1.0, 0.78, 0.62), n=3, sealed=False)
    entries(LX, y, top, (0.62, 0.78, 0.96), n=3, sealed=True)
    # promote connector — a short glowing tube
    cu = bpy.data.curves.new("t", 'CURVE'); cu.dimensions = '3D'
    cu.bevel_depth = 0.07; cu.bevel_resolution = 4
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(2)
    for bp, co in zip(sp.bezier_points, [(CX + CW / 2, y, 0.4), (0, y, 0.95), (LX - LW / 2, y, 0.4)]):
        bp.co = co; bp.handle_left_type = bp.handle_right_type = 'AUTO'
    t = bpy.data.objects.new("promote_%d" % i, cu)
    bpy.context.collection.objects.link(t)
    t.data.materials.append(clay("pm_%d" % i, GREEN, emit=3.4))
    # a small glowing node mid-arc = the promote() gate
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.2, location=(0, y, 0.95))
    g = bpy.context.active_object
    g.data.materials.append(clay("g_%d" % i, GREEN, emit=4.5))
    bpy.ops.object.shade_smooth()
    anchors["cand_%d" % i] = mathutils.Vector((CX, y - D / 2, 0.62))
    anchors["live_%d" % i] = mathutils.Vector((LX, y - D / 2, 0.62))
    anchors["tier_%d" % i] = mathutils.Vector((CX - CW / 2, y, 0.62))

# ---------- ground ----------
bpy.ops.mesh.primitive_plane_add(size=120, location=(0, 0, 0.0))
bpy.context.active_object.is_shadow_catcher = True

# ---------- lighting ----------
def area(loc, energy, size, aim=None):
    bpy.ops.object.light_add(type='AREA', location=loc)
    L = bpy.context.active_object
    L.data.energy = energy; L.data.size = size
    if aim:
        L.rotation_euler = (mathutils.Vector(aim) - L.location).to_track_quat('-Z', 'Y').to_euler()
    return L

area((-9, 3, 13), 4200, 13, aim=(-1, -4, 0.5))
area((10, 1, 8), 1500, 16)
area((0, -16, 11), 2400, 15, aim=(0, -5, 0.5))

# ---------- camera ----------
bpy.ops.object.camera_add(location=(4.2, -23.5, 16.5))
cam = bpy.context.active_object
scene.camera = cam
cam.data.lens = 80
target = mathutils.Vector((0.0, -3.55, 0.15))
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
cam.data.dof.use_dof = True
cam.data.dof.focus_distance = (target - cam.location).length
cam.data.dof.aperture_fstop = 10.0

# ---------- project ----------
bpy.context.view_layer.update()
def proj(p):
    v = world_to_camera_view(scene, cam, p)
    return {"x": round(v.x, 4), "y": round(1.0 - v.y, 4)}
coords = {k: proj(v) for k, v in anchors.items()}
with open(COORDS, "w") as f:
    json.dump({"res": [RES_X, RES_Y], "anchors": coords}, f, indent=2)

scene.render.filepath = OUT
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
bpy.ops.render.render(write_still=True)
print("RENDERED_OK", OUT)
print("COORDS", json.dumps(coords))
