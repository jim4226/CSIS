"""Blender headless build — the 8-layer CSIS stack as a vertical 3D tower.

Eight matte-clay slabs stacked L0 (substrate, bottom) to L7 (safety, top),
each with a recessed top panel. Renders stack.png + stack.coords.json.

Run:  blender --background --factory-startup --python _build_stack.py
"""
import bpy, math, mathutils, os, json
from bpy_extras.object_utils import world_to_camera_view

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "stack.png")
COORDS = os.path.join(HERE, "stack.coords.json")

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT'
RES_X, RES_Y = 1500, 1280
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

def box(name, loc, size, color, emit=0.0, bevel=0.07):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = size
    bv = ob.modifiers.new("b", "BEVEL")
    bv.width = bevel; bv.segments = 8; bv.harden_normals = True
    ob.data.materials.append(clay(name + "_m", color, emit=emit))
    bpy.ops.object.shade_smooth()
    return ob

# L0 (bottom) .. L7 (top): id, colour, emission
LAYERS = [
    ("L0", (0.86, 0.66, 0.28), 0.05),   # substrate — gold
    ("L1", (0.95, 0.55, 0.34), 0.05),   # agent runtime — orange
    ("L2", (0.95, 0.55, 0.34), 0.05),   # memory
    ("L3", (0.95, 0.55, 0.34), 0.05),   # curiosity
    ("L4", (0.29, 0.55, 0.86), 0.30),   # verification — blue
    ("L5", (0.95, 0.55, 0.34), 0.05),   # improvement
    ("L6", (0.74, 0.68, 0.55), 0.0),    # meta — dim (deferred)
    ("L7", (0.42, 0.66, 0.34), 0.55),   # safety envelope — green
]
W, D, H = 3.5, 1.8, 0.5
STEP = 0.62
anchors = {}

for i, (lid, col, emit) in enumerate(LAYERS):
    z = i * STEP
    box(lid, (0, 0, z), (W, D, H), col, emit=emit)
    pc = tuple(min(1.0, c * 1.16 + 0.03) for c in col)
    box(lid + "_panel", (0, 0, z + H / 2 - 0.012),
        (W - 0.6, D - 0.45, 0.055), pc, emit=emit * 0.5, bevel=0.022)
    anchors[lid] = mathutils.Vector((0.0, -D / 2, z))

# ---------- ground (shadow catcher) ----------
bpy.ops.mesh.primitive_plane_add(size=90, location=(0, 0, -0.4))
bpy.context.active_object.is_shadow_catcher = True

# ---------- lighting ----------
def area(loc, energy, size, aim=None):
    bpy.ops.object.light_add(type='AREA', location=loc)
    L = bpy.context.active_object
    L.data.energy = energy; L.data.size = size
    if aim:
        L.rotation_euler = (mathutils.Vector(aim) - L.location).to_track_quat('-Z', 'Y').to_euler()
    return L

area((-8, -7, 9), 2700, 12, aim=(0, -1, 2.3))
area((10, -6, 5), 800, 16)
area((-1, 7, 8), 1500, 12, aim=(0, -1, 2.6))

# ---------- camera ----------
bpy.ops.object.camera_add(location=(9.2, -16.5, 6.4))
cam = bpy.context.active_object
scene.camera = cam
cam.data.lens = 116
target = mathutils.Vector((0.0, 0.0, 2.2))
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
cam.data.dof.use_dof = True
cam.data.dof.focus_distance = (target - cam.location).length
cam.data.dof.aperture_fstop = 8.0

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
