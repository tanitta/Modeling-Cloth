# You are at the top. If you attempt to go any higher
#   you will go beyond the known limits of the code
#   universe where there are most certainly monsters

# might be able to get a speedup where I'm appending move and -move

# to do:
#  use point raycaster to make a cloth_wrap option
#  self colisions
    # maybe do dynamic margins for when cloth is moving fast
#  object collisions
    # collisions need to properly exclude pinned and vertex pinned
#  add bending springs
#  add curl by shortening bending springs on one axis or diagonal
#  independantly scale bending springs and structural to create buckling
#  option to cache animation?
#  Custom Source shape option for animated shapes


# collisions:
# Only need to check one of the edges for groups connected to a vertex    
# for edge to face intersections...
# figure out where the edge hit the face
# figure out which end of the edge is inside the face
# move along the face normal to the surface for the point inside.
# if I reflect by flipping the vel around the face normal
#   if it collides on the bounce it will get caught on the next iteration

# Sewing
# Could create super sewing that doesn't use edges but uses scalars along the edge to place virtual points
#   sort of a barycentric virtual spring. Could even use it to sew to faces if I can think of a ui for where on the face.
# On an all triangle mesh, where sew edges come together there are long strait lines. This probably causes those edges to fold.
#   in other words... creating diagonal springs between these edges will not solve the fold problem. Bend spring could do this.

# Bend springs:
# need to speed things up
# When faces have various sizes, the forces don't add up

# self collision
#   where points are pinned, stuff is all jittery
'''??? Would it make sense to do self collisions with virtual edges ???'''
'''??? Could do dynamic collision margins for stuff moving fast ???'''




bl_info = {
    "name": "Modeling Cloth",
    "author": "Rich Colburn, email: the3dadvantage@gmail.com",
    "version": (1, 0),
    "blender": (2, 78, 0),
    "location": "View3D > Extended Tools > Modeling Cloth",
    "description": "Maintains the surface area of an object so it behaves like cloth",
    "warning": "There might be an angry rhinoceros behind you",
    "wiki_url": "",
    "category": '3D View'}


import bpy
import bmesh
import numpy as np
from numpy import newaxis as nax
from bpy_extras import view3d_utils
import time

from . import guide_mesh
from . import collider 
from . import geometry 

#enable_numexpr = True
enable_numexpr = False
if enable_numexpr:
    import numexpr as ne

you_have_a_sense_of_humor = False
#you_have_a_sense_of_humor = True
if you_have_a_sense_of_humor:
    import antigravity








def get_last_object():
    """Finds cloth objects for keeping settings active
    while selecting other objects like pins"""
    cloths = [i for i in bpy.data.objects if i.modeling_cloth] # so we can select an empty and keep the settings menu up
    if bpy.context.object.modeling_cloth:
        return cloths, bpy.context.object
    
    if len(cloths) > 0:
        ob = extra_data['last_object']
        return cloths, ob
    return None, None


def get_poly_centers(ob, type=np.float32, mesh=None):
    mod = False
    m_count = len(ob.modifiers)
    if m_count > 0:
        show = np.zeros(m_count, dtype=np.bool)
        ren_set = np.copy(show)
        ob.modifiers.foreach_get('show_render', show)
        ob.modifiers.foreach_set('show_render', ren_set)
        mod = ue
    p_count = len(mesh.polygons)
    center = np.zeros(p_count * 3, dtype=type)
    mesh.polygons.foreach_get('center', center)
    center.shape = (p_count, 3)
    if mod:
        ob.modifiers.foreach_set('show_render', show)

    return center


def simple_poly_centers(ob, key=None):
    if key is not None:
        s_key = ob.data.shape_keys.key_blocks[key].data
        return np.squeeze([[np.mean([ob.data.vertices[i].co for i in p.vertices], axis=0)] for p in ob.data.polygons])


def get_poly_normals(ob, type=np.float32, mesh=None):
    mod = False
    m_count = len(ob.modifiers)
    if m_count > 0:
        show = np.zeros(m_count, dtype=np.bool)
        ren_set = np.copy(show)
        ob.modifiers.foreach_get('show_render', show)
        ob.modifiers.foreach_set('show_render', ren_set)
        mod = True
    p_count = len(mesh.polygons)
    normal = np.zeros(p_count * 3, dtype=type)
    mesh.polygons.foreach_get('normal', normal)
    normal.shape = (p_count, 3)
    if mod:
        ob.modifiers.foreach_set('show_render', show)

    return normal


def get_v_normals(ob, arr, mesh):
    """Since we're reading from a shape key we have to use
    a proxy mesh."""
    mod = False
    m_count = len(ob.modifiers)
    if m_count > 0:
        show = np.zeros(m_count, dtype=np.bool)
        ren_set = np.copy(show)
        ob.modifiers.foreach_get('show_render', show)
        ob.modifiers.foreach_set('show_render', ren_set)
        mod = True
    #v_count = len(mesh.vertices)
    #normal = np.zeros(v_count * 3)#, dtype=type)
    mesh.vertices.foreach_get('normal', arr.ravel())
    #normal.shape = (v_count, 3)
    if mod:
        ob.modifiers.foreach_set('show_render', show)


def get_v_nor(ob, nor_arr):
    ob.data.vertices.foreach_get('normal', nor_arr.ravel())
    return nor_arr


def closest_point_edge(e1, e2, p):
    '''Returns the location of the point on the edge'''
    vec1 = e2 - e1
    vec2 = p - e1
    d = np.dot(vec2, vec1) / np.dot(vec1, vec1)
    cp = e1 + vec1 * d 
    return cp


def create_vertex_groups(groups=['common', 'not_used'], weights=[0.0, 0.0], ob=None):
    '''Creates vertex groups and sets weights. "groups" is a list of strings
    for the names of the groups. "weights" is a list of weights corresponding 
    to the strings. Each vertex is assigned a weight for each vertex group to
    avoid calling vertex weights that are not assigned. If the groups are
    already present, the previous weights will be preserved. To reset weights
    delete the created groups'''
    if ob is None:
        ob = bpy.context.object
    vg = ob.vertex_groups
    for g in range(0, len(groups)):
        if groups[g] not in vg.keys(): # Don't create groups if there are already there
            vg.new(groups[g])
            vg[groups[g]].add(range(0,len(ob.data.vertices)), weights[g], 'REPLACE')
        else:
            vg[groups[g]].add(range(0,len(ob.data.vertices)), 0, 'ADD') # This way we avoid resetting the weights for existing groups.


def get_bmesh(obj=None):
    ob = get_last_object()[1]
    if ob is None:
        ob = obj
    obm = bmesh.new()
    if ob.mode == 'OBJECT':
        obm.from_mesh(ob.data)
    elif ob.mode == 'EDIT':
        obm = bmesh.from_edit_mesh(ob.data)
    return obm


def get_minimal_edges(ob):
    obm = get_bmesh(ob)
    obm.edges.ensure_lookup_table()
    obm.verts.ensure_lookup_table()
    obm.faces.ensure_lookup_table()
    
    # get sew edges:
    sew = [i.index for i in obm.edges if len(i.link_faces)==0]
    
    
    
    # so if I have a vertex with one or more sew edges attached
    # I need to get the mean location of all verts shared by those edges
    # every one of those verts needs to move towards the total mean
    
    
    # get linear edges
    e_count = len(obm.edges)
    eidx = np.zeros(e_count * 2, dtype=np.int32)
    e_bool = np.zeros(e_count, dtype=np.bool)
    e_bool[sew] = True
    ob.data.edges.foreach_get('vertices', eidx)
    eidx.shape = (e_count, 2)

    # get diagonal edges:
    diag_eidx = []
    start = 0
    stop = 0
    step_size = [len(i.verts) for i in obm.faces]
    p_v_count = np.sum(step_size)
    p_verts = np.ones(p_v_count, dtype=np.int32)
    ob.data.polygons.foreach_get('vertices', p_verts)
    # can only be understood on a good day when the coffee flows (uses rolling and slicing)
    # creates uniqe diagonal edge sets
    for f in obm.faces:
        fv_count = len(f.verts)
        stop += fv_count
        if fv_count > 3: # triangles are already connected by linear springs
            skip = 2
            f_verts = p_verts[start:stop]
            for fv in range(len(f_verts)):
                if fv > 1:        # as we go around the loop of verts in face we start overlapping
                    skip = fv + 1 # this lets us skip the overlap so we don't have mirror duplicates
                roller = np.roll(f_verts, fv)
                for r in roller[skip:-1]:
                    diag_eidx.append([roller[0], r])

        start += fv_count    
    
    # eidx groups
    sew_eidx = eidx[e_bool]
    lin_eidx = eidx[~e_bool]
    diag_eidx = np.array(diag_eidx)
    
    # deal with sew verts connected to more than one edge
    s_t_rav = sew_eidx.T.ravel()
    s_uni, s_inv, s_counts = np.unique(s_t_rav,return_inverse=True, return_counts=True)
    s_multi = s_counts > 1
    
    multi_groups = None
    if np.any(s_counts):
        multi_groups = []
        ls = sew_eidx[:,0]
        rs = sew_eidx[:,1]
        
        for i in s_uni[s_multi]:
            gr = np.array([i])
            gr = np.append(gr, ls[rs==i])
            gr = np.append(gr, rs[ls==i])
            multi_groups.append(gr)
        
    return lin_eidx, diag_eidx, sew_eidx, multi_groups


def add_virtual_springs(remove=False):
    cloth = data[get_last_object()[1].name]
    obm = get_bmesh()
    obm.verts.ensure_lookup_table()
    count = len(obm.verts)
    idxer = np.arange(count, dtype=np.int32)
    sel = np.array([v.select for v in obm.verts])    
    selected = idxer[sel]

    if remove:
        ls = cloth.virtual_springs[:, 0]
        
        in_sel = np.in1d(ls, idxer[sel])

        deleter = np.arange(ls.shape[0], dtype=np.int32)[in_sel]
        reduce = np.delete(cloth.virtual_springs, deleter, axis=0)
        cloth.virtual_springs = reduce
        
        if cloth.virtual_springs.shape[0] == 0:
            cloth.virtual_springs.shape = (0, 2)
        return

    existing = np.append(cloth.eidx, cloth.virtual_springs, axis=0)
    flip = existing[:, ::-1]
    existing = np.append(existing, flip, axis=0)
    ls = existing[:,0]
        
    springs = []
    for i in idxer[sel]:

        # to avoid duplicates:
        # where this vert occurs on the left side of the existing spring list
        v_in = existing[i == ls]
        v_in_r = v_in[:,1]
        not_in = selected[~np.in1d(selected, v_in_r)]
        idx_set = not_in[not_in != i]
        for sv in idx_set:
            springs.append([i, sv])
    virtual_springs = np.array(springs, dtype=np.int32)
    
    if virtual_springs.shape[0] == 0:
        virtual_springs.shape = (0, 2)
    
    cloth.virtual_springs = np.append(cloth.virtual_springs, virtual_springs, axis=0)
    # gets appended to eidx in the cloth_init function after calling get connected polys in case geometry changes

def scale_source(multiplier):
    """grow or shrink the source shape"""
    ob = get_last_object()[1]
    if ob is not None:
        if ob.modeling_cloth:
            count = len(ob.data.vertices)
            co = np.zeros(count*3, dtype=np.float32)
            ob.data.shape_keys.key_blocks['modeling cloth source key'].data.foreach_get('co', co)
            co.shape = (count, 3)
            mean = np.mean(co, axis=0)
            co -= mean
            co *= multiplier
            co += mean
            ob.data.shape_keys.key_blocks['modeling cloth source key'].data.foreach_set('co', co.ravel())                
            if hasattr(data[ob.name], 'cy_dists'):
                data[ob.name].cy_dists *= multiplier
            

