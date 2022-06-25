import  re
import jittor as jt
import numpy as np
from jittor import searchsorted
from kornia import create_meshgrid
jt.flags.use_cuda = 1

# from utils import index_point_feature

def depth2dist(z_vals, cos_angle):
    # z_vals: [N_ray N_sample]

    dists = z_vals[..., 1:] - z_vals[..., :-1]
    dists = jt.concat([dists, jt.array([1e10]).expand(dists[..., :1].shape)], -1)  # [N_rays, N_samples]
    dists = dists * cos_angle.unsqueeze(-1)
    return dists


def ndc2dist(ndc_pts, cos_angle):
    dists = jt.norm(ndc_pts[:, 1:] - ndc_pts[:, :-1], dim=-1)
    dists = jt.concat([dists, 1e10 * cos_angle.unsqueeze(-1)], -1)  # [N_rays, N_samples]
    return dists


def get_ray_directions(H, W, focal, center=None):
    """
    Get ray directions for all pixels in camera coordinate.
    Reference: https://www.scratchapixel.com/lessons/3d-basic-rendering/
               ray-tracing-generating-camera-rays/standard-coordinate-systems
    Inputs:
        H, W, focal: image height, width and focal length
    Outputs:
        directions: (H, W, 3), the direction of the rays in camera coordinate
    """
    grid = create_meshgrid(H, W, normalized_coordinates=False)[0] + 0.5

    i, j = grid.unbind(-1)
    #TODO:直接用jittor计算
    # i=jt.array(i.numpy())
    # j=jt.array(j.numpy())
    # # the direction here is without +0.5 pixel centering as calibration is not so accurate
    # # see https://github.com/bmild/nerf/issues/24
    # cent = center if center is not None else [W / 2, H / 2]
    # directions = jt.stack([(i - cent[0]) / focal[0], (j - cent[1]) / focal[1], jt.ones_like(i)], -1)  # (H, W, 3)

    i=i.numpy()
    j=j.numpy()
    # the direction here is without +0.5 pixel centering as calibration is not so accurate
    # see https://github.com/bmild/nerf/issues/24
    cent = center if center is not None else [W / 2, H / 2]
    directions = np.stack([(i - cent[0]) / focal[0], (j - cent[1]) / focal[1], np.ones_like(i)], -1)  # (H, W, 3)
    directions=jt.array(directions)
    return directions


def get_ray_directions_blender(H, W, focal, center=None):
    """
    Get ray directions for all pixels in camera coordinate.
    Reference: https://www.scratchapixel.com/lessons/3d-basic-rendering/
               ray-tracing-generating-camera-rays/standard-coordinate-systems
    Inputs:
        H, W, focal: image height, width and focal length
    Outputs:
        directions: (H, W, 3), the direction of the rays in camera coordinate
    """
    grid = create_meshgrid(H, W, normalized_coordinates=False)[0]+0.5
    i, j = grid.unbind(-1)
    i=jt.array(i.numpy())   #TODO:改用jittor
    j=jt.array(j.numpy())
    # the direction here is without +0.5 pixel centering as calibration is not so accurate
    # see https://github.com/bmild/nerf/issues/24
    cent = center if center is not None else [W / 2, H / 2]
    directions = jt.stack([(i - cent[0]) / focal[0], -(j - cent[1]) / focal[1], -jt.ones_like(i)],
                             -1)  # (H, W, 3)

    return directions


def get_rays(directions, c2w):
    """
    Get ray origin and normalized directions in world coordinate for all pixels in one image.
    Reference: https://www.scratchapixel.com/lessons/3d-basic-rendering/
               ray-tracing-generating-camera-rays/standard-coordinate-systems
    Inputs:
        directions: (H, W, 3) precomputed ray directions in camera coordinate
        c2w: (3, 4) transformation matrix from camera coordinate to world coordinate
    Outputs:
        rays_o: (H*W, 3), the origin of the rays in world coordinate
        rays_d: (H*W, 3), the normalized direction of the rays in world coordinate
    """
    # Rotate ray directions from camera coordinate to the world coordinate
    rays_d = directions @ jt.transpose(c2w[:3, :3], [1,0])  # (H, W, 3)
    # rays_d = rays_d / jt.norm(rays_d, dim=-1, keepdim=True)
    # The origin of all rays is the camera origin in world coordinate
    rays_o = c2w[:3, 3].expand(rays_d.shape)  # (H, W, 3)

    rays_d = rays_d.view(-1, 3)
    rays_o = rays_o.view(-1, 3)

    return rays_o, rays_d


