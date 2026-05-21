"""Blender headless build — Trust lattice: 5 trust-level slabs as a clean
3D ascending staircase with recessed top panels. Gates / deprecated / the
IntEnum note are added crisply in the HTML overlay, not in 3D (they
occlude badly between tight staircase steps).

Run:  blender --background --factory-startup --python _build_trust.py
"""
import bpy, math, mathutils, os, json
from bpy_extras.object_utils import world_to_camera_view

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "trust_lattice.png")
COORDS = os.path.join(HERE, "trust_lattice.coords.json")

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

scene.render.engine = 'BLENDER_EEVEE_NEXT'
RES_X, RES_Y = 1680, 1120
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

CREAM = (0.965, 0.915, 0.815)
world = bpy.data.worlds.new("w"); scene.world = world
world.use_nodes = True
bgn = world.node_tree.nodes["Background"]
bgn.inputs["Color"].default_value = (*CREAM, 1)
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

def box(name, loc, size, color, emit=0.0, bevel=0.075):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = size
    bv = ob.modifiers.new("bevel", "BEVEL")
    bv.width = bevel; bv.segments = 8; bv.harden_normals = True
    ob.data.materials.append(clay(name + "_m", color, emit=emit))
    bpy.ops.object.shade_smooth()
    return ob

# ---------- the 5-level staircase ----------
LEVELS = [
    ("raw",       (0.60, 0.58, 0.53), 0.0),
    ("untrusted", (0.93, 0.69, 0.17), 0.07),
    ("candidate", (0.96, 0.43, 0.26), 0.42),
    ("verified",  (0.22, 0.52, 0.88), 0.90),
    ("promoted",  (0.40, 0.70, 0.32), 1.85),
]
W, D, H = 2.3, 1.3, 0.56
STEP_Y, STEP_Z = 1.12, 0.80
anchors = {}

front_edge = []   # visible top-front edge of each slab, for the ascent ribbon
for i, (label, col, emit) in enumerate(LEVELS):
    y, z = -i * STEP_Y, i * STEP_Z
    box(label, (0, y, z), (W, D, H), col, emit=emit)
    # recessed top panel — a designed detail that reads in 3/4 view
    pc = tuple(min(1.0, c * 1.16 + 0.03) for c in col)
    box(label + "_panel", (0, y, z + H / 2 - 0.012),
        (W - 0.52, D - 0.42, 0.06), pc, emit=emit * 0.5, bevel=0.025)
    # two thin recessed "ledger" grooves on the slab front for extra detail
    for gy in (0.15, -0.15):
        box(label + "_gr", (0.5, y - D / 2 + 0.004, z + gy),
            (W - 1.7, 0.05, 0.05),
            tuple(max(0.0, c * 0.66) for c in col), bevel=0.012)
    # a small emissive gate stud at the front-left of each step above raw
    if i > 0:
        bpy.ops.mesh.primitive_cylinder_add(radius=0.13, depth=0.07,
            location=(-0.82, y - D / 2 + 0.02, z))
        st = bpy.context.active_object
        st.rotation_euler = (math.radians(90), 0, 0)
        st.data.materials.append(clay("stud%d" % i, (0.40, 0.66, 0.34), emit=4.5))
        bpy.ops.object.shade_smooth()
    anchors[label] = mathutils.Vector((0.0, y - D / 2, z))
    front_edge.append((0.78, y - D / 2 + 0.05, z + H / 2 + 0.03))

# glowing ascent ribbon along the visible top-front edge of the staircase
cu = bpy.data.curves.new("ascent", 'CURVE')
cu.dimensions = '3D'
cu.bevel_depth = 0.05
cu.bevel_resolution = 4
sp = cu.splines.new('BEZIER')
sp.bezier_points.add(len(front_edge) - 1)
for bp, co in zip(sp.bezier_points, front_edge):
    bp.co = co
    bp.handle_left_type = bp.handle_right_type = 'AUTO'
rib = bpy.data.objects.new("ascent", cu)
bpy.context.collection.objects.link(rib)
rib.data.materials.append(clay("ascent_m", (0.98, 0.88, 0.50), emit=5.5))

# ---------- ground (shadow catcher) ----------
bpy.ops.mesh.primitive_plane_add(size=90, location=(0, 0, -0.66))
bpy.context.active_object.is_shadow_catcher = True

# ---------- lighting ----------
def area(loc, energy, size, aim=None):
    bpy.ops.object.light_add(type='AREA', location=loc)
    L = bpy.context.active_object
    L.data.energy = energy; L.data.size = size
    if aim is not None:
        L.rotation_euler = (mathutils.Vector(aim) - L.location).to_track_quat('-Z', 'Y').to_euler()
    return L

area((-8, -7, 12), 2700, 11, aim=(0.0, -2.4, 1.6))
area((11, -6, 6), 720, 16)
area((-1, 7, 10), 1350, 12, aim=(0.0, -2.4, 2.0))

# ---------- camera ----------
bpy.ops.object.camera_add(location=(7.3, -21.5, 8.7))
cam = bpy.context.active_object
scene.camera = cam
cam.data.lens = 123
target = mathutils.Vector((0.05, -2.3, 1.6))
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
cam.data.dof.use_dof = True
cam.data.dof.focus_distance = (target - cam.location).length
cam.data.dof.aperture_fstop = 7.5

# ---------- project anchors ----------
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
