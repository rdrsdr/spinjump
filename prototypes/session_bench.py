"""Mede a taxa atingida pela sessão do servidor (fator 4×) com renderização ativa."""
import time, threading
from spinjump.config import load_config
from spinjump.web import server as srv
import spinjump.web.server as S

class M:
    n = 0
    def broadcast(self, m): pass
    def broadcast_frame(self, j, t): self.n += 1

def main():
    mgr = M()
    s = srv.Session(load_config(sets=["ui.playback_factor=4"]), mgr)
    # instrumenta o passo
    orig = s.sim.step
    acc = [0.0, 0]
    def timed():
        t = time.perf_counter(); r = orig(); acc[0] += time.perf_counter() - t; acc[1] += 1; return r
    s.sim.step = timed
    orig_pub = s._publish
    pub = [0.0, 0]
    def tpub(now):
        t = time.perf_counter(); orig_pub(now); pub[0] += time.perf_counter() - t; pub[1] += 1
    s._publish = tpub
    s.start()
    time.sleep(8)
    print('sim t', round(s.sim.d.time, 2), 'rate', round(s.rate, 3), 'frames', mgr.n, 'render ms', round(s.render_ms, 1))
    print('step us', round(acc[0]/acc[1]*1e6, 1), 'step total s', round(acc[0], 2), 'publish ms', round(pub[0]/max(pub[1],1)*1e3, 2), 'n', pub[1])
    s.stop_flag = True
    s.t_phys.join(timeout=60)
    s.renderer.close()
    print('closed')

if __name__ == '__main__':
    main()