def reset_shapes(ob=None):
    """Sets the modeling cloth key to match the source key.
    Will regenerate shape keys if they are missing"""
    if ob is None:    
        if bpy.context.object.modeling_cloth:
            ob = bpy.context.object
        else:    
            ob = extra_data['last_object']

    if ob.data.shape_keys == None:
        ob.shape_key_add('Basis')    
    if 'modeling cloth source key' not in ob.data.shape_keys.key_blocks:
        ob.shape_key_add('modeling cloth source key')        
    if 'modeling cloth key' not in ob.data.shape_keys.key_blocks:
        ob.shape_key_add('modeling cloth key')        
        ob.data.shape_keys.key_blocks['modeling cloth key'].value=1
    
    keys = ob.data.shape_keys.key_blocks
    count = len(ob.data.vertices)
    co = np.zeros(count * 3, dtype=np.float32)
    keys['Basis'].data.foreach_get('co', co)
    #co = applied_key_co(ob, None, 'modeling cloth source key')
    #keys['modeling cloth source key'].data.foreach_set('co', co)
    keys['modeling cloth key'].data.foreach_set('co', co)
    
    # reset the data stored in the class
    data[ob.name].vel[:] = 0
    co.shape = (co.shape[0]//3, 3)
    data[ob.name].co = co
    
    keys['modeling cloth key'].mute = True
    keys['modeling cloth key'].mute = False


def get_spring_mix(ob, eidx):
    rs = []
    ls = []
    minrl = []
    for i in eidx:
        r = eidx[eidx == i[1]].shape[0]
        l = eidx[eidx == i[0]].shape[0]
        rs.append (min(r,l))
        ls.append (min(r,l))
    mix = 1 / np.array(rs + ls) ** 1.2
    
    return mix
        

def update_pin_group():
    """Updates the cloth data after changing mesh or vertex weight pins"""
    create_instance(new=False)


def collision_data_update(self, context):
    if self.modeling_cloth_self_collision:    
        create_instance(new=False)    


def refresh_noise(self, context):
    if self.name in data:
        zeros = np.zeros(data[self.name].count, dtype=np.float32)
        random = np.random.random(data[self.name].count)
        zeros[:] = random
        data[self.name].noise = ((zeros + -0.5) * self.modeling_cloth_noise * 0.1)[:, nax]


def generate_wind(wind_vec, cloth):
    """Maintains a wind array and adds it to the cloth vel"""    
    
    tri_nor = cloth.normals # non-unit calculated by tri_normals_in_place() per each triangle
    w_vec = geometry.revert_rotation(cloth.ob, wind_vec)

    turb = cloth.ob.modeling_cloth_turbulence    
    if turb != 0: 
        w_vec += np.random.random(3).astype(np.float32) * turb * np.mean(w_vec) * 4

    # only blow on verts facing the wind
    perp = np.abs(tri_nor @ w_vec)
    cloth.wind += w_vec
    cloth.wind *= perp[:, nax][:, nax]
    
    # reshape for add.at
    shape = cloth.wind.shape
    cloth.wind.shape = (shape[0] * 3, 3)
    
    cloth.wind *= cloth.tri_mix
    np.add.at(cloth.vel, cloth.tridex.ravel(), cloth.wind)
    cloth.wind.shape = shape


def generate_inflate(cloth):
    """Blow it up baby!"""    
    
    tri_nor = cloth.normals #* cloth.ob.modeling_cloth_inflate # non-unit calculated by tri_normals_in_place() per each triangle
    #tri_nor /= np.einsum("ij, ij->i", tri_nor, tri_nor)[:, nax]
    
    # reshape for add.at
    shape = cloth.inflate.shape
    
    cloth.inflate += tri_nor[:, nax] * cloth.ob.modeling_cloth_inflate# * cloth.tri_mix
    
    cloth.inflate.shape = (shape[0] * 3, 3)
    cloth.inflate *= cloth.tri_mix


    np.add.at(cloth.vel, cloth.tridex.ravel(), cloth.inflate)
    cloth.inflate.shape = shape
    cloth.inflate *= 0


def get_quat(rad, axis):
    theta = (rad * 0.5)
    w = np.cos(theta)
    q_axis = axis * np.sin(theta)[:, nax]
    return w, q_axis


def q_rotate(co, w, axis):
    """Takes an N x 3 numpy array and returns that array rotated around
    the axis by the angle in radians w. (standard quaternion)"""    
    move1 = np.cross(axis, co)
    move2 = np.cross(axis, move1)
    move1 *= w[:, nax]
    return co + (move1 + move2) * 2


def bend_springs(cloth, co, measure=None):
    bend_eidx, tips = cloth.bend_eidx, cloth.bend_tips

    tips_co = co[tips]
    bls, brs = bend_eidx[:,0], bend_eidx[:, 1]
    b_oris = co[bls]
    
    be_vecs = co[brs] - b_oris
    te_vecs = tips_co - b_oris[:, nax]

    bcp_dots = np.einsum('ij,ikj->ik', be_vecs, te_vecs)
    be_dots = np.einsum('ij,ij->i', be_vecs, be_vecs)
    b_div = np.nan_to_num(bcp_dots / be_dots[:, nax])
    
    tcp = be_vecs[:, nax] * b_div[:, :, nax]
    
    # tip vecs from cp
    tcp_vecs = te_vecs - tcp
    tcp_dots = np.einsum('ijk,ijk->ij',tcp_vecs, tcp_vecs) 
    
    u_tcp_vecs = tcp_vecs / np.sqrt(tcp_dots)[:, :, nax]
    
    u_tcp_ls = u_tcp_vecs[:, 0]
    u_tcp_rs = u_tcp_vecs[:, 1]
    
    # dot of unit tri tips around axis
    angle_dot = np.einsum('ij,ij->i', u_tcp_ls, u_tcp_rs)
    
    #paralell = angle_dot < -.9999999
    
    angle = np.arccos(np.clip(angle_dot, -1, 1)) # values outside and arccos gives nan
    #angle = np.arccos(angle_dot) # values outside and arccos gives nan


    # get the angle sign
    tcp_cross = np.cross(u_tcp_vecs[:, 0], u_tcp_vecs[:, 1])
    sign = np.sign(np.einsum('ij,ij->i', be_vecs, tcp_cross))
    
    if measure is None:
        s = np.arccos(angle_dot)
        s *= sign
        s[angle_dot < -.9999999] = np.pi

        return s

    angle *= sign
    # rotate edges with quaternypoos
    u_be_vecs = be_vecs / np.sqrt(be_dots)[:, nax]
    b_dif = angle - measure
    
    l_ws, l_axes = get_quat(b_dif, u_be_vecs)
    r_ws, r_axes = l_ws, -l_axes
    
    # move tcp vecs so their origin is in the middle:
    #u_tcp_vecs *= 0.5    
    
    # should I rotate the unit vecs or the source?
    #   rotating the unit vecs here.
    
    stiff = cloth.ob.modeling_cloth_bend_stiff * 0.0057
    rot_ls = q_rotate(u_tcp_ls, l_ws, l_axes) 
    l_force = (rot_ls - u_tcp_ls) * stiff
    
    rot_rs = q_rotate(u_tcp_rs, r_ws, r_axes)    
    r_force = (rot_rs - u_tcp_rs) * stiff
    
    
    np.add.at(cloth.co, tips[:, 0], l_force)
    np.add.at(cloth.co, tips[:, 1], r_force)
    
    np.subtract.at(cloth.co, bend_eidx.ravel(), np.tile(r_force * .5, 2).reshape(r_force.shape[0] * 2, 3))
    np.subtract.at(cloth.co, bend_eidx.ravel(), np.tile(l_force * .5, 2).reshape(l_force.shape[0] * 2, 3))
    
    return
    cloth.co[tips[:, 0]] += l_force
    cloth.co[tips[:, 1]] += r_force
    
    #cloth.co[bend_eidx] -= l_force
    cloth.co[bend_eidx] -= r_force[:, nax]
    cloth.co[bend_eidx] -= l_force[:, nax]
    #cloth.co[brs] -= r_force
    #print("bend here")

    # will need to read bend springs continuously when using
    # a dynamic source shape. Guess I should do that now...
    
    

    # need the angle at each edge
    # need to get the tips of each tri around each edge
    # should be a pair everywhere there is a link face in
    #   the tri bmesh
    """
    With no sign I just get the dot in radians.
    Rotation should move towards the shortest distance
    to the same dot in radians. 
    
    Without getting the sign at all, it will always rotate
    in the same direction to go back to the target.
    By multiplying the dif by the sign, I can make it spin
    the other way to go back to the target dot in rads
    
    """
    

# sewing functions ---------------->>>
def create_sew_edges():

    bpy.ops.mesh.bridge_edge_loops()
    bpy.ops.mesh.delete(type='ONLY_FACE')
    return
    #highlight a sew edge
    #compare vertex counts
    #subdivide to match counts
    #distribute and smooth back into mesh
    #create sew lines
     

    



# sewing functions ---------------->>>

    
class Cloth(object):
    pass


def create_instance(new=True):
    """Creates instance of cloth object with attributes needed for engine"""
    
    for i in bpy.data.meshes:
        if i.users == 0:
            bpy.data.meshes.remove(i)
    
    if new:
        cloth = Cloth()
        cloth.ob = bpy.context.object # based on what the user has as the active object
        cloth.pin_list = [] # these will not be moved by the engine
        cloth.hook_list = [] # these will be moved by hooks and updated to the engine
        cloth.virtual_springs = np.empty((0,2), dtype=np.int32) # so we can attach points to each other without regard to topology
        cloth.sew_springs = [] # edges with no faces attached can be set to shrink
    
    else: # if we set a modeling cloth object and have something else selected, the most recent object will still have it's settings expose in the ui
        ob = get_last_object()[1]
        cloth = data[ob.name]
        cloth.ob = ob 
    
    # get proxy object
    #proxy = cloth.ob.to_mesh(bpy.context.scene, False, 'PREVIEW')
    # ----------------
    
    bpy.context.scene.objects.active = cloth.ob
    cloth.idxer = np.arange(len(cloth.ob.data.vertices), dtype=np.int32)
    # data only accesible through object mode
    mode = cloth.ob.mode
    if mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    
    # data is read from a source shape and written to the display shape so we can change the target springs by changing the source shape
    cloth.name = cloth.ob.name
    if cloth.ob.data.shape_keys == None:
        cloth.ob.shape_key_add('Basis')    
    if 'modeling cloth source key' not in cloth.ob.data.shape_keys.key_blocks:
        cloth.ob.shape_key_add('modeling cloth source key')        
    if 'modeling cloth key' not in cloth.ob.data.shape_keys.key_blocks:
        cloth.ob.shape_key_add('modeling cloth key')        
        cloth.ob.data.shape_keys.key_blocks['modeling cloth key'].value=1
    cloth.count = len(cloth.ob.data.vertices)
    
    # we can set a large group's pin state using the vertex group. No hooks are used here
    if 'modeling_cloth_pin' not in cloth.ob.vertex_groups:
        cloth.pin_group = create_vertex_groups(groups=['modeling_cloth_pin'], weights=[0.0], ob=None)
    for i in range(cloth.count):
        try:
            cloth.ob.vertex_groups['modeling_cloth_pin'].weight(i)
        except RuntimeError:
            # assign a weight of zero
            cloth.ob.vertex_groups['modeling_cloth_pin'].add(range(0,len(cloth.ob.data.vertices)), 0.0, 'REPLACE')
    cloth.pin_bool = ~np.array([cloth.ob.vertex_groups['modeling_cloth_pin'].weight(i) for i in range(cloth.count)], dtype=np.bool)

    # unique edges------------>>>
    uni_edges = get_minimal_edges(cloth.ob)
    if len(uni_edges[1]) > 0:   
        cloth.eidx = np.append(uni_edges[0], uni_edges[1], axis=0)
    else:
        cloth.eidx = uni_edges[0]
    #cloth.eidx = uni_edges[0][0]

    if cloth.virtual_springs.shape[0] > 0:
        cloth.eidx = np.append(cloth.eidx, cloth.virtual_springs, axis=0)
    cloth.eidx_tiler = cloth.eidx.T.ravel()    

    mixology = get_spring_mix(cloth.ob, cloth.eidx)
    

    eidx1 = np.copy(cloth.eidx)
    pindexer = np.arange(cloth.count, dtype=np.int32)[cloth.pin_bool]
    unpinned = np.in1d(cloth.eidx_tiler, pindexer)
    cloth.eidx_tiler = cloth.eidx_tiler[unpinned]    
    cloth.unpinned = unpinned

    cloth.sew_edges = uni_edges[2]
    cloth.multi_sew = uni_edges[3]
    
    # unique edges------------>>>
    
    cloth.pcount = pindexer.shape[0]
    cloth.pindexer = pindexer
    
    cloth.sco = np.zeros(cloth.count * 3, dtype=np.float32)
    cloth.ob.data.shape_keys.key_blocks['modeling cloth source key'].data.foreach_get('co', cloth.sco)
    cloth.sco.shape = (cloth.count, 3)
    cloth.co = np.zeros(cloth.count * 3, dtype=np.float32)
    cloth.ob.data.shape_keys.key_blocks['modeling cloth key'].data.foreach_get('co', cloth.co)
    cloth.co.shape = (cloth.count, 3)    
    co = cloth.co
    cloth.vel = np.zeros(cloth.count * 3, dtype=np.float32)
    cloth.vel_start = np.zeros(cloth.count * 3, dtype=np.float32)
    cloth.vel_start.shape = (cloth.count, 3)
    cloth.vel.shape = (cloth.count, 3)
    cloth.self_col_vel = np.copy(co)
    
    cloth.v_normals = np.zeros(co.shape, dtype=np.float32)
    #get_v_normals(cloth.ob, cloth.v_normals, proxy)
    
    #noise---
    noise_zeros = np.zeros(cloth.count, dtype=np.float32)
    random = np.random.random(cloth.count).astype(np.float32)
    noise_zeros[:] = random
    cloth.noise = ((noise_zeros + -0.5) * cloth.ob.modeling_cloth_noise * 0.1)[:, nax]
    
    cloth.waiting = False
    cloth.clicked = False # for the grab tool
    
    # this helps with extra springs behaving as if they had more mass---->>>
    cloth.mix = mixology[unpinned][:, nax]
    # -------------->>>

    # new self collisions:
    cloth.tridex = geometry.triangulate(cloth.ob.data, cloth)
    cloth.tridexer = np.arange(cloth.tridex.shape[0], dtype=np.int32)
    cloth.tri_co = cloth.co[cloth.tridex]
    geometry.tri_normals_in_place(cloth, cloth.tri_co) # non-unit normals
    # -------------->>>
    
    tri_uni, tri_inv, tri_counts = np.unique(cloth.tridex, return_inverse=True, return_counts=True)
    cloth.tri_mix = (1 / tri_counts[tri_inv])[:, nax]
    
    cloth.wind = np.zeros(cloth.tri_co.shape, dtype=np.float32)
    cloth.inflate = np.zeros(cloth.tri_co.shape, dtype=np.float32)

    bpy.ops.object.mode_set(mode=mode)
    
    
    # for use with a static source shape:
    cloth.source_angles = bend_springs(cloth, cloth.sco, None)
    svecs = cloth.sco[cloth.eidx[:, 1]] - cloth.sco[cloth.eidx[:, 0]]
    cloth.sdots = np.einsum('ij,ij->i', svecs, svecs)
    
    # for doing static cling
    #   cloth.col_idx = np.array([], dtype=np.int32)
    #   cloth.re_col = np.empty((0,3), dtype=np.float32)
    
    return cloth


def run_handler(cloth):
    T = time.time()
    if cloth.ob.modeling_cloth_handler_frame | cloth.ob.modeling_cloth_handler_scene:
        if cloth.ob.mode == 'EDIT':
            cloth.waiting = True
        if cloth.waiting:    
            if cloth.ob.mode == 'OBJECT':
                update_pin_group()

        if not cloth.waiting:
            eidx = cloth.eidx # world's most important variable
            cloth.ob.data.shape_keys.key_blocks['modeling cloth source key'].data.foreach_get('co', cloth.sco.ravel())

            sco = cloth.sco
            co = cloth.co
            
            co[cloth.pindexer] += cloth.noise[cloth.pindexer]
            #co += cloth.noise
            cloth.noise *= cloth.ob.modeling_cloth_noise_decay

            # mix in vel before collisions and sewing
            co[cloth.pindexer] += cloth.vel[cloth.pindexer]
            cloth.vel_start[:] = co

            # measure source -------------------------->>>
            dynamic = True # can store for speedup if source shape is static
            # bend spring calculations:
            if cloth.ob.modeling_cloth_bend_stiff != 0:
            
                # measure bend source if using dynamic source:
                source_angles = cloth.source_angles
                if dynamic:    
                    source_angles = bend_springs(cloth, sco, None)
            
            # linear spring measure
            sdots = cloth.sdots
            if dynamic:    
                cloth.ob.data.shape_keys.key_blocks['modeling cloth source key'].data.foreach_get('co', sco.ravel())
                svecs = sco[eidx[:, 1]] - sco[eidx[:, 0]]
                sdots = np.einsum('ij,ij->i', svecs, svecs)            
            # ----------------------------------------->>>
            
            force = cloth.ob.modeling_cloth_spring_force
            mix = cloth.mix * force
            
            ers = eidx[:, 1]
            els = eidx[:, 0]
            for x in range(cloth.ob.modeling_cloth_iterations):    

                # bend spring calculations:
                if cloth.ob.modeling_cloth_bend_stiff != 0:
                    bend_springs(cloth, co, source_angles)

                # add pull
                vecs = co[ers] - co[els]
                dots = np.einsum('ij,ij->i', vecs, vecs)
                div = np.nan_to_num(sdots / dots)
                swap = vecs * np.sqrt(div)[:, nax]
                move = vecs - swap

                # pull separate test--->>>
                push = cloth.ob.modeling_cloth_push_springs
                if push == 0:
                    move[div > 1] = 0
                else:
                    move[div > 1] *= push
                # pull only test--->>>
                
                tiled_move = np.append(move, -move, axis=0)[cloth.unpinned] * mix # * mix for stability: force multiplied by 1/number of springs
                
                np.add.at(cloth.co, cloth.eidx_tiler, tiled_move)
                
                # for doing static cling
                #   cloth.co[cloth.col_idx] = cloth.re_col

                cloth.co[~cloth.pin_bool] = cloth.vel_start[~cloth.pin_bool]

                if len(cloth.pin_list) > 0:
                    hook_co = np.array([cloth.ob.matrix_world.inverted() * i.matrix_world.to_translation() for i in cloth.hook_list])
                    cloth.co[cloth.pin_list] = hook_co
                
                # grab inside spring iterations
                if cloth.clicked: # for the grab tool
                    cloth.co[extra_data['vidx']] = np.array(extra_data['stored_vidx']) + np.array(+ extra_data['move'])   


            # refresh normals for inflate wind and self collisions
            cloth.tri_co = cloth.co[cloth.tridex]
            geometry.tri_normals_in_place(cloth, cloth.tri_co) # unit normals


            
            # add effects of velocity and Gravity to the vel array for later
            spring_dif = cloth.co - cloth.vel_start
            
            #if cloth.ob.modeling_cloth_bend_stiff > 0:
                #for
            
            # non-unit normals might be better for inflate and wind because
            # their strength is affected by the area as it is should be
            
            #place after wind and inflate unless those are added to vel after collisions
              
    
            # get proxy object
            #proxy = cloth.ob.to_mesh(bpy.context.scene, False, 'PREVIEW')
            #proxy = cloth.ob.data
            #get_v_normals(cloth.ob, cloth.v_normals, proxy)





            # gravity
            grav = cloth.ob.modeling_cloth_gravity * 0.01# / cloth.ob.modeling_cloth_iterations)
            if grav != 0:
                cloth.vel += geometry.revert_rotation(cloth.ob, np.array([0, 0, grav])) / np.array(cloth.ob.scale)
            
            # can cheat here:
            #spring_mean = np.mean(spring_dif, axis=0)
            #cloth.vel += spring_mean * 20

            # inextensible calc:
            cloth.vel += spring_dif * 2



            # The amount of drag increases with speed. 
            # have to convert to to a range between 0 and 1
            #squared_move_dist = np.sqrt(np.einsum("ij, ij->i", cloth.vel, cloth.vel))
            squared_move_dist = np.einsum("ij, ij->i", cloth.vel, cloth.vel)
            squared_move_dist += 1
            cloth.vel *= (1 / (squared_move_dist / cloth.ob.modeling_cloth_velocity))[:, nax]
            #cloth.vel *= cloth.ob.modeling_cloth_velocity

            # wind:
            x = cloth.ob.modeling_cloth_wind_x
            y = cloth.ob.modeling_cloth_wind_y
            z = cloth.ob.modeling_cloth_wind_z
            wind_vec = np.array([x,y,z])
            check_wind = wind_vec != 0
            if np.any(check_wind):
                generate_wind(wind_vec, cloth)            

            # inflate
            inflate = cloth.ob.modeling_cloth_inflate
            if inflate != 0:
                generate_inflate(cloth)
                #cloth.v_normals *= inflate
                #cloth.vel += cloth.v_normals

            

            if cloth.ob.modeling_cloth_sew != 0:
                if len(cloth.sew_edges) > 0:
                    sew_edges = cloth.sew_edges
                    rs = co[sew_edges[:,1]]
                    ls = co[sew_edges[:,0]]
                    sew_vecs = (rs - ls) * 0.5 * cloth.ob.modeling_cloth_sew
                    co[sew_edges[:,1]] -= sew_vecs
                    co[sew_edges[:,0]] += sew_vecs
                    
                    # for sew verts with more than one sew edge
                    if cloth.multi_sew is not None:
                        for sg in cloth.multi_sew:
                            cosg = co[sg]
                            meanie = np.mean(cosg, axis=0)
                            sg_vecs = meanie - cosg
                            co[sg] += sg_vecs * cloth.ob.modeling_cloth_sew
                
            # !!!!!  need to try adding in the velocity before doing the collision stuff
            # !!!!! so vel would be added here after wind and inflate but before collision
            
            
            # floor ---
            if cloth.ob.modeling_cloth_floor:    
                floored = cloth.co[:,2] < 0        
                cloth.vel[:,2][floored] *= -1
                cloth.vel[floored] *= .1
                cloth.co[:, 2][floored] = 0
            # floor ---            
            

            # objects ---
            #T = time.time()
            if cloth.ob.modeling_cloth_object_detect:
                if cloth.ob.modeling_cloth_self_collision:
                    self_collide(cloth)
                # print(extra_data)
                # extra_data['colliders'] = {}
                if extra_data['colliders'] is not None:
                    for i, val in extra_data['colliders'].items():
                        #if val.ob.modeling_cloth_self_collision == cloth.ob:    
                            #self_collide(cloth, val)
                            #cloth.co[cloth.pindexer] = cloth.vel_start[cloth.pindexer]
                        if val.ob != cloth.ob:
                            object_collide(cloth, val)
            #print(time.time()-T, "the whole enchalada")
            # objects ---

            cloth.co[~cloth.pin_bool] = cloth.vel_start[~cloth.pin_bool]
            
            if len(cloth.pin_list) > 0:
                cloth.co[cloth.pin_list] = hook_co
                cloth.vel[cloth.pin_list] = 0

            if cloth.clicked: # for the grab tool
                cloth.co[extra_data['vidx']] = np.array(extra_data['stored_vidx']) + np.array(+ extra_data['move'])


            cloth.ob.data.shape_keys.key_blocks['modeling cloth key'].data.foreach_set('co', cloth.co.ravel())

            cloth.ob.data.shape_keys.key_blocks['modeling cloth key'].mute = True
            cloth.ob.data.shape_keys.key_blocks['modeling cloth key'].mute = False

            # remove proxy
            #proxy.user_clear()
            #bpy.data.meshes.remove(proxy)
            #del(proxy)
    #print(time.time()-T, "the entire handler time")

# +++++++++++++ object collisions ++++++++++++++
def bounds_check(co1, co2, fudge):
    """Returns True if object bounding boxes intersect.
    Have to add the fudge factor for collision margins"""
    check = False
    co1_max = None # will never return None if check is true
    co1_min = np.min(co1, axis=0)
    co2_max = np.max(co2, axis=0)

    if np.all(co2_max + fudge > co1_min):
        co1_max = np.max(co1, axis=0)
        co2_min = np.min(co2, axis=0)        
        
        if np.all(co1_max > co2_min - fudge):
            check = True

    return check, co1_min, co1_max # might as well reuse the checks


def triangle_bounds_check(tri_co, co_min, co_max, idxer, fudge):
    """Returns a bool aray indexing the triangles that
    intersect the bounds of the object"""

    # min check cull step 1
    tri_min = np.min(tri_co, axis=1) - fudge
    check_min = co_max > tri_min
    in_min = np.all(check_min, axis=1)
    
    # max check cull step 2
    idx = idxer[in_min]
    tri_max = np.max(tri_co[in_min], axis=1) + fudge
    check_max = tri_max > co_min
    in_max = np.all(check_max, axis=1)
    in_min[idx[~in_max]] = False
    
    return in_min, tri_min[in_min], tri_max[in_max] # can reuse the min and max


def tri_back_check(co, tri_min, tri_max, idxer, fudge):
    """Returns a bool aray indexing the vertices that
    intersect the bounds of the culled triangles"""

    # min check cull step 1
    tb_min = np.min(tri_min, axis=0) - fudge
    check_min = co > tb_min
    in_min = np.all(check_min, axis=1)
    idx = idxer[in_min]
    
    # max check cull step 2
    tb_max = np.max(tri_max, axis=0) + fudge
    check_max = co[in_min] < tb_max
    in_max = np.all(check_max, axis=1)        
    in_min[idx[~in_max]] = False    
    
    return in_min 


# -------------------------------------------------------
# -------------------------------------------------------
def zxy_grid(co_y, tymin, tymax, subs, c, t, c_peat, t_peat):
    # create linespace grid between bottom and top of tri z
    #subs = 7
    t_min = np.min(tymin)
    t_max = np.max(tymax)
    divs = np.linspace(t_min, t_max, num=subs, dtype=np.float32)            
    
    # figure out which triangles and which co are in each section
    co_bools = (co_y > divs[:-1][:, nax]) & (co_y < divs[1:][:, nax])
    tri_bools = (tymin < divs[1:][:, nax]) & (tymax > divs[:-1][:, nax])

    for i, j in zip(co_bools, tri_bools):
        if (np.sum(i) > 0) & (np.sum(j) > 0):
            c3 = c[i]
            t3 = t[j]
        
            c_peat.append(np.repeat(c3, t3.shape[0]))
            t_peat.append(np.tile(t3, c3.shape[0]))


def zx_grid(co_x, txmin, txmax, subs, c, t, c_peat, t_peat, co_y, tymin, tymax):
    # create linespace grid between bottom and top of tri z
    #subs = 7
    t_min = np.min(txmin)
    t_max = np.max(txmax)
    divs = np.linspace(t_min, t_max, num=subs, dtype=np.float32)            
    
    # figure out which triangles and which co are in each section
    co_bools = (co_x > divs[:-1][:, nax]) & (co_x < divs[1:][:, nax])
    tri_bools = (txmin < divs[1:][:, nax]) & (txmax > divs[:-1][:, nax])

    for i, j in zip(co_bools, tri_bools):
        if (np.sum(i) > 0) & (np.sum(j) > 0):
            c2 = c[i]
            t2 = t[j]
            
            zxy_grid(co_y[i], tymin[j], tymax[j], subs, c2, t2, c_peat, t_peat)


def z_grid(co_z, tzmin, tzmax, subs, co_x, txmin, txmax, co_y, tymin, tymax):
    # create linespace grid between bottom and top of tri z
    #subs = 7
    t_min = np.min(tzmin)
    t_max = np.max(tzmax)
    divs = np.linspace(t_min, t_max, num=subs, dtype=np.float32)
            
    # figure out which triangles and which co are in each section
    co_bools = (co_z > divs[:-1][:, nax]) & (co_z < divs[1:][:, nax])
    tri_bools = (tzmin < divs[1:][:, nax]) & (tzmax > divs[:-1][:, nax])

    c_ranger = np.arange(co_bools.shape[1])
    t_ranger = np.arange(tri_bools.shape[1])

    c_peat = []
    t_peat = []

    for i, j in zip(co_bools, tri_bools):
        if (np.sum(i) > 0) & (np.sum(j) > 0):
            c = c_ranger[i]
            t = t_ranger[j]

            zx_grid(co_x[i], txmin[j], txmax[j], subs, c, t, c_peat, t_peat, co_y[i], tymin[j], tymax[j])
    
    if (len(c_peat) == 0) | (len(t_peat) == 0):
        return None, None
    
    return np.hstack(c_peat), np.hstack(t_peat)
# -------------------------------------------------------
# -------------------------------------------------------    

    
"""Combined with numexpr the first check min and max is faster
    Combined without numexpr is slower. It's better to separate min and max"""
def v_per_tri(co, tri_min, tri_max, idxer, tridexer, c_peat=None, t_peat=None):
    """Checks each point against the bounding box of each triangle"""

    co_x, co_y, co_z = co[:, 0], co[:, 1], co[:, 2]
    
    subs = 7
    #subs = bpy.data.objects['Plane.002'].modeling_cloth_grid_size
    
    c_peat, t_peat = z_grid(co_z, tri_min[:, 2], tri_max[:, 2], subs, co_x, tri_min[:, 0], tri_max[:, 0], co_y, tri_min[:, 1], tri_max[:, 1])
    if c_peat is None:
        return
    # X
    # Step 1 check x_min (because we're N squared here we break it into steps)
    check_x_min = co_x[c_peat] > tri_min[:, 0][t_peat]
    c_peat = c_peat[check_x_min]
    if c_peat.shape[0] == 0:
        return
    t_peat = t_peat[check_x_min]

    # Step 2 check x max
    check_x_max = co_x[c_peat] < tri_max[:, 0][t_peat]
    c_peat = c_peat[check_x_max]
    if c_peat.shape[0] == 0:
        return
    t_peat = t_peat[check_x_max]
    
    # Y
    # Step 3 check y min    
    check_y_min = co_y[c_peat] > tri_min[:, 1][t_peat]
    c_peat = c_peat[check_y_min]
    if c_peat.shape[0] == 0:
        return
    t_peat = t_peat[check_y_min]

    # Step 4 check y max
    check_y_max = co_y[c_peat] < tri_max[:, 1][t_peat]
    c_peat = c_peat[check_y_max]
    if c_peat.shape[0] == 0:
        return
    t_peat = t_peat[check_y_max]

    # Z
    # Step 5 check z min    
    check_z_min = co_z[c_peat] > tri_min[:, 2][t_peat]
    c_peat = c_peat[check_z_min]
    if c_peat.shape[0] == 0:
        return
    t_peat = t_peat[check_z_min]

    # Step 6 check y max
    check_z_max = co_z[c_peat] < tri_max[:, 2][t_peat]
    c_peat = c_peat[check_z_max]
    if c_peat.shape[0] == 0:
        return
    t_peat = t_peat[check_z_max]    

    return idxer[c_peat], t_peat
    #return c_peat, t_peat


def inside_triangles(tri_vecs, v2, co, tri_co_2, cidx, tidx, nor, ori, in_margin, offset=None):
    idxer = np.arange(in_margin.shape[0], dtype=np.int32)[in_margin]
    
    r_co = co[cidx[in_margin]]    
    r_tri = tri_co_2[tidx[in_margin]]
    
    v0 = tri_vecs[:,0]
    v1 = tri_vecs[:,1]
    
    d00_d11 = np.einsum('ijk,ijk->ij', tri_vecs, tri_vecs)
    d00 = d00_d11[:,0]
    d11 = d00_d11[:,1]
    d01 = np.einsum('ij,ij->i', v0, v1)
    d02 = np.einsum('ij,ij->i', v0, v2)
    d12 = np.einsum('ij,ij->i', v1, v2)

    div = 1 / (d00 * d11 - d01 * d01)
    u = (d11 * d02 - d01 * d12) * div
    v = (d00 * d12 - d01 * d02) * div
    
    # !!! Watch out for this number. It could affect speed !!! 
    if offset:
        check = (u > -offset) & (v > -offset) & (u + v < offset + 1)
    else:
        check = (u > 0) & (v > 0) & (u + v < 1)
    in_margin[idxer] = check


def object_collide(cloth, object):
    
    # for doing static cling
    #   cloth.col_idx = np.array([], dtype=np.int32)
    #   cloth.re_col = np.empty((0,3), dtype=np.float32)
    
    proxy = object.ob.to_mesh(bpy.context.scene, True, 'PREVIEW')
    geometry.proxy_in_place(object, proxy)
    geometry.apply_in_place(cloth.ob, cloth.co, cloth)

    inner_margin = object.ob.modeling_cloth_inner_margin
    outer_margin = object.ob.modeling_cloth_outer_margin
    fudge = max(inner_margin, outer_margin)

    # check object bounds: (need inner and out margins to adjust box size)
    box_check, co1_min, co1_max = bounds_check(cloth.co, object.co, fudge)
    # check for triangles inside the cloth bounds
    #anim = object.ob.modeling_cloth_collision_animated
    
    
    if box_check:

        geometry.proxy_v_normals_in_place(object, True, proxy)
        tri_co = object.co[object.tridex]
        tri_vo = object.vel[object.tridex]

        tris_in, tri_min, tri_max = triangle_bounds_check(tri_co, co1_min, co1_max, object.tridexer, fudge)#, object.ob.dimensions)

        # check for verts in the bounds around the culled triangles
        if np.any(tris_in):    
            tri_co_2 = tri_co[tris_in]
            back_check = tri_back_check(cloth.co, tri_min, tri_max, cloth.idxer, fudge)

            # begin every vertex co against every tri
            if np.any(back_check):
                v_tris = v_per_tri(cloth.co[back_check], tri_min, tri_max, cloth.idxer[back_check], object.tridexer[tris_in])

                if v_tris is not None:
                    # update the normals. cross_vecs used by barycentric tri check
                    # move the surface along the vertex normals by the outer margin distance
                    marginalized = (object.co + object.v_normals * outer_margin)[object.tridex]
                    geometry.tri_normals_in_place(object, marginalized)
                    
                    # add normals to make extruded tris
                    u_norms = object.normals[tris_in]
                    #u_norms = norms_2 / np.sqrt(np.einsum('ij, ij->i', norms_2, norms_2))[:, nax] 
                                        
                    cidx, tidx = v_tris
                    ori = object.origins[tris_in][tidx]
                    nor = u_norms[tidx]
                    vec2 = cloth.co[cidx] - ori
                    
                    d = np.einsum('ij, ij->i', nor, vec2) # nor is unit norms
                    in_margin = (d > -(inner_margin + outer_margin)) & (d < 0)#outer_margin) (we have offset outer margin)
                    
                    # <<<--- Inside triangle check --->>>
                    # will overwrite in_margin:
                    cross_2 = object.cross_vecs[tris_in][tidx][in_margin]
                    inside_triangles(cross_2, vec2[in_margin], cloth.co, marginalized[tris_in], cidx, tidx, nor, ori, in_margin)
                    
                    if np.any(in_margin):
                        # collision response --------------------------->>>
                        #if anim:    
                        t_in = tidx[in_margin]
                        
                        tri_vo = tri_vo[tris_in]
                        tri_vel1 = np.mean(tri_co_2[t_in], axis=1)
                        tri_vel2 = np.mean(tri_vo[t_in], axis=1)
                        tvel = tri_vel1 - tri_vel2

                        col_idx = cidx[in_margin] 
                        cloth.co[col_idx] -= nor[in_margin] * (d[in_margin])[:, nax]
                        cloth.vel[col_idx] = tvel
                        
                        # for doing static cling
                        #   cloth.re_col = np.copy(cloth.co[col_idx])                        
                        #   cloth.col_idx = col_idx
                        
    object.vel[:] = object.co    
    geometry.revert_in_place(cloth.ob, cloth.co)
    
    #temp_ob = bpy.data.objects.new('__TEMP', proxy)
    #for key in proxy.shape_keys.key_blocks:
    #    temp_ob.shape_key_remove(key)
            
    #bpy.data.objects.remove(temp_ob)
    bpy.data.meshes.remove(proxy)


# self collider =============================================
def self_collide(cloth):

    margin = cloth.ob.modeling_cloth_self_collision_margin

    tri_co = cloth.tri_co

    tri_min = np.min(tri_co, axis=1) - margin
    tri_max = np.max(tri_co, axis=1) + margin   

    # begin every vertex co against every tri
    v_tris = v_per_tri(cloth.co, tri_min, tri_max, cloth.idxer, cloth.tridexer)
    if v_tris is not None:
        cidx, tidx = v_tris

        u_norms = cloth.normals

        # don't check faces the verts are part of        
        check_neighbors = cidx[:, nax] == cloth.tridex[tidx]
        cull = np.any(check_neighbors, axis=1)
        cidx, tidx = cidx[~cull], tidx[~cull]
        
        ori = cloth.origins[tidx]
        nor = u_norms[tidx]
        vec2 = cloth.co[cidx] - ori
        
        d = np.einsum('ij, ij->i', nor, vec2) # nor is unit norms
        in_margin = (d > -margin) & (d < margin)
        # <<<--- Inside triangle check --->>>
        # will overwrite in_margin:
        cross_2 = cloth.cross_vecs[tidx][in_margin]
        inside_triangles(cross_2, vec2[in_margin], cloth.co, tri_co, cidx, tidx, nor, ori, in_margin, offset=0.0)
        
        if np.any(in_margin):
            # collision response --------------------------->>>
            t_in = tidx[in_margin]
            #tri_vel1 = np.mean(tri_co[t_in], axis=1)
            #tvel = np.mean(tri_vo[t_in], axis=1)
            #tvel = tri_vel1 - tri_vel2
            t_vel = np.mean(cloth.vel[cloth.tridex][t_in], axis=1)
            
            col_idx = cidx[in_margin] 
            d_in = d[in_margin]
    
            sign_margin = margin * np.sign(d_in) # which side of the face
            c_move = ((nor[in_margin] * d_in[:, nax]) - (nor[in_margin] * sign_margin[:, nax]))#) * -np.sign(d[in_margin])[:, nax]
            #c_move *= 1 / cloth.ob.modeling_cloth_grid_size
            #cloth.co[col_idx] -= ((nor[in_margin] * d_in[:, nax]) - (nor[in_margin] * sign_margin[:, nax]))#) * -np.sign(d[in_margin])[:, nax]
            cloth.co[col_idx] -= c_move #* .7
            #cloth.vel[col_idx] = 0
            cloth.vel[col_idx] = t_vel

    #object.vel[:] = object.co    
# self collider =============================================


# update functions --------------------->>>    
def tile_and_remove_neighbors(vidx, tidx, c_peat, t_peat):

    tshape = tidx.shape[0]
    vshape = vidx.shape[0]

    # eliminate tris that contain the point: 
    # check the speed difference of doing a reshape with ravel at the end
    co_tidex = c_peat.reshape(vshape, tshape)
    tri_tidex = tidx[t_peat.reshape(vshape, tshape)]
    check = tri_tidex == vidx[co_tidex][:,:,nax]
    cull = ~np.any(check, axis=2)

    # duplicate of each tri for each vert and each vert for each tri
    c_peat = c_peat[cull.ravel()]
    t_peat = t_peat[cull.ravel()]
    
    return c_peat, t_peat



    
# cloth object detect updater:
def cloth_object_update(self, context):
    """Updates the cloth object when detecting."""
    print("ran the detect updater. It did nothing.")


def manage_animation_handler(self, context):
    if self.modeling_cloth_handler_frame:
        self["modeling_cloth_handler_scene"] = False
        update_pin_group()
    
    if handler_frame in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(handler_frame)
    
    if len(data) > 0:
        bpy.app.handlers.frame_change_post.append(handler_frame)
    
    #count = len([i for i in bpy.data.objects if i.modeling_cloth_handler_frame])

        
def manage_continuous_handler(self, context):    
    if self.modeling_cloth_handler_scene:
        self["modeling_cloth_handler_frame"] = False
        update_pin_group()
    
    if handler_scene in bpy.app.handlers.scene_update_post:
        bpy.app.handlers.scene_update_post.remove(handler_scene)
    
    if len(data) > 0:
        bpy.app.handlers.scene_update_post.append(handler_scene)
    

# =================  Handler  ======================
def handler_frame(scene):

    items = data.items()
    if len(items) == 0:
        for i in bpy.data.objects:
            i.modeling_cloth = False
        
        for i in bpy.app.handlers.frame_change_post:
            if i.__name__ == 'handler_frame':
                bpy.app.handlers.frame_change_post.remove(i)
                
        for i in bpy.app.handlers.scene_update_post:
            if i.__name__ == 'handler_scene':
                bpy.app.handlers.scene_update_post.remove(i)                
    
    for i, cloth in items:    
        if i in bpy.data.objects: # using the name. The name could change
            if cloth.ob.modeling_cloth_handler_frame:    
                run_handler(cloth)
                if cloth.ob.modeling_cloth_auto_reset:
                    if bpy.context.scene.frame_current <= 1:    
                        reset_shapes(cloth.ob)
        else:
            del(data[i])
            break


def handler_scene(scene):

    items = data.items()
    if len(items) == 0:
        for i in bpy.data.objects:
            i.modeling_cloth = False

        for i in bpy.app.handlers.frame_change_post:
            if i.__name__ == 'handler_frame':
                bpy.app.handlers.frame_change_post.remove(i)

        for i in bpy.app.handlers.scene_update_post:
            if i.__name__ == 'handler_scene':
                bpy.app.handlers.scene_update_post.remove(i)                
    
    for i, cloth in items:    
        if i in bpy.data.objects: # using the name. The name could change
            if cloth.ob.modeling_cloth_handler_scene:    
                run_handler(cloth)

        else:
            del(data[i])
            break


def pause_update(self, context):
    if not self.modeling_cloth_pause:
        update_pin_group()


def global_setup():
    global data, extra_data
    data = bpy.context.scene.modeling_cloth_data_set
    extra_data = bpy.context.scene.modeling_cloth_data_set_extra    
    extra_data['alert'] = False
    extra_data['drag_alert'] = False
    extra_data['clicked'] = False


def init_cloth(self, context):
    global data, extra_data
    data = bpy.context.scene.modeling_cloth_data_set
    extra_data = bpy.context.scene.modeling_cloth_data_set_extra
    extra_data['alert'] = False
    extra_data['drag_alert'] = False
    extra_data['last_object'] = self
    extra_data['clicked'] = False
    
    # object collisions
    colliders = [i for i in bpy.data.objects if i.modeling_cloth_object_collision]
    if len(colliders) == 0:    
        extra_data['colliders'] = None    
    
    # iterate through dict: for i, j in d.items()
    if self.modeling_cloth:
        cloth = create_instance() # generate an instance of the class
        data[cloth.name] = cloth  # store class in dictionary using the object name as a key
    
    cull = [] # can't delete dict items while iterating
    for i, value in data.items():
        if not value.ob.modeling_cloth:
            cull.append(i) # store keys to delete

    for i in cull:
        del data[i]
    
#    # could keep the handler unless there are no modeling cloth objects active
#    
#    if handler_frame in bpy.app.handlers.frame_change_post:
#        bpy.app.handlers.frame_change_post.remove(handler_frame)
#    
#    if len(data) > 0:
#        bpy.app.handlers.frame_change_post.append(handler_frame)


def main(context, event):
    # get the context arguments
    scene = context.scene
    region = context.region
    rv3d = context.region_data
    coord = event.mouse_region_x, event.mouse_region_y

    # get the ray from the viewport and mouse
    view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
    ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)

    ray_target = ray_origin + view_vector
    
    guide = guide_mesh.create_guide()

    def visible_objects_and_duplis():
        """Loop over (object, matrix) pairs (mesh only)"""

        for obj in context.visible_objects:
            if obj.type == 'MESH':
                if obj.modeling_cloth:    
                    yield (obj, obj.matrix_world.copy())

    def obj_ray_cast(obj, matrix):
        """Wrapper for ray casting that moves the ray into object space"""

        # get the ray relative to the object
        matrix_inv = matrix.inverted()
        ray_origin_obj = matrix_inv * ray_origin
        ray_target_obj = matrix_inv * ray_target
        ray_direction_obj = ray_target_obj - ray_origin_obj

        # cast the ray
        success, location, normal, face_index = obj.ray_cast(ray_origin_obj, ray_direction_obj)

        if success:
            return location, normal, face_index
        else:
            return None, None, None

    # cast rays and find the closest object
    best_length_squared = -1.0
    best_obj = None
    for iteration in visible_objects_and_duplis():
        obj = iteration[0]
        matrix = iteration[1]
        obj_ray_cast_tuple = obj_ray_cast(obj, matrix)
        hit = obj_ray_cast_tuple[0]
        normal = obj_ray_cast_tuple[1] 
        face_index = obj_ray_cast_tuple[2] 
        if hit is not None:
            hit_world = matrix * hit
            vidx = [v for v in obj.data.polygons[face_index].vertices]
            verts = np.array([matrix * obj.data.shape_keys.key_blocks['modeling cloth key'].data[v].co for v in obj.data.polygons[face_index].vertices])
            vecs = verts - np.array(hit_world)
            closest = vidx[np.argmin(np.einsum('ij,ij->i', vecs, vecs))]
            length_squared = (hit_world - ray_origin).length_squared
            if best_obj is None or length_squared < best_length_squared:
                best_length_squared = length_squared
                best_obj = obj
                guide.location = matrix * obj.data.shape_keys.key_blocks['modeling cloth key'].data[closest].co
                extra_data['latest_hit'] = matrix * obj.data.shape_keys.key_blocks['modeling cloth key'].data[closest].co
                extra_data['name'] = obj.name
                extra_data['obj'] = obj
                extra_data['closest'] = closest
                
                if extra_data['just_clicked']:
                    extra_data['just_clicked'] = False
                    best_length_squared = length_squared
                    best_obj = obj
                   

