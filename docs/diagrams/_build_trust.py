"""Blender headless build — Trust lattice as a 3D ascending staircase.

Renders the 3D geometry only (no text). Prints normalized 2D screen
coordinates for each slab so crisp HTML text can be overlaid on top.

Run:  blender --background --factory-startup --python _build_trust.py
"""
import bpy, math, mathutils, os, json
from bpy_extras.object_utils import world_to_camera_view

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "trust_lattice.png")
COORDS = os.path.join(HERE, "trust_lattice.coords.json")

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ---------- render config ----------
scene.render.engine = 'BLENDER_EEVEE_NEXT'
RES_X, RES_Y = 1680, 1120
scene.render.resolution_x = RES_X
scene.render.resolution_y = RES_Y
scene.render.film_transparent = True
scene.view_settings.view_transform = 'AgX'
scene.view_settings.look = 'AgX - Punchy'
try:
    scene.eevee.use_raytracing = True
    scene.eevee.taa_render_samples = 160
except Exception:
    pass

CREAM = (0.965, 0.915, 0.815)

# ---------- world ----------
world = bpy.data.worlds.new("w"); scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (*CREAM, 1)
bg.inputs["Strength"].default_value = 0.34

# ---------- materials ----------
def clay(name, color, emit=0.0, rough=0.58):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = 0.3
    if emit > 0:
        b.inputs["Emission Color"].default_value = (*color, 1)
        b.inputs["Emission Strength"].default_value = emit
    return m

def slab(name, loc, size, color, emit=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = size
    bev = ob.modifiers.new("bevel", "BEVEL")
    bev.width = 0.075
    bev.segments = 8
    bev.harden_normals = True
    ob.data.materials.append(clay(name + "_m", color, emit=emit))
    bpy.ops.object.shade_smooth()
    return ob

# ---------- the 5-level staircase ----------
LEVELS = [
    ("raw",       (0.60, 0.58, 0.53), 0.0),
    ("untrusted", (0.92, 0.68, 0.18), 0.08),
    ("candidate", (0.95, 0.44, 0.27), 0.42),
    ("verified",  (0.24, 0.52, 0.86), 0.85),
    ("promoted",  (0.42, 0.68, 0.33), 1.7),
]
W, D, H = 2.3, 1.3, 0.54
STEP_Y, STEP_Z = 1.12, 0.80
anchors = {}      # label -> 3D point on the front face, for text overlay

for i, (label, col, emit) in enumerate(LEVELS):
    y = -i * STEP_Y
    z = i * STEP_Z
    slab(label, (0, y, z), (W, D, H), col, emit=emit)
    anchors[label] = mathutils.Vector((0.0, y - D / 2, z))

# ---------- ground (shadow catcher) ----------
bpy.ops.mesh.primitive_plane_add(size=90, location=(0, 0, -0.62))
bpy.context.active_object.is_shadow_catcher = True

# ---------- lighting ----------
def area(loc, energy, size, aim=None):
    bpy.ops.object.light_add(type='AREA', location=loc)
    L = bpy.context.active_object
    L.data.energy = energy
    L.data.size = size
    if aim is not None:
        L.rotation_euler = (mathutils.Vector(aim) - L.location).to_track_quat('-Z', 'Y').to_euler()
    return L

area((-8, -7, 12), 2600, 11, aim=(0.0, -2.4, 1.6))   # key
area((11, -6, 6), 700, 16)                            # fill
area((-1, 7, 10), 1300, 12, aim=(0.0, -2.4, 2.0))    # rim

# ---------- camera: gentle 3/4, long lens, framed with margin ----------
bpy.ops.object.camera_add(location=(7.2, -21.5, 8.6))
cam = bpy.context.active_object
scene.camera = cam
cam.data.lens = 125
target = mathutils.Vector((0.0, -2.25, 1.55))
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
cam.data.dof.use_dof = True
cam.data.dof.focus_distance = (target - cam.location).length
cam.data.dof.aperture_fstop = 7.0

# ---------- project anchors to 2D screen space ----------
bpy.context.view_layer.update()
coords = {}
for label, p in anchors.items():
    v = world_to_camera_view(scene, cam, p)
    coords[label] = {"x": round(v.x, 4), "y": round(1.0 - v.y, 4)}  # y flipped to top-down
with open(COORDS, "w") as f:
    json.dump({"res": [RES_X, RES_Y], "anchors": coords}, f, indent=2)

# ---------- render ----------
scene.render.filepath = OUT
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
bpy.ops.render.render(write_still=True)
print("RENDERED_OK", OUT)
print("COORDS", json.dumps(coords))