def ndc_rays_blender(H, W, focal, near, rays_o, rays_d):
    # Shift ray origins to near plane
    t = -(near + rays_o[..., 2]) / rays_d[..., 2]
    rays_o = rays_o + t[..., None] * rays_d

    # Projection
    o0 = -1. / (W / (2. * focal)) * rays_o[..., 0] / rays_o[..., 2]
    o1 = -1. / (H / (2. * focal)) * rays_o[..., 1] / rays_o[..., 2]
    o2 = 1. + 2. * near / rays_o[..., 2]

    d0 = -1. / (W / (2. * focal)) * (rays_d[..., 0] / rays_d[..., 2] - rays_o[..., 0] / rays_o[..., 2])
    d1 = -1. / (H / (2. * focal)) * (rays_d[..., 1] / rays_d[..., 2] - rays_o[..., 1] / rays_o[..., 2])
    d2 = -2. * near / rays_o[..., 2]

    rays_o = jt.stack([o0, o1, o2], -1)
    rays_d = jt.stack([d0, d1, d2], -1)

    return rays_o, rays_d

def ndc_rays(H, W, focal, near, rays_o, rays_d):
    # Shift ray origins to near plane
    t = (near - rays_o[..., 2]) / rays_d[..., 2]
    rays_o = rays_o + t[..., None] * rays_d

    # Projection
    o0 = 1. / (W / (2. * focal)) * rays_o[..., 0] / rays_o[..., 2]
    o1 = 1. / (H / (2. * focal)) * rays_o[..., 1] / rays_o[..., 2]
    o2 = 1. - 2. * near / rays_o[..., 2]

    d0 = 1. / (W / (2. * focal)) * (rays_d[..., 0] / rays_d[..., 2] - rays_o[..., 0] / rays_o[..., 2])
    d1 = 1. / (H / (2. * focal)) * (rays_d[..., 1] / rays_d[..., 2] - rays_o[..., 1] / rays_o[..., 2])
    d2 = 2. * near / rays_o[..., 2]

    rays_o = jt.stack([o0, o1, o2], -1)
    rays_d = jt.stack([d0, d1, d2], -1)

    return rays_o, rays_d

# Hierarchical sampling (section 5.2)
def sample_pdf(bins, weights, N_samples, det=False, pytest=False):

    # Get pdf
    weights = weights + 1e-5  # prevent nans
    pdf = weights / jt.sum(weights, -1, keepdim=True)
    cdf = jt.cumsum(pdf, -1)
    cdf = jt.concat([jt.zeros_like(cdf[..., :1]), cdf], -1)  # (batch, len(bins))

    # Take uniform samples
    if det:
        u = jt.linspace(0., 1., steps=N_samples)
        u = u.expand(list(cdf.shape[:-1]) + [N_samples])
    else:
        u = jt.rand(list(cdf.shape[:-1]) + [N_samples])

    # Pytest, overwrite u with numpy's fixed random numbers
    if pytest:
        np.random.seed(0)
        new_shape = list(cdf.shape[:-1]) + [N_samples]
        if det:
            u = np.linspace(0., 1., N_samples)
            u = np.broadcast_to(u, new_shape)
        else:
            u = np.random.rand(*new_shape)
        u = jt.float64(u)

    # Invert CDF

    inds = searchsorted(cdf.detach(), u, right=True)
    below = jt.max(jt.zeros_like(inds - 1), inds - 1)
    above = jt.min((cdf.shape[-1] - 1) * jt.ones_like(inds), inds)
    inds_g = jt.stack([below, above], -1)  # (batch, N_samples, 2)

    matched_shape = [inds_g.shape[0], inds_g.shape[1], cdf.shape[-1]]
    cdf_g = jt.gather(cdf.unsqueeze(1).expand(matched_shape), 2, inds_g)
    bins_g = jt.gather(bins.unsqueeze(1).expand(matched_shape), 2, inds_g)

    denom = (cdf_g[..., 1] - cdf_g[..., 0])
    denom = jt.where(denom < 1e-5, jt.ones_like(denom), denom)
    t = (u - cdf_g[..., 0]) / denom
    samples = bins_g[..., 0] + t * (bins_g[..., 1] - bins_g[..., 0])

    return samples