# sewing --------->>>
class ModelingClothSew(bpy.types.Operator):
    """For connected two edges with sew lines"""
    bl_idname = "object.modeling_cloth_create_sew_lines"
    bl_label = "Modeling Cloth Create Sew Lines"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        
        #ob = get_last_object() # returns tuple with list and last cloth objects or None
        #if ob is not None:
            #obj = ob[1]
        #else:
        obj = bpy.context.object
        
        #bpy.context.scene.objects.active = obj
        mode = obj.mode
        if mode != "EDIT":
            bpy.ops.object.mode_set(mode="EDIT")
        
        create_sew_edges()
        bpy.ops.object.mode_set(mode="EDIT")            

        return {'FINISHED'}
# sewing --------->>>


class ModelingClothPin(bpy.types.Operator):
    """Modal ray cast for placing pins"""
    bl_idname = "view3d.modeling_cloth_pin"
    bl_label = "Modeling Cloth Pin"
    bl_options = {'REGISTER', 'UNDO'}
    def __init__(self):
        #bpy.ops.object.select_all(action='DESELECT')    
        extra_data['just_clicked'] = False
        
    def modal(self, context, event):
        bpy.context.window.cursor_set("CROSSHAIR")
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'NUMPAD_0',
        'NUMPAD_PERIOD','NUMPAD_1', 'NUMPAD_2', 'NUMPAD_3', 'NUMPAD_4',
         'NUMPAD_5', 'NUMPAD_6', 'NUMPAD_7', 'NUMPAD_8', 'NUMPAD_9'}:
            # allow navigation
            return {'PASS_THROUGH'}
        elif event.type == 'MOUSEMOVE':
            main(context, event)
            return {'RUNNING_MODAL'}
        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if extra_data['latest_hit'] is not None:
                if extra_data['name'] is not None:
                    closest = extra_data['closest']
                    name = extra_data['name']
                    e = bpy.data.objects.new('modeling_cloth_pin', None)
                    bpy.context.scene.objects.link(e)
                    e.location = extra_data['latest_hit']
                    e.show_x_ray = True
                    e.select = True
                    e.empty_draw_size = .1
                    data[name].pin_list.append(closest)
                    data[name].hook_list.append(e)
                    extra_data['latest_hit'] = None
                    extra_data['name'] = None        
        
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            guide_mesh.delete_guide()
            cloths = [i for i in bpy.data.objects if i.modeling_cloth] # so we can select an empty and keep the settings menu up
            extra_data['alert'] = False
            if len(cloths) > 0:                                        #
                ob = extra_data['last_object']                         #
                bpy.context.scene.objects.active = ob
            bpy.context.window.cursor_set("DEFAULT")
            return {'CANCELLED'}

            
        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        cloth_objects = False
        cloths = [i for i in bpy.data.objects if i.modeling_cloth] # so we can select an empty and keep the settings menu up
        if len(cloths) > 0:
            cloth_objects = True        
            extra_data['alert'] = True
            
        if context.space_data.type == 'VIEW_3D' and cloth_objects:
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "Active space must be a View3d")
            extra_data['alert'] = False
            bpy.context.window.cursor_set("DEFAULT")
            return {'CANCELLED'}


