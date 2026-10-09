import math
import numpy as np
import spinjump.surface_rope as sr
from spinjump.config import load_config
from spinjump.sim import Simulation

cap = {}
orig = sr.solve_banded
def spy(lu, ab, b, **kw):
    cap["ab"] = ab.copy(); cap["b"] = b.copy()
    return orig(lu, ab, b, **kw)
sr.solve_banded = spy

if __name__ == "__main__":
    s = Simulation(load_config(sets=["rope.coil_update_every_steps=1", "rope.coil_window_turns=0.25"]))
    r = s.rope
    r._step_chain(0.0, 0.0, 9.81)
    ab = cap["ab"]; size = ab.shape[1]; u = 3
    A = np.zeros((size, size))
    for i in range(size):
        for j in range(max(0, i - 3), min(size, i + 4)):
            A[i, j] = ab[u + i - j, j]
    print("size", size, "simétrica:", np.allclose(A, A.T), "autovalor mín", np.linalg.eigvalsh(0.5 * (A + A.T)).min())
    print("diag[:6]", np.round(np.diag(A)[:6], 6))
    print("linha 2:", np.round(A[2, :8], 6))
    print("linha 3:", np.round(A[3, :8], 6))
