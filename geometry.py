import bpy
import bmesh
import numpy as np
from numpy import newaxis as nax
from bpy_extras import view3d_utils
import time

def get_co(ob, arr=None, key=None): # key
    """Returns vertex coords as N x 3"""
    c = len(ob.data.vertices)
    if arr is None:    
        arr = np.zeros(c * 3, dtype=np.float32)
    if key is not None:
        ob.data.shape_keys.key_blocks[key].data.foreach_get('co', arr.ravel())        
        arr.shape = (c, 3)
        return arr
    ob.data.vertices.foreach_get('co', arr.ravel())
    arr.shape = (c, 3)
    return arr

def get_proxy_co(ob, arr, me):
    """Returns vertex coords with modifier effects as N x 3"""
    if arr is None:
        arr = np.zeros(len(me.vertices) * 3, dtype=np.float32)
        arr.shape = (arr.shape[0] //3, 3)    
    c = arr.shape[0]
    me.vertices.foreach_get('co', arr.ravel())
    arr.shape = (c, 3)
    return arr

def proxy_in_place(object, me):
    """Overwrite vert coords with modifiers in world space"""
    me.vertices.foreach_get('co', object.co.ravel())
    object.co = apply_transforms(object.ob, object.co)


def apply_rotation(object):
    """When applying vectors such as normals we only need
    to rotate"""
    m = np.array(object.ob.matrix_world)
    mat = m[:3, :3].T
    object.v_normals = object.v_normals @ mat
    

def proxy_v_normals_in_place(object, world=True, me=None):
    """Overwrite vert coords with modifiers in world space"""
    me.vertices.foreach_get('normal', object.v_normals.ravel())
    if world:    
        apply_rotation(object)


def proxy_v_normals(ob, me):
    """Overwrite vert coords with modifiers in world space"""
    arr = np.zeros(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get('normal', arr)
    arr.shape = (arr.shape[0] //3, 3)
    m = np.array(ob.matrix_world, dtype=np.float32)    
    mat = m[:3, :3].T # rotates backwards without T
    return arr @ mat


def apply_transforms(ob, co):
    """Get vert coords in world space"""
    m = np.array(ob.matrix_world, dtype=np.float32)    
    mat = m[:3, :3].T # rotates backwards without T
    loc = m[:3, 3]
    return co @ mat + loc


def apply_in_place(ob, arr, cloth):
    """Overwrite vert coords in world space"""
    m = np.array(ob.matrix_world, dtype=np.float32)    
    mat = m[:3, :3].T # rotates backwards without T
    loc = m[:3, 3]
    arr[:] = arr @ mat + loc
    #cloth.co = cloth.co @ mat + loc


def applied_key_co(ob, arr=None, key=None):
    """Get vert coords in world space"""
    c = len(ob.data.vertices)
    if arr is None:
        arr = np.zeros(c * 3, dtype=np.float32)
    ob.data.shape_keys.key_blocks[key].data.foreach_get('co', arr)
    arr.shape = (c, 3)
    m = np.array(ob.matrix_world)    
    mat = m[:3, :3].T # rotates backwards without T
    loc = m[:3, 3]
    return arr @ mat + loc


def revert_transforms(ob, co):
    """Set world coords on object. 
    Run before setting coords to deal with object transforms
    if using apply_transforms()"""
    m = np.linalg.inv(ob.matrix_world)    
    mat = m[:3, :3].T # rotates backwards without T
    loc = m[:3, 3]
    return co @ mat + loc  


def revert_in_place(ob, co):
    """Revert world coords to object coords in place."""
    m = np.linalg.inv(ob.matrix_world)    
    mat = m[:3, :3].T # rotates backwards without T
    loc = m[:3, 3]
    co[:] = co @ mat + loc


def revert_rotation(ob, co):
    """When reverting vectors such as normals we only need
    to rotate"""
    #m = np.linalg.inv(ob.matrix_world)    
    m = np.array(ob.matrix_world)
    mat = m[:3, :3] # rotates backwards without T
    return co @ mat

def triangulate(me, ob=None):
    """Requires a mesh. Returns an index array for viewing co as triangles"""
    obm = bmesh.new()
    obm.from_mesh(me)        
    bmesh.ops.triangulate(obm, faces=obm.faces)
    #obm.to_mesh(me)        
    count = len(obm.faces)    
    #tri_idx = np.zeros(count * 3, dtype=np.int32)        
    #me.polygons.foreach_get('vertices', tri_idx)
    tri_idx = np.array([[v.index for v in f.verts] for f in obm.faces])
    
    # Identify bend spring groups. Each edge gets paired with two points on tips of tris around edge    
    # Restricted to edges with two linked faces on a triangulated version of the mesh
    if ob is not None:
        link_ed = [e for e in obm.edges if len(e.link_faces) == 2]
        ob.bend_eidx = np.array([[e.verts[0].index, e.verts[1].index] for e in link_ed])
        fv = np.array([[[v.index for v in f.verts] for f in e.link_faces] for e in link_ed])
        fv.shape = (fv.shape[0],6)
        ob.bend_tips = np.array([[idx for idx in fvidx if idx not in e] for e, fvidx in zip(ob.bend_eidx, fv)])
    obm.free()
    
    return tri_idx#.reshape(count, 3)


def tri_normals_in_place(object, tri_co):    
    """Takes N x 3 x 3 set of 3d triangles and 
    returns non-unit normals and origins"""
    object.origins = tri_co[:,0]
    object.cross_vecs = tri_co[:,1:] - object.origins[:, nax]
    object.normals = np.cross(object.cross_vecs[:,0], object.cross_vecs[:,1])
    object.nor_dots = np.einsum("ij, ij->i", object.normals, object.normals)
    object.normals /= np.sqrt(object.nor_dots)[:, nax]


def get_tri_normals(tr_co):
    """Takes N x 3 x 3 set of 3d triangles and 
    returns non-unit normals and origins"""
    origins = tr_co[:,0]
    cross_vecs = tr_co[:,1:] - origins[:, nax]
    return cross_vecs, np.cross(cross_vecs[:,0], cross_vecs[:,1]), origins


def closest_points_edge(vec, origin, p):
    '''Returns the location of the point on the edge'''
    vec2 = p - origin
    d = (vec2 @ vec) / (vec @ vec)
    cp = vec * d[:, nax]
    return cp, d