# drag===================================
# drag===================================
#[‘DEFAULT’, ‘NONE’, ‘WAIT’, ‘CROSSHAIR’, ‘MOVE_X’, ‘MOVE_Y’, ‘KNIFE’, ‘TEXT’, ‘PAINT_BRUSH’, ‘HAND’, ‘SCROLL_X’, ‘SCROLL_Y’, ‘SCROLL_XY’, ‘EYEDROPPER’]

def main_drag(context, event):
    # get the context arguments
    scene = context.scene
    region = context.region
    rv3d = context.region_data
    coord = event.mouse_region_x, event.mouse_region_y

    # get the ray from the viewport and mouse
    view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
    ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)

    ray_target = ray_origin + view_vector

    def visible_objects_and_duplis():
        """Loop over (object, matrix) pairs (mesh only)"""

        for obj in context.visible_objects:
            if obj.type == 'MESH':
                if obj.modeling_cloth:    
                    yield (obj, obj.matrix_world.copy())

    def obj_ray_cast(obj, matrix):
        """Wrapper for ray casting that moves the ray into object space"""

        # get the ray relative to the object
        matrix_inv = matrix.inverted()
        ray_origin_obj = matrix_inv * ray_origin
        ray_target_obj = matrix_inv * ray_target
        ray_direction_obj = ray_target_obj - ray_origin_obj
        
        # cast the ray
        success, location, normal, face_index = obj.ray_cast(ray_origin_obj, ray_direction_obj)

        if success:
            return location, normal, face_index, ray_target
        else:
            return None, None, None, ray_target

    # cast rays and find the closest object
    best_length_squared = -1.0
    best_obj = None

    for visible_objects_and_duplis_tuple in visible_objects_and_duplis():
        obj = visible_objects_and_duplis_tuple[0]
        matrix = visible_objects_and_duplis_tuple[1]
        obj_ray_cast_tuple = obj_ray_cast(obj, matrix)
        hit = obj_ray_cast_tuple[0]
        normal = obj_ray_cast_tuple[1] 
        face_index = obj_ray_cast_tuple[2]
        target = obj_ray_cast_tuple[3]
        extra_data['target'] = target
        if hit is not None:
            
            hit_world = matrix * hit
            length_squared = (hit_world - ray_origin).length_squared

            if best_obj is None or length_squared < best_length_squared:
                best_length_squared = length_squared
                best_obj = obj
                vidx = [v for v in obj.data.polygons[face_index].vertices]
                vert = obj.data.shape_keys.key_blocks['modeling cloth key'].data
            if best_obj is not None:    

                if extra_data['clicked']:    
                    extra_data['matrix'] = matrix.inverted()
                    data[best_obj.name].clicked = True
                    extra_data['stored_mouse'] = np.copy(target)
                    extra_data['vidx'] = vidx
                    extra_data['stored_vidx'] = np.array([vert[v].co for v in extra_data['vidx']])
                    extra_data['clicked'] = False
                    
    if extra_data['stored_mouse'] is not None:
        move = np.array(extra_data['target']) - extra_data['stored_mouse']
        extra_data['move'] = (move @ np.array(extra_data['matrix'])[:3, :3].T)
                   
                   
