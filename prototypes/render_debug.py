import numpy as np
from PIL import Image
from spinjump.config import load_config
from spinjump.sim import Simulation
from spinjump.render import SceneRenderer, frame_state, CameraState
if __name__ == "__main__":
    s = Simulation(load_config(sets=["solver.max_time_s=8"])).run()
    sr = SceneRenderer(s.b.xml, 960, 600, 0.04, 50)
    fs = frame_state(s, 12)
    print("com", fs.com, "qpos", fs.qpos, "render body xpos", )
    img = sr.render(fs, CameraState(mode="follow", distance=95))
    print("renderer body pos", sr.d.xpos[1], "geom sizes", sr.m.geom_size[sr.m.geom_bodyid==1][:3])
    Image.fromarray(img).save("out/debug_follow.png")
    cs = CameraState(mode="free", distance=6, lookat=list(fs.com), azimuth=30, elevation=-10)
    Image.fromarray(sr.render(fs, cs)).save("out/debug_close.png")
