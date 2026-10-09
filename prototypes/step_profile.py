import cProfile, pstats, time
from spinjump.config import load_config
from spinjump.sim import Simulation
if __name__ == "__main__":
    s = Simulation(load_config(sets=['solver.max_time_s=5']))
    pr = cProfile.Profile(); pr.enable(); s.run(); pr.disable()
    pstats.Stats(pr).sort_stats('tottime').print_stats(18)