# dragger===
class ModelingClothDrag(bpy.types.Operator):
    """Modal ray cast for dragging"""
    bl_idname = "view3d.modeling_cloth_drag"
    bl_label = "Modeling Cloth Drag"
    bl_options = {'REGISTER', 'UNDO'}
    def __init__(self):
        #bpy.ops.object.select_all(action='DESELECT')    
        extra_data['hit'] = None
        extra_data['clicked'] = False
        extra_data['stored_mouse'] = None
        extra_data['vidx'] = None
        extra_data['new_click'] = True
        extra_data['target'] = None
        for i in data:
            data[i].clicked = False
        
    def modal(self, context, event):
        bpy.context.window.cursor_set("HAND")
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            # allow navigation
            return {'PASS_THROUGH'}
        elif event.type == 'MOUSEMOVE':
            #pos = queryMousePosition()            
            main_drag(context, event)
            return {'RUNNING_MODAL'}
        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            # when I click, If I have a hit, store the hit on press
            extra_data['clicked'] = True
            extra_data['vidx'] = []
            
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            extra_data['clicked'] = False
            extra_data['stored_mouse'] = None
            extra_data['vidx'] = None
            extra_data['new_click'] = True
            extra_data['target'] = None
            for i in data:
                data[i].clicked = False

            
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            extra_data['drag_alert'] = False
            extra_data['clicked'] = False
            extra_data['hit'] = None
            bpy.context.window.cursor_set("DEFAULT")
            extra_data['stored_mouse'] = None
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        cloth_objects = False
        cloths = [i for i in bpy.data.objects if i.modeling_cloth] # so we can select an empty and keep the settings menu up
        if len(cloths) > 0:
            cloth_objects = True        
            extra_data['drag_alert'] = True
            
        if context.space_data.type == 'VIEW_3D' and cloth_objects:
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "Active space must be a View3d")
            extra_data['drag_alert'] = False
            extra_data['stored_mouse'] = None
            bpy.context.window.cursor_set("DEFAULT")
            return {'CANCELLED'}


