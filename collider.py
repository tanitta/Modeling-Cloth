class Collider(object):
    pass


class SelfCollider(object):
    pass


def create_collider():
    col = Collider()
    col.ob = bpy.context.object

    # get proxy
    proxy = col.ob.to_mesh(bpy.context.scene, True, 'PREVIEW')
    
    col.co = get_proxy_co(col.ob, None, proxy)
    col.idxer = np.arange(col.co.shape[0], dtype=np.int32)
    proxy_in_place(col, proxy)
    col.v_normals = proxy_v_normals(col.ob, proxy)
    col.vel = np.copy(col.co)
    col.tridex = triangulate(proxy)
    col.tridexer = np.arange(col.tridex.shape[0], dtype=np.int32)
    # cross_vecs used later by barycentric tri check
    proxy_v_normals_in_place(col, True, proxy)
    marginalized = col.co + col.v_normals * col.ob.modeling_cloth_outer_margin
    col.cross_vecs, col.origins, col.normals = get_tri_normals(marginalized[col.tridex])    
    
    # remove proxy
    bpy.data.meshes.remove(proxy)
    return col


# Self collision object
def create_self_collider():
    # maybe fixed? !!! bug where first frame of collide uses empty data. Stuff goes flying.
    col = Collider()
    col.ob = bpy.context.object
    col.co = get_co(col.ob, None)
    proxy_in_place(col)
    col.v_normals = proxy_v_normals(col.ob)
    col.vel = np.copy(col.co)
    #col.tridex = triangulate(col.ob)
    col.tridexer = np.arange(col.tridex.shape[0], dtype=np.int32)
    # cross_vecs used later by barycentric tri check
    proxy_v_normals_in_place(col)
    marginalized = col.co + col.v_normals * col.ob.modeling_cloth_outer_margin
    col.cross_vecs, col.origins, col.normals = get_tri_normals(marginalized[col.tridex])    

    return col


# collide object updater
def collision_object_update(self, context):
    """Updates the collider object"""    
    collide = self.modeling_cloth_object_collision
    # remove objects from dict if deleted
    cull_list = []
    if 'colliders' in extra_data:
        if extra_data['colliders'] is not None:   
            if not collide:
                if self.name in extra_data['colliders']:
                    del(extra_data['colliders'][self.name])
            for i in extra_data['colliders']:
                remove = True
                if i in bpy.data.objects:
                    if bpy.data.objects[i].type == "MESH":
                        if bpy.data.objects[i].modeling_cloth_object_collision:
                            remove = False
                if remove:
                    cull_list.append(i)
    for i in cull_list:
        del(extra_data['colliders'][i])

    # add class to dict if true.
    if collide:    
        if 'colliders' not in extra_data:    
            extra_data['colliders'] = {}
        if extra_data['colliders'] is None:
            extra_data['colliders'] = {}
        extra_data['colliders'][self.name] = create_collider()