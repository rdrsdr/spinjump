---
title: SpinJump
emoji: 🌀
colorFrom: blue
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
short_description: Live 3D physics sim of a rope spiral around a chimney
---

# SpinJump — live 3D physics simulation

> **Simulation only.** Qualitative, exploratory results from a simplified model. They are **not** a
> human-safety validation, **not** instructions, and **not** a recommendation. The real activity can
> kill or seriously injure — **do not attempt it.**

A virtual crash-test dummy tied to a rope wound around the top of a 50 m chimney leaves the edge,
swings around the chimney as the rope unwinds, spirals down, hits the ground and slides. The rope
lying on the wall is simulated with friction: with a steep pull the coils slide down the chimney, and
that friction brakes the descent (a checkbox switches to the faster locked-coil model). Physics
(MuJoCo) and 3D rendering run on the server; your browser receives live frames and telemetry.

**How to use:** read the intro page and confirm → pick a preset or edit the form → **Start**. Drag the
image to orbit the camera (Free mode), use the wheel to zoom and the slider to change playback speed.
When it ends you get a summary and a link to the report.

**About this public instance**

- Each visitor gets their own simulation; the server runs at most 2 at a time (free CPU tier). If it
  is full, wait a moment and try again.
- Free CPU (no GPU): the effective rate is shown on screen and may drop below 1× when two people are
  simulating at once. Each run is capped at 180 simulated seconds.
- The Space sleeps when unused; the first visit after that may take a few minutes.
- Reports are temporary (only the most recent runs are kept) and anyone with the link can open them.

Technical documentation (in Portuguese): [DOCUMENTACAO.md](DOCUMENTACAO.md) and [NOTES.md](NOTES.md).