# drag===================================End
# drag===================================End



class DeletePins(bpy.types.Operator):
    """Delete modeling cloth pins and clear pin list for current object"""
    bl_idname = "object.delete_modeling_cloth_pins"
    bl_label = "Delete Modeling Cloth Pins"
    bl_options = {'REGISTER', 'UNDO'}    
    def execute(self, context):

        ob = get_last_object() # returns tuple with list and last cloth objects or None
        if ob is not None:
            l_copy = data[ob[1].name].pin_list[:]
            h_copy = data[ob[1].name].hook_list[:]
            for i in range(len(data[ob[1].name].hook_list)):
                if data[ob[1].name].hook_list[i].select:
                    bpy.data.objects.remove(data[ob[1].name].hook_list[i])
                    l_copy.remove(data[ob[1].name].pin_list[i]) 
                    h_copy.remove(data[ob[1].name].hook_list[i]) 
            
            data[ob[1].name].pin_list = l_copy
            data[ob[1].name].hook_list = h_copy

        bpy.context.scene.objects.active = ob[1]
        return {'FINISHED'}


class SelectPins(bpy.types.Operator):
    """Select modeling cloth pins for current object"""
    bl_idname = "object.select_modeling_cloth_pins"
    bl_label = "Select Modeling Cloth Pins"
    bl_options = {'REGISTER', 'UNDO'}    
    def execute(self, context):
        ob = get_last_object() # returns list and last cloth objects or None
        if ob is not None:
            #bpy.ops.object.select_all(action='DESELECT')
            for i in data[ob[1].name].hook_list:
                i.select = True

        return {'FINISHED'}


class PinSelected(bpy.types.Operator):
    """Add pins to verts selected in edit mode"""
    bl_idname = "object.modeling_cloth_pin_selected"
    bl_label = "Modeling Cloth Pin Selected"
    bl_options = {'REGISTER', 'UNDO'}    
    def execute(self, context):
        ob = bpy.context.object
        bpy.ops.object.mode_set(mode='OBJECT')
        sel = [i.index for i in ob.data.vertices if i.select]
                
        name = ob.name
        matrix = ob.matrix_world.copy()
        for v in sel:    
            e = bpy.data.objects.new('modeling_cloth_pin', None)
            bpy.context.scene.objects.link(e)
            if ob.active_shape_key is None:    
                closest = matrix * ob.data.vertices[v].co# * matrix
            else:
                closest = matrix * ob.active_shape_key.data[v].co# * matrix
            e.location = closest #* matrix
            e.show_x_ray = True
            e.select = True
            e.empty_draw_size = .1
            data[name].pin_list.append(v)
            data[name].hook_list.append(e)            
            ob.select = False
        bpy.ops.object.mode_set(mode='EDIT')       
        
        return {'FINISHED'}


class UpdataPinWeights(bpy.types.Operator):
    """Update Pin Weights"""
    bl_idname = "object.modeling_cloth_update_pin_group"
    bl_label = "Modeling Cloth Update Pin Weights"
    bl_options = {'REGISTER', 'UNDO'}        
    def execute(self, context):
        update_pin_group()
        return {'FINISHED'}


class GrowSource(bpy.types.Operator):
    """Grow Source Shape"""
    bl_idname = "object.modeling_cloth_grow"
    bl_label = "Modeling Cloth Grow"
    bl_options = {'REGISTER', 'UNDO'}        
    def execute(self, context):
        scale_source(1.02)
        return {'FINISHED'}


