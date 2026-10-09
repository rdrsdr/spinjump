import numpy as np, math
from spinjump.config import load_config
from spinjump.sim import Simulation, TELEMETRY_FIELDS
F = {k:i for i,k in enumerate(TELEMETRY_FIELDS)}
if __name__ == "__main__":
    out = {}
    for rel in (False, True):
        s = Simulation(load_config()); s.release_rope_at_ground = rel; s.run()
        S = np.array(s.samples); tg = s.tr.first_ground_t; i = np.searchsorted(S[:,0], tg)
        p = S[i:, [F['x'], F['y']]]
        path = np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1)); net = np.linalg.norm(p[-1]-p[0])
        rad = np.hypot(p[:,0], p[:,1])
        out[rel] = p[-1]
        print('solta' if rel else 'corda', 'path', round(path,2), 'net', round(net,2), 'straight', round(net/path,3), 'rad0', round(rad[0],2), 'radmax', round(rad.max(),2), 'radend', round(rad[-1],2), 'dtheta_deg', round((S[-1,F['theta_turns']]-S[i,F['theta_turns']])*360,1))
    print('distância entre pontos finais', round(float(np.linalg.norm(out[True]-out[False])),2))