def dda(rays_o, rays_d, bbox_3D):
    inv_ray_d = 1.0 / (rays_d + 1e-6)
    t_min = (bbox_3D[:1] - rays_o) * inv_ray_d  # N_rays 3
    t_max = (bbox_3D[1:] - rays_o) * inv_ray_d
    t = jt.stack((t_min, t_max))  # 2 N_rays 3
    t_min = jt.max(jt.min(t, dim=0)[0], dim=-1, keepdim=True)[0]
    t_max = jt.min(jt.max(t, dim=0)[0], dim=-1, keepdim=True)[0]
    return t_min, t_max


def ray_marcher(rays,
                N_samples=64,
                lindisp=False,
                perturb=0,
                bbox_3D=None):
    """
    sample points along the rays
    Inputs:
        rays: ()

    Returns:

    """

    # Decompose the inputs
    N_rays = rays.shape[0]
    rays_o, rays_d = rays[:, 0:3], rays[:, 3:6]  # both (N_rays, 3)
    near, far = rays[:, 6:7], rays[:, 7:8]  # both (N_rays, 1)

    if bbox_3D is not None:
        # cal aabb boundles
        near, far = dda(rays_o, rays_d, bbox_3D)

    # Sample depth points
    z_steps = jt.linspace(0, 1, N_samples)  # (N_samples)
    if not lindisp:  # use linear sampling in depth space
        z_vals = near * (1 - z_steps) + far * z_steps
    else:  # use linear sampling in disparity space
        z_vals = 1 / (1 / near * (1 - z_steps) + 1 / far * z_steps)

    z_vals = z_vals.expand(N_rays, N_samples)

    if perturb > 0:  # perturb sampling depths (z_vals)
        z_vals_mid = 0.5 * (z_vals[:, :-1] + z_vals[:, 1:])  # (N_rays, N_samples-1) interval mid points
        # get intervals between samples
        upper = jt.concat([z_vals_mid, z_vals[:, -1:]], -1)
        lower = jt.concat([z_vals[:, :1], z_vals_mid], -1)

        perturb_rand = perturb * jt.rand(z_vals.shape)
        z_vals = lower + (upper - lower) * perturb_rand

    xyz_coarse_sampled = rays_o.unsqueeze(1) + \
                         rays_d.unsqueeze(1) * z_vals.unsqueeze(2)  # (N_rays, N_samples, 3)

    return xyz_coarse_sampled, rays_o, rays_d, z_vals


def read_pfm(filename):
    file = open(filename, 'rb')
    color = None
    width = None
    height = None
    scale = None
    endian = None

    header = file.readline().decode('utf-8').rstrip()
    if header == 'PF':
        color = True
    elif header == 'Pf':
        color = False
    else:
        raise Exception('Not a PFM file.')

    dim_match = re.match(r'^(\d+)\s(\d+)\s$', file.readline().decode('utf-8'))
    if dim_match:
        width, height = map(int, dim_match.groups())
    else:
        raise Exception('Malformed PFM header.')

    scale = float(file.readline().rstrip())
    if scale < 0:  # little-endian
        endian = '<'
        scale = -scale
    else:
        endian = '>'  # big-endian

    data = np.fromfile(file, endian + 'f')
    shape = (height, width, 3) if color else (height, width)

    data = np.reshape(data, shape)
    data = np.flipud(data)
    file.close()
    return data, scale


def ndc_bbox(all_rays):
    near_min = jt.min(all_rays[...,:3].view(-1,3),dim=0)[0]
    near_max = jt.max(all_rays[..., :3].view(-1, 3), dim=0)[0]
    far_min = jt.min((all_rays[...,:3]+all_rays[...,3:6]).view(-1,3),dim=0)[0]
    far_max = jt.max((all_rays[...,:3]+all_rays[...,3:6]).view(-1, 3), dim=0)[0]
    print(f'===> ndc bbox near_min:{near_min} near_max:{near_max} far_min:{far_min} far_max:{far_max}')
    return jt.stack((jt.minimum(near_min,far_min),jt.maximum(near_max,far_max)))