class ShrinkSource(bpy.types.Operator):
    """Shrink Source Shape"""
    bl_idname = "object.modeling_cloth_shrink"
    bl_label = "Modeling Cloth Shrink"
    bl_options = {'REGISTER', 'UNDO'}        
    def execute(self, context):
        scale_source(0.98)
        return {'FINISHED'}


class ResetShapes(bpy.types.Operator):
    """Reset Shapes"""
    bl_idname = "object.modeling_cloth_reset"
    bl_label = "Modeling Cloth Reset"
    bl_options = {'REGISTER', 'UNDO'}        
    def execute(self, context):
        reset_shapes()
        return {'FINISHED'}


class AddVirtualSprings(bpy.types.Operator):
    """Add Virtual Springs Between All Selected Vertices"""
    bl_idname = "object.modeling_cloth_add_virtual_spring"
    bl_label = "Modeling Cloth Add Virtual Spring"
    bl_options = {'REGISTER', 'UNDO'}        
    def execute(self, context):
        add_virtual_springs()
        return {'FINISHED'}


class RemoveVirtualSprings(bpy.types.Operator):
    """Remove Virtual Springs Between All Selected Vertices"""
    bl_idname = "object.modeling_cloth_remove_virtual_spring"
    bl_label = "Modeling Cloth Remove Virtual Spring"
    bl_options = {'REGISTER', 'UNDO'}        
    def execute(self, context):
        add_virtual_springs(remove=True)
        return {'FINISHED'}


class ApplyClothToMesh(bpy.types.Operator):
    """Apply cloth effects to mesh for export."""
    bl_idname = "object.modeling_cloth_apply_cloth_to_mesh"
    bl_label = "Modeling Cloth Remove Virtual Spring"
    bl_options = {'REGISTER', 'UNDO'}        
    def execute(self, context):
        ob = get_last_object()[1]
        v_count = len(ob.data.vertices)
        co = np.zeros(v_count * 3, dtype=np.float32)
        ob.data.shape_keys.key_blocks['modeling cloth key'].data.foreach_get('co', co)
        ob.data.shape_keys.key_blocks['Basis'].data.foreach_set('co', co)
        ob.data.shape_keys.key_blocks['Basis'].mute = True
        ob.data.shape_keys.key_blocks['Basis'].mute = False
        ob.data.vertices.foreach_set('co', co)
        ob.data.update()

        return {'FINISHED'}


def create_properties():            

    bpy.types.Object.modeling_cloth = bpy.props.BoolProperty(name="Modeling Cloth", 
        description="For toggling modeling cloth", 
        default=False, update=init_cloth)

    bpy.types.Object.modeling_cloth_floor = bpy.props.BoolProperty(name="Modeling Cloth Floor", 
        description="Stop at floor", 
        default=False)

    bpy.types.Object.modeling_cloth_pause = bpy.props.BoolProperty(name="Modeling Cloth Pause", 
        description="Stop without removing data",
        default=True, update=pause_update)
    
    # handler type ----->>>        
    bpy.types.Object.modeling_cloth_handler_scene = bpy.props.BoolProperty(name="Modeling Cloth Continuous Update", 
        description="Choose continuous update", 
        default=False, update=manage_continuous_handler)        

    bpy.types.Object.modeling_cloth_handler_frame = bpy.props.BoolProperty(name="Modeling Cloth Handler Animation Update", 
        description="Choose animation update", 
        default=False, update=manage_animation_handler)
        
    bpy.types.Object.modeling_cloth_auto_reset = bpy.props.BoolProperty(name="Modeling Cloth Reset at Frame 1", 
        description="Automatically reset if the current frame number is 1 or less", 
        default=False)#, update=manage_handlers)        
    # ------------------>>>

    bpy.types.Object.modeling_cloth_noise = bpy.props.FloatProperty(name="Modeling Cloth Noise", 
        description="Set the noise strength", 
        default=0.001, precision=4, min=0, max=1, update=refresh_noise)

    bpy.types.Object.modeling_cloth_noise_decay = bpy.props.FloatProperty(name="Modeling Cloth Noise Decay", 
        description="Multiply the noise by this value each iteration", 
        default=0.99, precision=4, min=0, max=1)#, update=refresh_noise_decay)

    # spring forces ------------>>>
    bpy.types.Object.modeling_cloth_spring_force = bpy.props.FloatProperty(name="Modeling Cloth Spring Force", 
        description="Set the spring force", 
        default=1.0, precision=4, min=0, max=2.5)#, update=refresh_noise)

    bpy.types.Object.modeling_cloth_push_springs = bpy.props.FloatProperty(name="Modeling Cloth Push Spring Force", 
        description="Set the push spring force", 
        default=1.0, precision=4, min=0, max=2.5)#, update=refresh_noise)
    
    # bend springs
    bpy.types.Object.modeling_cloth_bend_stiff = bpy.props.FloatProperty(name="Modeling Cloth Bend Spring Force", 
        description="Set the bend spring force", 
        default=0.0, precision=4, min=0, max=10, soft_max=1)#, update=refresh_noise)
    # -------------------------->>>

    bpy.types.Object.modeling_cloth_gravity = bpy.props.FloatProperty(name="Modeling Cloth Gravity", 
        description="Modeling cloth gravity", 
        default=0.0, precision=4, soft_min=-10, soft_max=10, min=-1000, max=1000)

    bpy.types.Object.modeling_cloth_iterations = bpy.props.IntProperty(name="Stiffness", 
        description="How stiff the cloth is", 
        default=2, min=1, max=500)#, update=refresh_noise_decay)

    bpy.types.Object.modeling_cloth_velocity = bpy.props.FloatProperty(name="Velocity", 
        description="Cloth keeps moving", 
        default=.98, min= -200, max=200, soft_min= -1, soft_max=1)#, update=refresh_noise_decay)

    # Wind. Note, wind should be measured against normal and be at zero when normals are at zero. Squared should work
    bpy.types.Object.modeling_cloth_wind_x = bpy.props.FloatProperty(name="Wind X", 
        description="Not the window cleaner", 
        default=0, min= -10, max=10, soft_min= -1, soft_max=1)#, update=refresh_noise_decay)

    bpy.types.Object.modeling_cloth_wind_y = bpy.props.FloatProperty(name="Wind Y", 
        description="Y? Because wind is cool", 
        default=0, min= -10, max=10, soft_min= -1, soft_max=1)#, update=refresh_noise_decay)

    bpy.types.Object.modeling_cloth_wind_z = bpy.props.FloatProperty(name="Wind Z", 
        description="It's windzee outzide", 
        default=0, min= -10, max=10, soft_min= -1, soft_max=1)#, update=refresh_noise_decay)

    bpy.types.Object.modeling_cloth_turbulence = bpy.props.FloatProperty(name="Wind Turbulence", 
        description="Add Randomness to wind", 
        default=0, min=0, max=10, soft_min= 0, soft_max=1)#, update=refresh_noise_decay)

    # self collision ----->>>
    bpy.types.Object.modeling_cloth_self_collision = bpy.props.BoolProperty(name="Modeling Cloth Self Collsion", 
        description="Toggle self collision", 
        default=False, update=collision_data_update)

#    bpy.types.Object.modeling_cloth_self_collision_force = bpy.props.FloatProperty(name="recovery force", 
#        description="Self colide faces repel", 
#        default=.17, precision=4, min= -1.1, max=1.1, soft_min= 0, soft_max=1)

    bpy.types.Object.modeling_cloth_self_collision_margin = bpy.props.FloatProperty(name="Margin", 
        description="Self colide faces margin", 
        default=.08, precision=4, min= -1, max=1, soft_min= 0, soft_max=1)

#    bpy.types.Object.modeling_cloth_self_collision_cy_size = bpy.props.FloatProperty(name="Cylinder size", 
#        description="Self colide faces cylinder size", 
#        default=1, precision=4, min= 0, max=4, soft_min= 0, soft_max=1.5)
    # ---------------------->>>

    # extras ------->>>
    bpy.types.Object.modeling_cloth_inflate = bpy.props.FloatProperty(name="inflate", 
        description="add force to vertex normals", 
        default=0, precision=4, min= -10, max=10, soft_min= -1, soft_max=1)

    bpy.types.Object.modeling_cloth_sew = bpy.props.FloatProperty(name="sew", 
        description="add force to vertex normals", 
        default=0, precision=4, min= -10, max=10, soft_min= -1, soft_max=1)
    # -------------->>>

    # external collisions ------->>>
    global extra_data
    bpy.types.Object.modeling_cloth_object_collision = bpy.props.BoolProperty(name="Modeling Cloth Self Collsion", 
        description="Detect and collide with this object", 
        default=False, update=(lambda self, context: collider.collision_object_update(self, context, extra_data)))

    #bpy.types.Object.modeling_cloth_collision_animated = bpy.props.BoolProperty(name="Modeling Cloth Collsion Animated", 
        #description="Treat collide object as animated. (turn off for speed on static objects)", 
        #default=True)#, update=collision_object_update)
    
    bpy.types.Object.modeling_cloth_object_detect = bpy.props.BoolProperty(name="Modeling Cloth Self Collsion", 
        description="Detect collision objects", 
        default=True, update=cloth_object_update)    

    bpy.types.Object.modeling_cloth_outer_margin = bpy.props.FloatProperty(name="Modeling Cloth Outer Margin", 
        description="Collision margin on positive normal side of face", 
        default=0.04, precision=4, min=0, max=100, soft_min=0, soft_max=1000)
        
    bpy.types.Object.modeling_cloth_inner_margin = bpy.props.FloatProperty(name="Modeling Cloth Inner Margin", 
        description="Collision margin on negative normal side of face", 
        default=0.08, precision=4, min=0, max=100, soft_min=0, soft_max=1000)        
    # ---------------------------->>>
    
    # more collision stuff ------->>>
    bpy.types.Object.modeling_cloth_grid_size = bpy.props.IntProperty(name="Modeling Cloth Grid Size", 
    description="Max subdivisions for the dynamic broad phase grid", 
    default=10, min=0, max=1000, soft_min=0, soft_max=1000)
    
    # property dictionaries
    if "modeling_cloth_data_set" not in dir(bpy.types.Scene):
        bpy.types.Scene.modeling_cloth_data_set = {} 
        bpy.types.Scene.modeling_cloth_data_set_extra = {} 
    
        
def remove_properties():            
    '''Drives to the grocery store and buys a sandwich'''
    del(bpy.types.Object.modeling_cloth)
    del(bpy.types.Object.modeling_cloth_floor)
    del(bpy.types.Object.modeling_cloth_pause)
    del(bpy.types.Object.modeling_cloth_noise)    
    del(bpy.types.Object.modeling_cloth_noise_decay)
    del(bpy.types.Object.modeling_cloth_spring_force)
    del(bpy.types.Object.modeling_cloth_gravity)        
    del(bpy.types.Object.modeling_cloth_iterations)
    del(bpy.types.Object.modeling_cloth_velocity)
    del(bpy.types.Object.modeling_cloth_inflate)
    del(bpy.types.Object.modeling_cloth_sew)

    # self collision
#    del(bpy.types.Object.modeling_cloth_self_collision)    
#    del(bpy.types.Object.modeling_cloth_self_collision_cy_size)    
#    del(bpy.types.Object.modeling_cloth_self_collision_force)    
#    del(bpy.types.Object.modeling_cloth_self_collision_margin)    

    # data storage
    del(bpy.types.Scene.modeling_cloth_data_set)
    del(bpy.types.Scene.modeling_cloth_data_set_extra)


