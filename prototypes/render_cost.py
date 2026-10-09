import time, sys, os
from spinjump.config import load_config
from spinjump.sim import Simulation
from spinjump.render import SceneRenderer, frame_state, CameraState, encode_jpeg
if __name__ == "__main__":
    slices, stacks, ppt = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    s = Simulation(load_config(sets=["solver.max_time_s=3"])).run()
    xml = s.b.xml.replace('<quality shadowsize="2048" offsamples="4"/>', f'<quality shadowsize="0" offsamples="0" numslices="{slices}" numstacks="{stacks}"/>')
    sr = SceneRenderer(xml, 960, 600, 0.04, 50)
    fs = frame_state(s, 12)
    fs.stored = s.rope.stored_polyline(12, pts_per_turn=ppt).astype('float32')
    for mode in ("free", "follow"):
        cs = CameraState(mode=mode)
        sr.render(fs, cs)
        t0 = time.perf_counter()
        for _ in range(20): img = sr.render(fs, cs)
        t1 = time.perf_counter()
        for _ in range(20): encode_jpeg(img, 80)
        t2 = time.perf_counter()
        print(slices, stacks, ppt, mode, 'render ms', round((t1-t0)/20*1e3,1), 'jpeg ms', round((t2-t1)/20*1e3,1), 'ngeom', sr.r.scene.ngeom, 'cpu', os.cpu_count())