class ModelingClothPanel(bpy.types.Panel):
    """Modeling Cloth Panel"""
    bl_label = "Modeling Cloth Panel"
    bl_idname = "Modeling Cloth"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_category = "Extended Tools"
    #gt_show = True
    
    def draw(self, context):
        status = False
        layout = self.layout
        
        # tools
        col = layout.column(align=True)
        col.label(text="Tools")        
        col.operator("object.modeling_cloth_create_sew_lines", text="Sew Lines", icon="MOD_UVPROJECT")
        col.operator("object.modeling_cloth_apply_cloth_to_mesh", text="Apply to Mesh", icon="FILE_TICK")
        
        # modeling cloth
        col = layout.column(align=True)
        col.label(text="Modeling Cloth")
        ob = bpy.context.object
        cloths = [i for i in bpy.data.objects if i.modeling_cloth] # so we can select an empty and keep the settings menu up
        if len(cloths) > 0:
            extra_data = bpy.context.scene.modeling_cloth_data_set_extra
            if 'alert' not in extra_data:
                global_setup()    
            status = extra_data['alert']
            if ob is not None:
                if ob.type != 'MESH' or status:
                    ob = extra_data['last_object']

        if ob is not None:
            if ob.type == 'MESH':
                col.prop(ob ,"modeling_cloth", text="Modeling Cloth", icon='SURFACE_DATA')               
                if ob.modeling_cloth:    
                    col.prop(ob ,"modeling_cloth_self_collision", text="Self Collision", icon='PHYSICS')
                    col.prop(ob ,"modeling_cloth_self_collision_margin", text="Self Margin")#, icon='PLAY')
                    
                pause = 'PAUSE'
                if ob.modeling_cloth_pause:
                    pause = 'PLAY'
                
                col.prop(ob ,"modeling_cloth_object_collision", text="Collider", icon="STYLUS_PRESSURE")
                #if ob.modeling_cloth_object_collision:
                    #col.prop(ob ,"modeling_cloth_collision_animated", text="Animated", icon="POSE_DATA")
                if ob.modeling_cloth_object_collision:    
                    col.prop(ob ,"modeling_cloth_outer_margin", text="Outer Margin", icon="FORCE_FORCE")
                    col.prop(ob ,"modeling_cloth_inner_margin", text="Inner Margin", icon="STICKY_UVS_LOC")
                    col = layout.column(align=True)
                    
                col.label("Collide List:")
                colliders = [i.name for i in bpy.data.objects if i.modeling_cloth_object_collision]
                for i in colliders:
                    col.label(i)

                if ob.modeling_cloth:

                    # object collisions
                    col = layout.column(align=True)
                    col.label("Collisions")
                    if ob.modeling_cloth:    
                        col.prop(ob ,"modeling_cloth_object_detect", text="Object Collisions", icon="PHYSICS")

                    col = layout.column(align=True)
                    col.scale_y = 2.0
                    #col.prop(ob ,"modeling_cloth_pause", text=pause, icon=pause)               

                    col = layout.column(align=True)
                    col.scale_y = 1.4
                    col.prop(ob, "modeling_cloth_grid_size", text="Grid Boxes", icon="MESH_GRID")
                    col.prop(ob, "modeling_cloth_handler_frame", text="Animation Update", icon="TRIA_RIGHT")
                    if ob.modeling_cloth_handler_frame:    
                        col.prop(ob, "modeling_cloth_auto_reset", text="Frame 1 Reset")
                    col.prop(ob, "modeling_cloth_handler_scene", text="Continuous Update", icon="TIME")
                    col = layout.column(align=True)
                    col.scale_y = 2.0
                    col.operator("object.modeling_cloth_reset", text="Reset")
                    col.alert = extra_data['drag_alert']
                    col.operator("view3d.modeling_cloth_drag", text="Grab")
                    col = layout.column(align=True)
                        
                    col.prop(ob ,"modeling_cloth_iterations", text="Iterations")#, icon='OUTLINER_OB_LATTICE')               
                    col.prop(ob ,"modeling_cloth_spring_force", text="Stiffness")#, icon='OUTLINER_OB_LATTICE')               
                    col.prop(ob ,"modeling_cloth_push_springs", text="Push Springs")#, icon='OUTLINER_OB_LATTICE')               
                    col.prop(ob ,"modeling_cloth_bend_stiff", text="Bend Springs")#, icon='CURVE_NCURVE')               
                    col.prop(ob ,"modeling_cloth_noise", text="Noise")#, icon='PLAY')               
                    col.prop(ob ,"modeling_cloth_noise_decay", text="Decay Noise")#, icon='PLAY')               
                    col.prop(ob ,"modeling_cloth_gravity", text="Gravity")#, icon='PLAY')        
                    col.prop(ob ,"modeling_cloth_inflate", text="Inflate")#, icon='PLAY')        
                    col.prop(ob ,"modeling_cloth_sew", text="Sew Force")#, icon='PLAY')        
                    col.prop(ob ,"modeling_cloth_velocity", text="Velocity")#, icon='PLAY')        
                    col = layout.column(align=True)
                    col.label("Wind")                
                    col.prop(ob ,"modeling_cloth_wind_x", text="Wind X")#, icon='PLAY')        
                    col.prop(ob ,"modeling_cloth_wind_y", text="Wind Y")#, icon='PLAY')        
                    col.prop(ob ,"modeling_cloth_wind_z", text="Wind Z")#, icon='PLAY')        
                    col.prop(ob ,"modeling_cloth_turbulence", text="Turbulence")#, icon='PLAY')        
                    col.prop(ob ,"modeling_cloth_floor", text="Floor")#, icon='PLAY')        
                    col = layout.column(align=True)
                    col.scale_y = 1.5
                    col.alert = status
                    if ob.modeling_cloth:    
                        if ob.mode == 'EDIT':
                            col.operator("object.modeling_cloth_pin_selected", text="Pin Selected")
                            col = layout.column(align=True)
                            col.operator("object.modeling_cloth_add_virtual_spring", text="Add Virtual Springs")
                            col.operator("object.modeling_cloth_remove_virtual_spring", text="Remove Selected")
                        else:
                            col.operator("view3d.modeling_cloth_pin", text="Create Pins")
                        col = layout.column(align=True)
                        col.operator("object.select_modeling_cloth_pins", text="Select Pins")
                        col.operator("object.delete_modeling_cloth_pins", text="Delete Pins")
                        col.operator("object.modeling_cloth_grow", text="Grow Source")
                        col.operator("object.modeling_cloth_shrink", text="Shrink Source")
                        col = layout.column(align=True)
                        #col.prop(ob ,"modeling_cloth_self_collision", text="Self Collision")#, icon='PLAY')        
                        #col.prop(ob ,"modeling_cloth_self_collision_force", text="Repel")#, icon='PLAY')        
                        #col.prop(ob ,"modeling_cloth_self_collision_margin", text="Margin")#, icon='PLAY')        
                        #col.prop(ob ,"modeling_cloth_self_collision_cy_size", text="Cylinder Size")#, icon='PLAY')        

                    
                # =============================
                col = layout.column(align=True)
                col.label('Collision Series')
                col.operator("object.modeling_cloth_collision_series", text="Paperback")
                col.operator("object.modeling_cloth_collision_series_kindle", text="Kindle")
                col.operator("object.modeling_cloth_donate", text="Donate")


class CollisionSeries(bpy.types.Operator):
    """Support my addons by checking out my awesome sci fi books"""
    bl_idname = "object.modeling_cloth_collision_series"
    bl_label = "Modeling Cloth Collision Series"
        
    def execute(self, context):
        collision_series()
        return {'FINISHED'}


class CollisionSeriesKindle(bpy.types.Operator):
    """Support my addons by checking out my awesome sci fi books"""
    bl_idname = "object.modeling_cloth_collision_series_kindle"
    bl_label = "Modeling Cloth Collision Series Kindle"
        
    def execute(self, context):
        collision_series(False)
        return {'FINISHED'}


class Donate(bpy.types.Operator):
    """Support my addons by donating"""
    bl_idname = "object.modeling_cloth_donate"
    bl_label = "Modeling Cloth Donate"

        
    def execute(self, context):
        collision_series(False, False)
        self.report({'INFO'}, 'Paypal, The3dAdvantage@gmail.com')
        return {'FINISHED'}


def collision_series(paperback=True, kindle=True):
    import webbrowser
    import imp
    if paperback:    
        webbrowser.open("https://www.createspace.com/6043857")
        imp.reload(webbrowser)
        webbrowser.open("https://www.createspace.com/7164863")
        return
    if kindle:
        webbrowser.open("https://www.amazon.com/Resolve-Immortal-Flesh-Collision-Book-ebook/dp/B01CO3MBVQ")
        imp.reload(webbrowser)
        webbrowser.open("https://www.amazon.com/Formulacrum-Collision-Book-Rich-Colburn-ebook/dp/B0711P744G")
        return
    webbrowser.open("https://www.paypal.com/donate/?token=G1UymFn4CP8lSFn1r63jf_XOHAuSBfQJWFj9xjW9kWCScqkfYUCdTzP-ywiHIxHxYe7uJW&country.x=US&locale.x=US")

# ============================================================================================    
    


def register():
    create_properties()
    bpy.utils.register_class(ModelingClothPanel)
    bpy.utils.register_class(ModelingClothPin)
    bpy.utils.register_class(ModelingClothDrag)
    bpy.utils.register_class(DeletePins)
    bpy.utils.register_class(SelectPins)
    bpy.utils.register_class(PinSelected)
    bpy.utils.register_class(GrowSource)
    bpy.utils.register_class(ShrinkSource)
    bpy.utils.register_class(ResetShapes)
    bpy.utils.register_class(UpdataPinWeights)
    bpy.utils.register_class(AddVirtualSprings)
    bpy.utils.register_class(RemoveVirtualSprings)
    bpy.utils.register_class(ModelingClothSew)
    bpy.utils.register_class(ApplyClothToMesh)
    
    
    bpy.utils.register_class(CollisionSeries)
    bpy.utils.register_class(CollisionSeriesKindle)
    bpy.utils.register_class(Donate)


def unregister():
    remove_properties()
    bpy.utils.unregister_class(ModelingClothPanel)
    bpy.utils.unregister_class(ModelingClothPin)
    bpy.utils.unregister_class(ModelingClothDrag)
    bpy.utils.unregister_class(DeletePins)
    bpy.utils.unregister_class(SelectPins)
    bpy.utils.unregister_class(PinSelected)
    bpy.utils.unregister_class(GrowSource)
    bpy.utils.unregister_class(ShrinkSource)
    bpy.utils.unregister_class(ResetShapes)
    bpy.utils.unregister_class(UpdataPinWeights)
    bpy.utils.unregister_class(AddVirtualSprings)
    bpy.utils.unregister_class(RemoveVirtualSprings)
    bpy.utils.unregister_class(ModelingClothSew)
    bpy.utils.unregister_class(ApplyClothToMesh)
    
    
    bpy.utils.unregister_class(CollisionSeries)
    bpy.utils.unregister_class(CollisionSeriesKindle)
    bpy.utils.unregister_class(Donate)
    
    
if __name__ == "__main__":
    register()

    # testing!!!!!!!!!!!!!!!!
    #generate_collision_data(bpy.context.object)
    # testing!!!!!!!!!!!!!!!!
    
    for i in bpy.data.objects:
        i.modeling_cloth = False
        i.modeling_cloth_object_collision = False
        
    for i in bpy.app.handlers.frame_change_post:
        if i.__name__ == 'handler_frame':
            bpy.app.handlers.frame_change_post.remove(i)
            
    for i in bpy.app.handlers.scene_update_post:
        if i.__name__ == 'handler_scene':
            bpy.app.handlers.scene_update_post.remove(i)            
